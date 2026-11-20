"""Streaming tests for the platform-owned LangGraph runtime."""

import asyncio
import queue
import threading
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.models import Agent, Run
from app.providers.base import ConnectivityResult, ExecutionResult, StreamEvent
from app.services.execution import prepare_execution, stream_execution
from app.services.sse import _produce, event_stream_response


class _ConnectedRequest:
    """Minimal stand-in for ``starlette.requests.Request``."""

    async def is_disconnected(self) -> bool:
        return False


def _langchain_ok() -> ConnectivityResult:
    return ConnectivityResult(
        ok=True,
        status="connected",
        capabilities={"execute": True, "streaming": True, "graph": True},
        resource_label="test-model",
        details={"model": "test-model"},
    )


def _make_langchain_agent(client: TestClient, ws_id: str) -> dict:
    conn = client.post(
        "/api/v1/provider-connections",
        json={
            "provider": "langchain",
            "name": "LC",
            "base_url": "http://localhost:11434/v1",
            "api_key": "k",
            "model": "test-model",
        },
    )
    assert conn.status_code == 200, conn.text
    agent = client.post(
        "/api/v1/agents",
        json={"workspace_id": ws_id, "name": "Streamer"},
    ).json()
    linked = client.post(
        f"/api/v1/agents/{agent['id']}/link",
        json={"provider_connection_id": conn.json()["id"]},
    )
    assert linked.status_code == 200, linked.text
    return agent


def test_platform_stream_route_persists_and_emits_events(client: TestClient, user_a: dict) -> None:
    ws = client.get("/api/v1/workspaces").json()["items"][0]
    with patch(
        "app.providers.langchain.LangChainProvider.check_connectivity",
        return_value=_langchain_ok(),
    ):
        agent = _make_langchain_agent(client, ws["id"])

    def fake_stream(*args, **kwargs):
        yield StreamEvent.chunk("hi")
        yield StreamEvent.final(
            ExecutionResult(
                status="completed",
                output={"message": "hi there"},
                token_count=2,
            )
        )

    with patch("app.providers.langchain.LangChainProvider.stream", side_effect=fake_stream):
        response = client.post(
            f"/api/v1/agents/{agent['id']}/test/stream",
            json={"input": {"message": "hello"}},
        )
    assert response.status_code == 200, response.text
    assert "event: chunk" in response.text
    assert "event: final" in response.text
    assert "hi there" in response.text
    assert '"run_id": "run_' in response.text


def test_stream_cancellation_marks_run_cancelled(
    client: TestClient, user_a: dict
) -> None:
    ws = client.get("/api/v1/workspaces").json()["items"][0]
    with patch(
        "app.providers.langchain.LangChainProvider.check_connectivity",
        return_value=_langchain_ok(),
    ):
        agent_data = _make_langchain_agent(client, ws["id"])

    settings = get_settings()
    db = SessionLocal()
    try:
        agent = db.get(Agent, agent_data["id"])
        assert agent is not None
        ctx = prepare_execution(
            db,
            settings,
            agent=agent,
            payload={"message": "hi"},
            conversation_id=None,
            metadata={},
            source="test",
            credential=None,
            correlation_id="corr-cancel",
            user_label="tester",
        )
    finally:
        db.close()

    def fake_stream(*args, **kwargs):
        yield StreamEvent.chunk("partial")
        yield StreamEvent.final(
            ExecutionResult(status="completed", output={"message": "never reached"})
        )

    with patch("app.providers.langchain.LangChainProvider.stream", side_effect=fake_stream):
        generator = stream_execution(settings, ctx, {"message": "hi"})
        first = next(generator)
        assert first.type == "chunk"
        # Simulate the client closing the SSE connection mid-stream.
        generator.close()

    verify = SessionLocal()
    try:
        run = verify.get(Run, ctx.run_id)
        assert run is not None
        assert run.status == "cancelled"
        assert run.error_category == "client_cancelled"
        assert run.completed_at is not None
    finally:
        verify.close()


def test_producer_closes_source_when_already_stopped() -> None:
    """The producer owns the iterator, so it is the one that closes it."""
    pulled: list[str] = []
    closed = threading.Event()

    def source():
        try:
            pulled.append("one")
            yield StreamEvent.chunk("one")
            pulled.append("two")
            yield StreamEvent.chunk("two")
        except GeneratorExit:
            closed.set()
            raise

    stop = threading.Event()
    stop.set()
    out: queue.Queue = queue.Queue()
    _produce(source(), out, stop)

    assert closed.is_set()
    assert pulled == ["one"]


def test_sse_wrapper_closes_source_when_client_disconnects() -> None:
    gate = threading.Event()
    closed = threading.Event()
    pulled: list[str] = []

    def source():
        try:
            pulled.append("one")
            yield StreamEvent.chunk("one")
            pulled.append("two")
            gate.wait(5)
            yield StreamEvent.chunk("two")
            pulled.append("three")
        finally:
            closed.set()

    async def scenario() -> str:
        body = event_stream_response(source(), request=_ConnectedRequest()).body_iterator
        first = await body.__anext__()
        close_task = asyncio.create_task(body.aclose())
        # Let the wrapper's finally set the stop event before the producer is
        # allowed to continue, so the assertion below is deterministic.
        await asyncio.sleep(0.1)
        gate.set()
        await asyncio.wait_for(close_task, 6)
        return first

    first = asyncio.run(scenario())

    assert "event: chunk" in first
    assert closed.wait(2)
    assert pulled == ["one", "two"]


def test_sse_wrapper_streams_to_completion() -> None:
    def source():
        yield StreamEvent.chunk("a")
        yield StreamEvent.final(ExecutionResult(status="completed", output={"message": "a"}))

    async def scenario() -> list[str]:
        response = event_stream_response(source())
        assert response.media_type == "text/event-stream"
        return [chunk async for chunk in response.body_iterator]

    chunks = asyncio.run(scenario())

    assert [chunk.splitlines()[0] for chunk in chunks] == ["event: chunk", "event: final"]
