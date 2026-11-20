from unittest.mock import MagicMock, patch

from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.providers.base import ExecutionRequest
from app.providers.langchain import LangChainProvider
from app.services.local_graph import default_graph


def _models_response(payload: dict, status_code: int = 200) -> MagicMock:
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = payload
    return mock


def _factory(*, model, temperature, max_tokens, streaming):
    return FakeListChatModel(responses=["adapter answer"])


def test_connectivity_requires_a_model() -> None:
    result = LangChainProvider().check_connectivity(
        base_url="http://example.test/v1",
        credentials={"api_key": "k"},
        extra_config={},
        timeout_seconds=5,
    )
    assert result.ok is False
    assert result.details["code"] == "model_required"


def test_connectivity_checks_real_model_list() -> None:
    response = _models_response({"data": [{"id": "gpt-4o-mini"}, {"id": "other"}]})
    with patch("app.providers.langchain.request_json", return_value=response):
        result = LangChainProvider().check_connectivity(
            base_url="http://example.test/v1",
            credentials={"api_key": "k"},
            extra_config={"model": "gpt-4o-mini"},
            timeout_seconds=5,
        )
    assert result.ok is True
    assert result.status == "connected"
    assert result.details["model_listed"] is True
    assert result.capabilities["streaming"] is True


def test_connectivity_warns_when_model_is_not_listed() -> None:
    response = _models_response({"data": [{"id": "other"}]})
    with patch("app.providers.langchain.request_json", return_value=response):
        result = LangChainProvider().check_connectivity(
            base_url="http://example.test/v1",
            credentials={"api_key": "k"},
            extra_config={"model": "custom"},
            timeout_seconds=5,
        )
    assert result.ok is True
    assert result.details["model_listed"] is False
    assert "not in the model list" in result.details["warning"]


def test_execute_runs_the_published_graph() -> None:
    graph = default_graph(model="test-model")
    result = LangChainProvider().execute(
        base_url="http://example.test/v1",
        credentials={"api_key": "k"},
        extra_config={"model": "test-model"},
        resource_id=None,
        request=ExecutionRequest(
            input={"message": "hello"},
            metadata={"graph": graph},
        ),
        model_factory=_factory,
    )
    assert result.status == "completed"
    assert result.output["message"] == "adapter answer"
    assert result.provider_extension["langchain"]["steps"][-1]["type"] == "output"


def test_execute_requires_a_graph_snapshot() -> None:
    try:
        LangChainProvider().execute(
            base_url="http://example.test/v1",
            credentials={"api_key": "k"},
            extra_config={"model": "test-model"},
            resource_id=None,
            request=ExecutionRequest(input={"message": "hello"}),
            model_factory=_factory,
        )
    except Exception as exc:  # AppError
        assert getattr(exc, "code", None) == "invalid_graph"
    else:  # pragma: no cover
        raise AssertionError("missing graph was accepted")


def test_stream_yields_final_event() -> None:
    graph = default_graph(model="test-model")
    events = list(
        LangChainProvider().stream(
            base_url="http://example.test/v1",
            credentials={"api_key": "k"},
            extra_config={"model": "test-model"},
            resource_id=None,
            request=ExecutionRequest(
                input={"message": "hello"},
                metadata={"graph": graph},
            ),
            model_factory=_factory,
        )
    )
    assert events[-1].type == "final"
    assert events[-1].data["status"] == "completed"
