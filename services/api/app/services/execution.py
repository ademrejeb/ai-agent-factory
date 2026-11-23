import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Iterator

from sqlalchemy.orm import Session

from app.config import Settings
from app.db import SessionLocal
from app.errors import AppError
from app.ids import new_id
from app.lifecycle import (
    CONFIGURED,
    EXECUTABLE_GATEWAY,
    EXECUTABLE_TEST,
    MONITORED,
    TESTED,
    VALIDATED,
    transition,
)
from app.models import (
    Agent,
    AgentVersion,
    AgentSecret,
    ApiCredential,
    AuditEvent,
    Deployment,
    LocalGraph,
    ProviderConnection,
    Run,
    Skill,
    Tool,
    UsageEvent,
)
from app.providers.base import ExecutionRequest, ExecutionResult, StreamEvent
from app.providers.registry import get_adapter
from app.security import decrypt_secret
from app.services.langgraph_runtime import graph_from_snapshot
from app.services.knowledge import make_retriever
from app.services.local_graph import GraphValidationError, default_graph, validate_graph
from app.services.agent_settings import normalize_agent_settings

TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled"}

@dataclass
class ExecutionContext:
    """Everything finalization needs, without ORM objects crossing threads."""

    run_id: str
    organization_id: str
    agent_id: str
    provider: str
    connection_id: str
    base_url: str
    credentials: dict[str, Any]
    extra_config: dict[str, Any]
    resource_id: str | None
    deployment_id: str | None
    source: str
    credential_id: str | None
    correlation_id: str
    graph: dict[str, Any] | None = None
    secrets: dict[str, str] = field(default_factory=dict)
    tools: dict[str, dict[str, Any]] = field(default_factory=dict)
    skills: dict[str, dict[str, Any]] = field(default_factory=dict)
    skill_ids: list[str] = field(default_factory=list)
    agent_settings: dict[str, Any] = field(default_factory=dict)
    retrieval: Any = None
    max_message_chars: int = 8_000
    max_extension_bytes: int = 32_000
    metadata: dict[str, Any] = field(default_factory=dict)


def _summarize(payload: dict[str, Any], max_chars: int = 500) -> dict[str, Any]:
    raw = json.dumps(payload, default=str)
    return {
        "bytes": len(raw.encode("utf-8")),
        "preview": raw[:max_chars],
        "truncated": len(raw) > max_chars,
    }


def load_credentials(settings: Settings, conn: ProviderConnection) -> dict[str, Any]:
    raw = decrypt_secret(settings, conn.credentials_encrypted)
    return json.loads(raw)


def latest_deployment(db: Session, agent_id: str) -> Deployment | None:
    return (
        db.query(Deployment)
        .filter(Deployment.agent_id == agent_id)
        .order_by(Deployment.created_at.desc())
        .first()
    )


def draft_graph(db: Session, agent: Agent) -> dict[str, Any] | None:
    row = db.query(LocalGraph).filter(LocalGraph.agent_id == agent.id).first()
    if row is not None:
        try:
            return validate_graph(row.nodes, row.edges)
        except GraphValidationError as exc:
            raise AppError("invalid_graph", exc.message, 409, {"node_id": exc.node_id}) from exc
    if agent.provider == "langchain":
        conn = (
            db.get(ProviderConnection, agent.provider_connection_id)
            if agent.provider_connection_id
            else None
        )
        model = (conn.extra_config or {}).get("model") if conn else None
        return default_graph(model=model if isinstance(model, str) else None)
    return None


def published_graph(db: Session, deployment: Deployment | None) -> dict[str, Any] | None:
    if not deployment or not deployment.version_id:
        return None
    version = db.get(AgentVersion, deployment.version_id)
    return graph_from_snapshot(version.snapshot if version else None)


def resolve_graph(
    db: Session, agent: Agent, source: str, deployment: Deployment | None
) -> dict[str, Any] | None:
    if agent.provider != "langchain":
        return None
    if source == "gateway":
        return published_graph(db, deployment)
    return draft_graph(db, agent)


def runtime_tools(db: Session, settings: Settings, organization_id: str) -> dict[str, dict[str, Any]]:
    from app.services.tools import load_headers

    rows = (
        db.query(Tool)
        .filter(Tool.organization_id == organization_id)
        .order_by(Tool.name.asc())
        .all()
    )
    return {
        row.id: {
            "id": row.id,
            "name": row.name,
            "kind": row.kind,
            "description": row.description,
            "config": dict(row.config or {}),
            "input_schema": dict(row.input_schema or {}),
            "headers": load_headers(settings, row),
            "enabled": bool(row.enabled),
        }
        for row in rows
    }


def runtime_skills(db: Session, organization_id: str) -> dict[str, dict[str, Any]]:
    rows = (
        db.query(Skill)
        .filter(Skill.organization_id == organization_id)
        .order_by(Skill.name.asc())
        .all()
    )
    return {
        row.id: {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "instructions": row.instructions,
        }
        for row in rows
    }


def prepare_execution(
    db: Session,
    settings: Settings,
    *,
    agent: Agent,
    payload: dict[str, Any],
    conversation_id: str | None,
    metadata: dict[str, Any],
    source: str,
    credential: ApiCredential | None,
    correlation_id: str,
    user_label: str,
    idempotency_key: str | None = None,
) -> ExecutionContext:
    if agent.archived_at is not None:
        raise AppError("agent_archived", "Agent is archived.", 409)
    allowed = EXECUTABLE_GATEWAY if source == "gateway" else EXECUTABLE_TEST
    if agent.lifecycle_status not in allowed:
        raise AppError(
            "invalid_lifecycle",
            "Agent is not eligible for this kind of execution.",
            409,
            {"status": agent.lifecycle_status, "source": source},
        )
    if not agent.provider_connection_id or not agent.provider:
        raise AppError("invalid_agent", "Agent has no provider connection.", 400)

    conn = db.get(ProviderConnection, agent.provider_connection_id)
    if not conn or conn.organization_id != agent.organization_id:
        raise AppError("invalid_agent", "Provider connection is missing.", 400)

    deployment = latest_deployment(db, agent.id) if source == "gateway" else None
    if source == "gateway":
        if not deployment or deployment.status != "active":
            raise AppError("not_published", "No active platform deployment for this agent.", 409)
        if deployment.health_status == "unhealthy":
            raise AppError("unhealthy_deployment", "Deployment is marked unhealthy.", 409)

    graph = resolve_graph(db, agent, source, deployment)
    if agent.provider == "langchain" and graph is None:
        raise AppError(
            "invalid_graph",
            "This LangChain agent has no graph. Open the graph editor and save or publish it.",
            409,
        )

    started = datetime.now(UTC)
    run = Run(
        id=new_id("run"),
        organization_id=agent.organization_id,
        agent_id=agent.id,
        deployment_id=deployment.id if deployment else None,
        credential_id=credential.id if credential else None,
        status="running",
        source=source,
        provider=agent.provider,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        input_summary=_summarize(payload),
        output_summary={},
        started_at=started,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    secret_rows = (
        db.query(AgentSecret).filter(AgentSecret.agent_id == agent.id).all()
    )
    secrets = {row.name: decrypt_secret(settings, row.value_encrypted) for row in secret_rows}
    return ExecutionContext(
        run_id=run.id,
        organization_id=agent.organization_id,
        agent_id=agent.id,
        provider=agent.provider,
        connection_id=conn.id,
        base_url=conn.base_url,
        credentials=load_credentials(settings, conn),
        extra_config=dict(conn.extra_config or {}),
        resource_id=agent.provider_resource_id,
        deployment_id=deployment.id if deployment else None,
        source=source,
        credential_id=credential.id if credential else None,
        correlation_id=correlation_id,
        graph=graph,
        secrets=secrets,
        tools=runtime_tools(db, settings, agent.organization_id),
        skills=runtime_skills(db, agent.organization_id),
        skill_ids=[
            str(item)
            for item in (agent.skill_ids or [])
            if isinstance(item, str) and item
        ],
        agent_settings=normalize_agent_settings(agent.settings or {}),
        retrieval=make_retriever(settings, agent.organization_id),
        max_message_chars=settings.gateway_max_message_chars,
        max_extension_bytes=settings.gateway_max_extension_bytes,
        metadata={
            **metadata,
            "conversation_id": conversation_id,
            "user_label": user_label,
            "graph": graph,
        },
    )


def _bounded_text(value: Any, limit: int) -> Any:
    if value is None:
        return None
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    if len(text) <= limit:
        return text
    return text[:limit] + "\n… [truncated]"


def _bounded_extension(extension: Any, limit_bytes: int) -> dict[str, Any]:
    if not isinstance(extension, dict):
        return {}
    raw = json.dumps(extension, default=str)
    if len(raw.encode("utf-8")) <= limit_bytes:
        return extension
    return {
        "truncated": True,
        "bytes": len(raw.encode("utf-8")),
        "preview": raw[:limit_bytes],
    }


def _record_usage(db: Session, ctx: ExecutionContext, *, event_type: str = "agent_run") -> None:
    existing = (
        db.query(UsageEvent)
        .filter(UsageEvent.run_id == ctx.run_id, UsageEvent.event_type == event_type)
        .first()
    )
    if existing:
        return
    db.add(
        UsageEvent(
            id=new_id("uevt"),
            organization_id=ctx.organization_id,
            run_id=ctx.run_id,
            event_type=event_type,
            quantity=1,
            unit="request",
            is_estimate=False,
            created_at=datetime.now(UTC),
        )
    )


def _record_audit(db: Session, ctx: ExecutionContext, *, status: str) -> None:
    exists = (
        db.query(AuditEvent)
        .filter(
            AuditEvent.resource_type == "run",
            AuditEvent.resource_id == ctx.run_id,
            AuditEvent.action == "run.execute",
        )
        .first()
    )
    if exists:
        return
    db.add(
        AuditEvent(
            id=new_id("aud"),
            organization_id=ctx.organization_id,
            actor_user_id=None,
            action="run.execute",
            resource_type="run",
            resource_id=ctx.run_id,
            metadata_json={"source": ctx.source, "status": status},
            created_at=datetime.now(UTC),
        )
    )


def finalize_execution(
    db: Session,
    ctx: ExecutionContext,
    result: ExecutionResult,
) -> Run:
    run = db.get(Run, ctx.run_id)
    if run is None:
        raise AppError("not_found", "Run disappeared during execution.", 500)
    if run.status in TERMINAL_RUN_STATUSES:
        return run

    now = datetime.now(UTC)
    started = run.started_at
    if started is not None:
        if started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        run.duration_ms = max(0, int((now - started).total_seconds() * 1000))
    run.provider_run_id = result.provider_run_id or run.provider_run_id
    run.token_count = result.token_count
    run.token_count_is_estimate = result.token_count_is_estimate

    if result.status in {"queued", "running"}:
        run.status = result.status
        run.output_summary = {
            "provider_extension": _bounded_extension(
                result.provider_extension, ctx.max_extension_bytes
            ),
            "async": True,
        }
        db.commit()
        db.refresh(run)
        return run

    agent = db.get(Agent, ctx.agent_id)
    deployment = db.get(Deployment, ctx.deployment_id) if ctx.deployment_id else None

    if result.status == "completed":
        run.status = "completed"
        run.completed_at = now
        run.output_summary = {
            **_summarize(result.output),
            "message": _bounded_text(result.output.get("message"), ctx.max_message_chars),
            "conversation_id": result.conversation_id,
            "provider_extension": _bounded_extension(
                result.provider_extension, ctx.max_extension_bytes
            ),
        }
        if ctx.source == "test" and agent is not None:
            if agent.lifecycle_status in {CONFIGURED, TESTED}:
                agent.lifecycle_status = transition(agent.lifecycle_status, TESTED)
                agent.lifecycle_status = transition(agent.lifecycle_status, VALIDATED)
        if ctx.source == "gateway" and deployment is not None:
            deployment.health_status = "healthy"
            deployment.last_health_check_at = now
            deployment.last_error = None
            if agent is not None and agent.lifecycle_status != MONITORED:
                agent.lifecycle_status = transition(agent.lifecycle_status, MONITORED)
    elif result.status == "cancelled":
        # The caller dropped the connection. Keep this distinct from a provider
        # failure so dashboards do not blame the model for a client choice.
        run.status = "cancelled"
        run.completed_at = now
        run.error_category = result.error_category or "client_cancelled"
        run.error_message = result.error_message or "The caller cancelled the run."
        run.output_summary = {
            "provider_extension": _bounded_extension(
                result.provider_extension, ctx.max_extension_bytes
            )
        }
    else:
        run.status = "failed"
        run.completed_at = now
        run.error_category = result.error_category or "provider_failed"
        run.error_message = result.error_message or "Provider reported failure."
        run.output_summary = {
            "provider_extension": _bounded_extension(
                result.provider_extension, ctx.max_extension_bytes
            )
        }
        if deployment is not None:
            deployment.health_status = "unhealthy"
            deployment.last_error = run.error_message
            deployment.last_health_check_at = now

    _record_usage(db, ctx)
    _record_audit(db, ctx, status=run.status)
    db.commit()
    db.refresh(run)
    return run


def _error_extension(exc: AppError) -> dict[str, Any]:
    steps = exc.details.get("steps")
    if isinstance(steps, list) and steps:
        return {"langchain": {"steps": steps}}
    return {}


def fail_execution(
    db: Session,
    ctx: ExecutionContext,
    *,
    code: str,
    message: str,
    extension: dict[str, Any] | None = None,
) -> Run:
    return finalize_execution(
        db,
        ctx,
        ExecutionResult(
            status="failed",
            output={},
            error_category=code,
            error_message=message,
            provider_extension=extension or {},
        ),
    )


def _request_for(ctx: ExecutionContext, settings: Settings, payload: dict[str, Any]) -> ExecutionRequest:
    return ExecutionRequest(
        input=payload,
        conversation_id=ctx.metadata.get("conversation_id"),
        metadata=ctx.metadata,
        user=str(ctx.metadata.get("user_label") or "platform"),
        timeout_seconds=settings.gateway_timeout_seconds,
        secrets=ctx.secrets,
        tools=ctx.tools,
        skills=ctx.skills,
        skill_ids=ctx.skill_ids,
        agent_settings=ctx.agent_settings,
        allow_private_urls=settings.private_urls_allowed,
        max_http_response_bytes=settings.http_node_max_response_bytes,
        settings=settings,
        retrieval=ctx.retrieval,
    )


def execute_agent(
    db: Session,
    settings: Settings,
    *,
    agent: Agent,
    payload: dict[str, Any],
    conversation_id: str | None,
    metadata: dict[str, Any],
    source: str,
    credential: ApiCredential | None,
    correlation_id: str,
    user_label: str,
    idempotency_key: str | None = None,
) -> Run:
    ctx = prepare_execution(
        db,
        settings,
        agent=agent,
        payload=payload,
        conversation_id=conversation_id,
        metadata=metadata,
        source=source,
        credential=credential,
        correlation_id=correlation_id,
        user_label=user_label,
        idempotency_key=idempotency_key,
    )
    t0 = time.perf_counter()
    try:
        result = get_adapter(ctx.provider).execute(
            base_url=ctx.base_url,
            credentials=ctx.credentials,
            extra_config=ctx.extra_config,
            resource_id=ctx.resource_id,
            request=_request_for(ctx, settings, payload),
        )
        result.duration_ms = int((time.perf_counter() - t0) * 1000)
    except AppError as exc:
        run = fail_execution(
            db, ctx, code=exc.code, message=exc.message, extension=_error_extension(exc)
        )
        exc.details = {**exc.details, "run_id": run.id}
        raise
    except Exception as exc:  # noqa: BLE001
        run = fail_execution(db, ctx, code="internal_error", message=str(exc) or "Execution failed.")
        raise AppError(
            "internal_error",
            "Execution failed unexpectedly.",
            500,
            {"run_id": run.id},
        ) from exc
    return finalize_execution(db, ctx, result)


def stream_execution(
    settings: Settings,
    ctx: ExecutionContext,
    payload: dict[str, Any],
) -> Iterator[StreamEvent]:
    """Stream a run using a fresh session owned by the streaming thread.

    The request-scoped session must not be used while ``StreamingResponse`` is
    iterating, because the generator runs in a different thread.
    """

    db = SessionLocal()
    try:
        adapter = get_adapter(ctx.provider)
        streamer = getattr(adapter, "stream", None)
        if streamer is None:
            run = fail_execution(
                db,
                ctx,
                code="unsupported_capability",
                message=f"{ctx.provider} streaming is not implemented by this adapter.",
            )
            yield StreamEvent(
                type="error",
                data={
                    "error_category": "unsupported_capability",
                    "error_message": "Streaming is not supported for this provider.",
                    "run_id": run.id,
                },
            )
            return
        final_result: ExecutionResult | None = None
        try:
            for event in streamer(
                base_url=ctx.base_url,
                credentials=ctx.credentials,
                extra_config=ctx.extra_config,
                resource_id=ctx.resource_id,
                request=_request_for(ctx, settings, payload),
            ):
                if event.type == "final":
                    final_result = ExecutionResult(
                        status=event.data.get("status") or "completed",
                        output=event.data.get("output") or {},
                        provider_run_id=event.data.get("provider_run_id"),
                        conversation_id=event.data.get("conversation_id"),
                        token_count=event.data.get("token_count"),
                        token_count_is_estimate=bool(
                            event.data.get("token_count_is_estimate")
                        ),
                        error_category=event.data.get("error_category"),
                        error_message=event.data.get("error_message"),
                        provider_extension=event.data.get("provider_extension") or {},
                    )
                    run = finalize_execution(db, ctx, final_result)
                    yield StreamEvent(
                        type="final",
                        text=event.text,
                        data={**event.data, "run_id": run.id, "status": run.status},
                    )
                elif event.type == "error":
                    run = fail_execution(
                        db,
                        ctx,
                        code=str(event.data.get("error_category") or "provider_failed"),
                        message=str(event.data.get("error_message") or "Provider stream failed."),
                    )
                    yield StreamEvent(
                        type="error",
                        data={**event.data, "run_id": run.id},
                    )
                    return
                else:
                    yield event
        except GeneratorExit:
            # Starlette closes the iterator when the client disconnects. Record
            # the terminal state instead of leaving the run stuck in ``running``.
            finalize_execution(
                db,
                ctx,
                ExecutionResult(
                    status="cancelled",
                    output={},
                    error_category="client_cancelled",
                    error_message="The caller closed the stream before it finished.",
                ),
            )
            raise
        except AppError as exc:
            run = fail_execution(
                db, ctx, code=exc.code, message=exc.message, extension=_error_extension(exc)
            )
            yield StreamEvent(
                type="error",
                data={
                    "error_category": exc.code,
                    "error_message": exc.message,
                    "run_id": run.id,
                },
            )
            return
        except Exception as exc:  # noqa: BLE001
            run = fail_execution(
                db, ctx, code="internal_error", message=str(exc) or "Stream failed."
            )
            yield StreamEvent(
                type="error",
                data={
                    "error_category": "internal_error",
                    "error_message": "Streaming failed unexpectedly.",
                    "run_id": run.id,
                },
            )
            return
        if final_result is None:
            run = fail_execution(
                db,
                ctx,
                code="provider_failed",
                message="Provider stream ended without a final result.",
            )
            yield StreamEvent(
                type="error",
                data={
                    "error_category": "provider_failed",
                    "error_message": "Provider stream ended without a final result.",
                    "run_id": run.id,
                },
            )
    finally:
        db.close()


def start_async_agent(
    db: Session,
    settings: Settings,
    *,
    agent: Agent,
    payload: dict[str, Any],
    conversation_id: str | None,
    metadata: dict[str, Any],
    source: str,
    credential: ApiCredential | None,
    correlation_id: str,
    user_label: str,
    idempotency_key: str | None = None,
) -> Run:
    ctx = prepare_execution(
        db,
        settings,
        agent=agent,
        payload=payload,
        conversation_id=conversation_id,
        metadata=metadata,
        source=source,
        credential=credential,
        correlation_id=correlation_id,
        user_label=user_label,
        idempotency_key=idempotency_key,
    )
    adapter = get_adapter(ctx.provider)
    starter = getattr(adapter, "start_async", None)
    if starter is None:
        fail_execution(
            db,
            ctx,
            code="unsupported_capability",
            message=f"{ctx.provider} asynchronous runs are not supported.",
        )
        raise AppError(
            "unsupported_capability",
            f"{ctx.provider} asynchronous runs are not supported.",
            409,
            {"run_id": ctx.run_id},
        )
    try:
        result = starter(
            base_url=ctx.base_url,
            credentials=ctx.credentials,
            extra_config=ctx.extra_config,
            resource_id=ctx.resource_id,
            request=_request_for(ctx, settings, payload),
        )
    except AppError as exc:
        run = fail_execution(
            db, ctx, code=exc.code, message=exc.message, extension=_error_extension(exc)
        )
        exc.details = {**exc.details, "run_id": run.id}
        raise
    run = finalize_execution(db, ctx, result)
    _record_usage(db, ctx, event_type="agent_run_enqueued")
    db.commit()
    db.refresh(run)
    return run


def refresh_run(db: Session, settings: Settings, run: Run) -> Run:
    """Pull the provider state for a queued/running async run."""

    if run.status in TERMINAL_RUN_STATUSES or not run.provider_run_id:
        return run
    agent = db.get(Agent, run.agent_id)
    if agent is None or not agent.provider_connection_id:
        return run
    conn = db.get(ProviderConnection, agent.provider_connection_id)
    if conn is None:
        return run
    adapter = get_adapter(agent.provider)
    ctx = ExecutionContext(
        run_id=run.id,
        organization_id=run.organization_id,
        agent_id=agent.id,
        provider=agent.provider or conn.provider,
        connection_id=conn.id,
        base_url=conn.base_url,
        credentials=load_credentials(settings, conn),
        extra_config=dict(conn.extra_config or {}),
        resource_id=agent.provider_resource_id,
        deployment_id=run.deployment_id,
        source=run.source,
        credential_id=run.credential_id,
        correlation_id=run.correlation_id,
        graph=published_graph(db, db.get(Deployment, run.deployment_id))
        if run.deployment_id
        else None,
        metadata={"conversation_id": None},
    )
    try:
        result = adapter.get_run(
            base_url=ctx.base_url,
            credentials=ctx.credentials,
            extra_config=ctx.extra_config,
            resource_id=ctx.resource_id,
            provider_run_id=run.provider_run_id,
            timeout_seconds=min(settings.gateway_timeout_seconds, 20),
        )
    except AppError as exc:
        run.error_message = exc.message
        db.commit()
        db.refresh(run)
        return run
    _record_usage(db, ctx)
    return finalize_execution(db, ctx, result)


def get_idempotent_run(
    db: Session, *, credential_id: str, agent_id: str, key: str
) -> Run | None:
    return (
        db.query(Run)
        .filter(
            Run.credential_id == credential_id,
            Run.agent_id == agent_id,
            Run.idempotency_key == key,
        )
        .first()
    )
