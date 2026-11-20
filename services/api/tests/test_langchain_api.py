from unittest.mock import patch

from fastapi.testclient import TestClient

from app.providers.base import ConnectivityResult, ExecutionResult
from app.services.local_graph import default_graph


def _langchain_ok() -> ConnectivityResult:
    return ConnectivityResult(
        ok=True,
        status="connected",
        capabilities={"execute": True, "streaming": True, "graph": True},
        resource_label="test-model",
        details={"model": "test-model", "model_listed": True},
    )


def _exec_ok() -> ExecutionResult:
    return ExecutionResult(
        status="completed",
        output={"message": "graph answer"},
        token_count=5,
        provider_extension={"langchain": {"steps": []}},
    )


def _make_langchain_agent(client: TestClient, ws_id: str) -> tuple[dict, dict]:
    conn = client.post(
        "/api/v1/provider-connections",
        json={
            "provider": "langchain",
            "name": "Local OpenAI-compatible",
            "base_url": "http://localhost:11434/v1",
            "api_key": "test-key",
            "model": "test-model",
        },
    )
    assert conn.status_code == 200, conn.text
    agent = client.post(
        "/api/v1/agents",
        json={"workspace_id": ws_id, "name": "Graph agent"},
    ).json()
    linked = client.post(
        f"/api/v1/agents/{agent['id']}/link",
        json={"provider_connection_id": conn.json()["id"]},
    )
    assert linked.status_code == 200, linked.text
    return conn.json(), linked.json()


def test_langchain_link_creates_a_default_graph(client: TestClient, user_a: dict) -> None:
    ws = client.get("/api/v1/workspaces").json()["items"][0]
    with patch(
        "app.providers.langchain.LangChainProvider.check_connectivity",
        return_value=_langchain_ok(),
    ):
        conn, agent = _make_langchain_agent(client, ws["id"])
    assert conn["extra_config"]["model"] == "test-model"
    assert agent["provider"] == "langchain"

    graph = client.get(f"/api/v1/agents/{agent['id']}/graph")
    assert graph.status_code == 200, graph.text
    body = graph.json()
    assert body["revision"] == 1
    assert body["graph"]["nodes"]["input"]["type"] == "input"
    assert body["graph"]["nodes"]["output"]["type"] == "output"


def test_graph_save_validate_and_publish_snapshot(client: TestClient, user_a: dict) -> None:
    ws = client.get("/api/v1/workspaces").json()["items"][0]
    with patch(
        "app.providers.langchain.LangChainProvider.check_connectivity",
        return_value=_langchain_ok(),
    ):
        _, agent = _make_langchain_agent(client, ws["id"])

    graph = default_graph(model="test-model")
    graph["nodes"]["answer"]["name"] = "Answer v2"
    graph["nodes"]["answer"]["config"]["system"] = "Be precise."

    invalid = client.post(
        f"/api/v1/agents/{agent['id']}/graph/validate",
        json={"nodes": {}, "edges": []},
    )
    assert invalid.status_code == 200
    assert invalid.json()["valid"] is False

    valid = client.post(
        f"/api/v1/agents/{agent['id']}/graph/validate",
        json=graph,
    )
    assert valid.status_code == 200
    assert valid.json()["valid"] is True

    saved = client.put(f"/api/v1/agents/{agent['id']}/graph", json=graph)
    assert saved.status_code == 200, saved.text
    assert saved.json()["revision"] == 2

    with patch("app.providers.langchain.LangChainProvider.execute", return_value=_exec_ok()):
        dry = client.post(
            f"/api/v1/agents/{agent['id']}/graph/dry_run",
            json={"input": {"message": "hello"}},
        )
    assert dry.status_code == 200, dry.text
    assert dry.json()["run"]["status"] == "completed"
    assert dry.json()["run"]["output"]["message"] == "graph answer"

    published = client.post(f"/api/v1/agents/{agent['id']}/publish")
    assert published.status_code == 200, published.text

    versions = client.get(f"/api/v1/agents/{agent['id']}/versions").json()["items"]
    snapshot = versions[0]["snapshot"]
    assert snapshot["graph"]["revision"] == 2
    assert snapshot["graph"]["nodes"]["answer"]["name"] == "Answer v2"


def test_gateway_uses_published_graph_not_draft(client: TestClient, user_a: dict) -> None:
    ws = client.get("/api/v1/workspaces").json()["items"][0]
    with patch(
        "app.providers.langchain.LangChainProvider.check_connectivity",
        return_value=_langchain_ok(),
    ):
        _, agent = _make_langchain_agent(client, ws["id"])

    with patch("app.providers.langchain.LangChainProvider.execute", return_value=_exec_ok()):
        client.post(
            f"/api/v1/agents/{agent['id']}/test",
            json={"input": {"message": "warm up"}},
        )
    published = client.post(f"/api/v1/agents/{agent['id']}/publish")
    assert published.status_code == 200, published.text

    # Change the draft after publishing. The gateway must still see revision 1.
    draft = default_graph(model="test-model")
    draft["nodes"]["answer"]["name"] = "Draft changed"
    saved = client.put(f"/api/v1/agents/{agent['id']}/graph", json=draft)
    assert saved.status_code == 200

    captured: dict = {}

    def fake_execute(*args, **kwargs):
        captured.update(kwargs["request"].metadata["graph"])
        return _exec_ok()

    secret = client.post("/api/v1/credentials", json={"name": "graph-gw"}).json()["secret"]
    with patch(
        "app.providers.langchain.LangChainProvider.execute", side_effect=fake_execute
    ):
        gateway = client.post(
            f"/api/v1/agents/{agent['id']}/runs",
            json={"input": {"message": "hello"}},
            headers={"Authorization": f"Bearer {secret}"},
        )
    assert gateway.status_code == 200, gateway.text
    assert captured["nodes"]["answer"]["name"] == "Answer with the model"
    assert captured["edges"]


def test_graph_editor_rejects_non_langchain_agent(client: TestClient, user_a: dict) -> None:
    ws = client.get("/api/v1/workspaces").json()["items"][0]
    agent = client.post(
        "/api/v1/agents",
        json={"workspace_id": ws["id"], "name": "Unlinked"},
    ).json()
    response = client.get(f"/api/v1/agents/{agent['id']}/graph")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "unsupported_capability"
