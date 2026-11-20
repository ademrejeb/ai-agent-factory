"""Tests for the platform-owned LangGraph runtime.

These exercise the exact runtime used in production with an injected chat model
and HTTP transport, so no network access or paid tokens are required.
"""

import httpx
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.services.langgraph_runtime import LangGraphRuntime
from app.services.local_graph import (
    GraphRuntimeError,
    GraphValidationError,
    default_graph,
    validate_graph,
)


def _model_factory(*, model, temperature, max_tokens, streaming):
    return FakeListChatModel(responses=["model answer"])


def _basic_graph() -> dict:
    return {
        "nodes": {
            "input": {
                "id": "input",
                "type": "input",
                "name": "Input",
                "position": {"x": 0, "y": 0},
                "config": {
                    "fields": [
                        {"name": "message", "type": "string", "required": True},
                    ]
                },
            },
            "answer": {
                "id": "answer",
                "type": "llm",
                "name": "Answer",
                "position": {"x": 1, "y": 0},
                "config": {
                    "prompt": "{{ message }}",
                    "system": "Be concise.",
                    "output_key": "answer",
                },
            },
            "out": {
                "id": "out",
                "type": "output",
                "name": "Output",
                "position": {"x": 2, "y": 0},
                "config": {"path": "answer"},
            },
        },
        "edges": [
            {"id": "e1", "source": "input", "target": "answer", "sourceHandle": None},
            {"id": "e2", "source": "answer", "target": "out", "sourceHandle": None},
        ],
    }


def test_runtime_executes_llm_and_output() -> None:
    runtime = LangGraphRuntime(
        model="test-model",
        api_key="test-key",
        base_url="http://example.test/v1",
        model_factory=_model_factory,
    )
    result = runtime.run(_basic_graph(), {"message": "hello"})
    assert result.status == "completed"
    assert result.output["message"] == "model answer"
    assert [step["node"] for step in result.steps] == ["input", "answer", "out"]


def test_runtime_condition_routes_to_separate_outputs() -> None:
    graph = {
        "nodes": {
            "input": {
                "id": "input",
                "type": "input",
                "name": "Input",
                "position": {"x": 0, "y": 0},
                "config": {
                    "fields": [
                        {"name": "flag", "type": "boolean", "required": True},
                        {"name": "message", "type": "string", "required": True},
                    ]
                },
            },
            "cond": {
                "id": "cond",
                "type": "condition",
                "name": "Flag?",
                "position": {"x": 1, "y": 0},
                "config": {"path": "flag", "operator": "truthy"},
            },
            "yes": {
                "id": "yes",
                "type": "http",
                "name": "Yes",
                "position": {"x": 2, "y": 0},
                "config": {
                    "method": "POST",
                    "url": "https://api.example.test/echo",
                    "headers": {"X-Test": "{{ message }}"},
                    "body": {"q": "{{ message }}"},
                    "output_key": "resp",
                },
            },
            "no": {
                "id": "no",
                "type": "llm",
                "name": "No",
                "position": {"x": 2, "y": 1},
                "config": {"prompt": "{{ message }}", "output_key": "answer"},
            },
            "out_yes": {
                "id": "out_yes",
                "type": "output",
                "name": "Yes out",
                "position": {"x": 3, "y": 0},
                "config": {"path": "resp"},
            },
            "out_no": {
                "id": "out_no",
                "type": "output",
                "name": "No out",
                "position": {"x": 3, "y": 1},
                "config": {"path": "answer"},
            },
        },
        "edges": [
            {"id": "e1", "source": "input", "target": "cond", "sourceHandle": None},
            {"id": "e2", "source": "cond", "target": "yes", "sourceHandle": "true"},
            {"id": "e3", "source": "cond", "target": "no", "sourceHandle": "false"},
            {"id": "e4", "source": "yes", "target": "out_yes", "sourceHandle": None},
            {"id": "e5", "source": "no", "target": "out_no", "sourceHandle": None},
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Test"] == "hello"
        return httpx.Response(200, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    runtime = LangGraphRuntime(
        model="test-model",
        api_key="test-key",
        base_url="http://example.test/v1",
        model_factory=_model_factory,
        http_client=client,
    )
    yes = runtime.run(graph, {"flag": True, "message": "hello"})
    no = runtime.run(graph, {"flag": False, "message": "hello"})
    assert [step["node"] for step in yes.steps] == ["input", "cond", "yes", "out_yes"]
    assert [step["node"] for step in no.steps] == ["input", "cond", "no", "out_no"]
    assert yes.output["ok"] is True
    assert no.output["message"] == "model answer"


def test_runtime_rejects_missing_required_input() -> None:
    runtime = LangGraphRuntime(
        model="test-model",
        api_key="test-key",
        base_url="http://example.test/v1",
        model_factory=_model_factory,
    )
    try:
        runtime.run(_basic_graph(), {})
    except Exception as exc:  # GraphRuntimeError is wrapped by LangGraph
        assert "required" in str(exc)
    else:  # pragma: no cover - the graph must reject this
        raise AssertionError("missing required input was accepted")


def test_runtime_streams_single_chunk_for_non_streaming_model() -> None:
    runtime = LangGraphRuntime(
        model="test-model",
        api_key="test-key",
        base_url="http://example.test/v1",
        model_factory=_model_factory,
    )
    events = list(runtime.stream(_basic_graph(), {"message": "hello"}))
    assert events[0].type == "chunk"
    assert events[0].text == "model answer"
    assert events[-1].type == "final"
    assert events[-1].data["output"]["message"] == "model answer"


def test_validation_rejects_cycles_and_merges() -> None:
    graph = default_graph(model="test-model")
    graph["nodes"]["answer"]["config"]["prompt"] = "{{ message }}"
    # A second incoming edge to the LLM node is a merge and must be rejected.
    graph["edges"].append(
        {"id": "e_dup", "source": "output", "target": "answer", "sourceHandle": None}
    )
    try:
        validate_graph(graph["nodes"], graph["edges"])
    except GraphValidationError as exc:
        assert "output" in exc.message or "incoming" in exc.message or "terminal" in exc.message
    else:  # pragma: no cover
        raise AssertionError("merge was accepted")


def _agent_graph(*, tools=("tool1",), skills=()) -> dict:
    return {
        "nodes": {
            "input": {
                "id": "input",
                "type": "input",
                "name": "Input",
                "position": {"x": 0, "y": 0},
                "config": {"fields": [{"name": "message", "type": "string", "required": True}]},
            },
            "agent": {
                "id": "agent",
                "type": "agent",
                "name": "Agent",
                "position": {"x": 1, "y": 0},
                "config": {
                    "prompt": "{{ message }}",
                    "system": "Use the tool.",
                    "tool_ids": list(tools),
                    "skill_ids": list(skills),
                    "max_steps": 3,
                    "output_key": "answer",
                },
            },
            "check": {
                "id": "check",
                "type": "guardrail",
                "name": "Check",
                "position": {"x": 2, "y": 0},
                "config": {
                    "path": "answer",
                    "max_chars": 100,
                    "require_terms": ["final"],
                },
            },
            "out": {
                "id": "out",
                "type": "output",
                "name": "Output",
                "position": {"x": 3, "y": 0},
                "config": {"path": "answer"},
            },
            "blocked": {
                "id": "blocked",
                "type": "output",
                "name": "Blocked",
                "position": {"x": 3, "y": 1},
                "config": {"template": "blocked"},
            },
        },
        "edges": [
            {"id": "e1", "source": "input", "target": "agent", "sourceHandle": None},
            {"id": "e2", "source": "agent", "target": "check", "sourceHandle": None},
            {"id": "e3", "source": "check", "target": "out", "sourceHandle": "pass"},
            {"id": "e4", "source": "check", "target": "blocked", "sourceHandle": "fail"},
        ],
    }


class _ToolCallingModel:
    def __init__(self) -> None:
        self.calls = 0

    def bind_tools(self, specs):  # noqa: ANN001
        self.specs = specs
        return self

    def invoke(self, messages, config=None):  # noqa: ANN001
        from langchain_core.messages import AIMessage

        self.calls += 1
        if self.calls == 1:
            return AIMessage(
                content="",
                tool_calls=[{"name": "tool1", "args": {"q": "x"}, "id": "c1"}],
            )
        return AIMessage(content="final answer")


def test_agent_node_calls_tool_and_guardrail_routes() -> None:
    model = _ToolCallingModel()
    runtime = LangGraphRuntime(
        model="test-model",
        api_key="test-key",
        base_url="http://example.test/v1",
        model_factory=lambda **_: model,
        tools={
            "tool1": {
                "id": "tool1",
                "name": "Tool one",
                "kind": "http",
                "description": "Does a thing",
                "config": {},
                "input_schema": {"type": "object", "properties": {}},
                "enabled": True,
            }
        },
        skills={"skill1": {"id": "skill1", "name": "Safety", "instructions": "Be safe."}},
        tool_runner=lambda tool_id, args: {"ok": tool_id, "args": args},
    )
    result = runtime.run(_agent_graph(tools=("tool1",), skills=("skill1",)), {"message": "go"})
    assert result.output["message"] == "final answer"
    assert any(step.get("type") == "tool_call" for step in result.steps)
    assert any(step.get("type") == "guardrail" and step.get("passed") for step in result.steps)


def test_guardrail_fail_branch_is_reachable() -> None:
    runtime = LangGraphRuntime(
        model="test-model",
        api_key="test-key",
        base_url="http://example.test/v1",
        model_factory=_model_factory,
        tools={},
    )
    graph = _agent_graph(tools=())
    # The fake model returns "model answer", which lacks the required "final" term.
    result = runtime.run(graph, {"message": "go"})
    assert result.output["message"] == "blocked"


def test_failed_tool_keeps_completed_steps() -> None:
    def broken_runner(tool_id, args):
        raise GraphRuntimeError("tool down")

    runtime = LangGraphRuntime(
        model="test-model",
        api_key="test-key",
        base_url="http://example.test/v1",
        model_factory=lambda **_: _ToolCallingModel(),
        tools={
            "tool1": {
                "id": "tool1",
                "name": "Tool one",
                "kind": "http",
                "config": {},
                "input_schema": {"type": "object", "properties": {}},
                "enabled": True,
            }
        },
        tool_runner=broken_runner,
    )
    graph = {
        "nodes": {
            "input": {
                "id": "input",
                "type": "input",
                "name": "Input",
                "position": {"x": 0, "y": 0},
                "config": {"fields": [{"name": "message", "type": "string", "required": True}]},
            },
            "call": {
                "id": "call",
                "type": "tool",
                "name": "Call",
                "position": {"x": 1, "y": 0},
                "config": {"tool_id": "tool1", "arguments": {}, "output_key": "result"},
            },
            "out": {
                "id": "out",
                "type": "output",
                "name": "Output",
                "position": {"x": 2, "y": 0},
                "config": {"path": "result"},
            },
        },
        "edges": [
            {"id": "e1", "source": "input", "target": "call", "sourceHandle": None},
            {"id": "e2", "source": "call", "target": "out", "sourceHandle": None},
        ],
    }
    try:
        runtime.run(graph, {"message": "go"})
    except GraphRuntimeError as exc:
        assert exc.message == "tool down"
        assert any(step.get("node") == "call" and step.get("error") for step in exc.steps)
    else:
        raise AssertionError("expected a runtime failure")
