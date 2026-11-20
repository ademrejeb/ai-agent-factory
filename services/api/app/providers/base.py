from dataclasses import dataclass, field
from typing import Any, Iterator, Protocol


@dataclass
class ConnectivityResult:
    ok: bool
    status: str
    capabilities: dict[str, Any]
    resource_label: str | None = None
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionRequest:
    input: dict[str, Any]
    conversation_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    user: str = "platform"
    timeout_seconds: float = 60.0
    secrets: dict[str, str] = field(default_factory=dict)
    tools: dict[str, dict[str, Any]] = field(default_factory=dict)
    skills: dict[str, dict[str, Any]] = field(default_factory=dict)
    skill_ids: list[str] = field(default_factory=list)
    allow_private_urls: bool = False
    max_http_response_bytes: int = 2_000_000
    settings: Any = None


@dataclass
class ExecutionResult:
    status: str
    output: dict[str, Any]
    provider_run_id: str | None = None
    conversation_id: str | None = None
    token_count: int | None = None
    token_count_is_estimate: bool = False
    error_category: str | None = None
    error_message: str | None = None
    provider_extension: dict[str, Any] = field(default_factory=dict)
    duration_ms: int | None = None


@dataclass
class StreamEvent:
    """One event in a provider stream or a normalized async status update.

    ``type`` is deliberately small and stable:

    * ``chunk``: incremental answer text in ``text``.
    * ``status``: provider progress that is not user-visible answer text.
    * ``final``: the run finished; ``data`` is the normalized execution result.
    * ``error``: the run failed; ``data`` carries message/category.
    """

    type: str
    text: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def chunk(cls, text: str) -> "StreamEvent":
        return cls(type="chunk", text=text)

    @classmethod
    def final(cls, result: ExecutionResult) -> "StreamEvent":
        return cls(
            type="final",
            text=result.output.get("message") if isinstance(result.output, dict) else None,
            data={
                "status": result.status,
                "output": result.output,
                "provider_run_id": result.provider_run_id,
                "conversation_id": result.conversation_id,
                "token_count": result.token_count,
                "token_count_is_estimate": result.token_count_is_estimate,
                "error_category": result.error_category,
                "error_message": result.error_message,
                "provider_extension": result.provider_extension,
            },
        )

    @classmethod
    def error(cls, message: str, category: str = "provider_failed") -> "StreamEvent":
        return cls(type="error", data={"error_category": category, "error_message": message})


class ProviderAdapter(Protocol):
    name: str

    def check_connectivity(
        self,
        *,
        base_url: str,
        credentials: dict[str, Any],
        extra_config: dict[str, Any],
        timeout_seconds: float,
    ) -> ConnectivityResult: ...

    def execute(
        self,
        *,
        base_url: str,
        credentials: dict[str, Any],
        extra_config: dict[str, Any],
        resource_id: str | None,
        request: ExecutionRequest,
    ) -> ExecutionResult: ...

    def get_run(
        self,
        *,
        base_url: str,
        credentials: dict[str, Any],
        extra_config: dict[str, Any],
        resource_id: str | None,
        provider_run_id: str,
        timeout_seconds: float,
    ) -> ExecutionResult: ...


class StreamingAdapter(Protocol):
    """Adapters that expose a synchronous iterator of normalized stream events."""

    def stream(
        self,
        *,
        base_url: str,
        credentials: dict[str, Any],
        extra_config: dict[str, Any],
        resource_id: str | None,
        request: ExecutionRequest,
    ) -> Iterator[StreamEvent]: ...


class AsyncAdapter(Protocol):
    """Adapters that can enqueue a run and expose it through ``get_run``."""

    def start_async(
        self,
        *,
        base_url: str,
        credentials: dict[str, Any],
        extra_config: dict[str, Any],
        resource_id: str | None,
        request: ExecutionRequest,
    ) -> ExecutionResult: ...
