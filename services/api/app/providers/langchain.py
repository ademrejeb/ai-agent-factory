"""LangChain/LangGraph provider adapter.

Unlike Dify and Sim, this provider does not host the workflow. The control
plane owns a small graph and executes it with real LangChain chat models
against any OpenAI-compatible endpoint (OpenAI, Ollama, LM Studio, vLLM, or a
compatible gateway).

Connectivity is a real credential/resource check: ``GET {base_url}/models``
with the supplied key. A model name is required because an OpenAI-compatible
endpoint cannot infer which model a graph should call.
"""

from __future__ import annotations

from typing import Any, Iterator

from app.errors import AppError
from app.providers.base import (
    ConnectivityResult,
    ExecutionRequest,
    ExecutionResult,
    StreamEvent,
)
from app.providers.http import provider_http_error, request_json
from app.services.langgraph_runtime import LangGraphRuntime
from app.services.local_graph import GraphRuntimeError, GraphValidationError


class LangChainProvider:
    name = "langchain"

    def _headers(self, credentials: dict[str, Any]) -> dict[str, str]:
        key = credentials.get("api_key")
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    def _root(self, base_url: str) -> str:
        return base_url.rstrip("/")

    def _model(self, extra_config: dict[str, Any]) -> str:
        model = extra_config.get("model")
        if not isinstance(model, str) or not model.strip():
            raise AppError(
                "invalid_connection",
                "A model name is required for a LangChain connection.",
                400,
                {"field": "model"},
            )
        return model.strip()

    def check_connectivity(
        self,
        *,
        base_url: str,
        credentials: dict[str, Any],
        extra_config: dict[str, Any],
        timeout_seconds: float,
    ) -> ConnectivityResult:
        model = extra_config.get("model")
        if not isinstance(model, str) or not model.strip():
            return ConnectivityResult(
                ok=False,
                status="error",
                capabilities={"execute": False, "streaming": False, "graph": True},
                error="A model name is required before checking this connection.",
                details={"code": "model_required", "field": "model"},
            )
        model = model.strip()
        url = f"{self._root(base_url)}/models"
        response = request_json(
            "GET",
            url,
            headers=self._headers(credentials),
            timeout=timeout_seconds,
            provider=self.name,
        )
        if response.status_code >= 400:
            err = provider_http_error(self.name, response)
            return ConnectivityResult(
                ok=False,
                status="error",
                capabilities={"execute": False, "streaming": False, "graph": True},
                error=(
                    f"GET /models returned HTTP {response.status_code}. "
                    "Check the base URL (it usually includes /v1) and the API key."
                ),
                details=err.details,
            )
        try:
            body = response.json()
        except ValueError:
            return ConnectivityResult(
                ok=False,
                status="error",
                capabilities={"execute": False, "streaming": False, "graph": True},
                error="GET /models did not return JSON. Is this an OpenAI-compatible endpoint?",
                details={},
            )
        rows = body.get("data") if isinstance(body, dict) else None
        ids = [
            str(row.get("id"))
            for row in (rows or [])
            if isinstance(row, dict) and row.get("id")
        ]
        listed = model in ids
        capabilities = {
            "execute": True,
            "blocking": True,
            "streaming": True,
            "graph": True,
            "run_lookup": False,
            "resource_creation": "platform_owned",
            "resource_listing": "platform_owned",
            "visual_authoring": True,
        }
        details: dict[str, Any] = {
            "model": model,
            "model_listed": listed,
            "model_count": len(ids),
            "models_sample": ids[:25],
        }
        if ids and not listed:
            details["warning"] = (
                f"'{model}' is not in the model list returned by /models. "
                "The endpoint may still accept it; execution will verify."
            )
        return ConnectivityResult(
            ok=True,
            status="connected",
            capabilities=capabilities,
            resource_label=model,
            details=details,
        )

    def list_resources(
        self,
        *,
        base_url: str,
        credentials: dict[str, Any],
        extra_config: dict[str, Any],
        timeout_seconds: float,
    ) -> list[dict[str, Any]]:
        model = self._model(extra_config)
        return [
            {
                "id": None,
                "name": model,
                "kind": "graph",
                "description": "Platform-owned LangGraph definition executed by LangChain.",
            }
        ]

    def _runtime(
        self,
        *,
        base_url: str,
        credentials: dict[str, Any],
        extra_config: dict[str, Any],
        streaming: bool,
        model_factory: Any = None,
        http_client: Any = None,
        request: ExecutionRequest | None = None,
    ) -> LangGraphRuntime:
        model = self._model(extra_config)
        return LangGraphRuntime(
            model=model,
            # Local OpenAI-compatible servers (Ollama, LM Studio) accept any
            # bearer value but the client library requires a non-empty string.
            api_key=credentials.get("api_key") or "ollama",
            base_url=base_url,
            default_temperature=extra_config.get("temperature"),
            default_max_tokens=extra_config.get("max_tokens"),
            model_factory=model_factory,
            http_client=http_client,
            streaming=streaming,
            secrets=request.secrets if request else None,
            tools=request.tools if request else None,
            skills=request.skills if request else None,
            default_skill_ids=request.skill_ids if request else None,
            allow_private_urls=request.allow_private_urls if request else False,
            max_http_response_bytes=(
                request.max_http_response_bytes if request else 2_000_000
            ),
            settings=request.settings if request else None,
        )

    def _graph(self, request: ExecutionRequest) -> dict[str, Any]:
        graph = request.metadata.get("graph")
        if not isinstance(graph, dict):
            raise AppError(
                "invalid_graph",
                "This agent has no graph snapshot. Open the graph editor and publish again.",
                400,
            )
        return graph

    def execute(
        self,
        *,
        base_url: str,
        credentials: dict[str, Any],
        extra_config: dict[str, Any],
        resource_id: str | None,
        request: ExecutionRequest,
        model_factory: Any = None,
        http_client: Any = None,
    ) -> ExecutionResult:
        runtime = self._runtime(
            base_url=base_url,
            credentials=credentials,
            extra_config=extra_config,
            streaming=False,
            model_factory=model_factory,
            http_client=http_client,
            request=request,
        )
        try:
            result = runtime.run(self._graph(request), request.input)
        except GraphValidationError as exc:
            raise AppError("invalid_graph", exc.message, 400, {"node_id": exc.node_id}) from exc
        except GraphRuntimeError as exc:
            raise AppError(
                "graph_failed",
                exc.message,
                502,
                {"node_id": exc.node_id, "steps": exc.steps},
            ) from exc
        return ExecutionResult(
            status="completed",
            output=result.output,
            token_count=result.token_count,
            provider_extension={
                "langchain": {"steps": result.steps, "values": result.values}
            },
        )

    def stream(
        self,
        *,
        base_url: str,
        credentials: dict[str, Any],
        extra_config: dict[str, Any],
        resource_id: str | None,
        request: ExecutionRequest,
        model_factory: Any = None,
        http_client: Any = None,
    ) -> Iterator[StreamEvent]:
        runtime = self._runtime(
            base_url=base_url,
            credentials=credentials,
            extra_config=extra_config,
            streaming=True,
            model_factory=model_factory,
            http_client=http_client,
            request=request,
        )
        yield from runtime.stream(self._graph(request), request.input)

    def start_async(
        self,
        *,
        base_url: str,
        credentials: dict[str, Any],
        extra_config: dict[str, Any],
        resource_id: str | None,
        request: ExecutionRequest,
    ) -> ExecutionResult:
        raise AppError(
            "unsupported_capability",
            "LangChain graph execution is synchronous; asynchronous runs are not supported.",
            409,
        )
