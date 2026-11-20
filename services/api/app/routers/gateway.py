from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.deps import customer_credential
from app.errors import AppError
from app.ids import new_id
from app.models import Agent, ApiCredential, Run
from app.providers.base import StreamEvent
from app.schemas import RunRequest
from app.services.execution import (
    execute_agent,
    latest_deployment,
    get_idempotent_run,
    prepare_execution,
    start_async_agent,
    stream_execution,
)
from app.services.limiter import enforce_rate_limit
from app.services.sse import event_stream_response

router = APIRouter(tags=["gateway"])


def _gateway_response(run: Run) -> dict:
    """Stable customer-facing shape for both fresh runs and idempotent replays."""
    output = run.output_summary or {}
    return {
        "run_id": run.id,
        "agent_id": run.agent_id,
        "status": run.status,
        "correlation_id": run.correlation_id,
        "provider_run_id": run.provider_run_id,
        "output": {
            "message": output.get("message"),
            "conversation_id": output.get("conversation_id"),
        },
        "provider_extension": output.get("provider_extension") or {},
        "duration_ms": run.duration_ms,
        "error_category": run.error_category,
        "error_message": run.error_message,
    }


def _require_agent(db: Session, cred: ApiCredential, agent_id: str) -> Agent:
    agent = db.get(Agent, agent_id)
    if not agent or agent.organization_id != cred.organization_id:
        raise AppError("not_found", "Agent not found.", 404)
    return agent


def _idempotency_key(request: Request) -> str | None:
    value = request.headers.get("idempotency-key")
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    if len(value) > 200:
        raise AppError("invalid_request", "Idempotency-Key is too long.", 400)
    return value


def _idempotent_run(
    db: Session, cred: ApiCredential, agent_id: str, idem: str | None
) -> Run | None:
    if not idem:
        return None
    existing = get_idempotent_run(
        db, credential_id=cred.id, agent_id=agent_id, key=idem
    )
    if existing and existing.organization_id == cred.organization_id:
        return existing
    return None


def _replay_after_race(
    db: Session, cred: ApiCredential, agent_id: str, idem: str | None
) -> Run | None:
    db.rollback()
    return _idempotent_run(db, cred, agent_id, idem)


@router.get("/api/v1/gateway/agents/{agent_id}")
def gateway_agent(
    agent_id: str,
    db: Session = Depends(get_db),
    cred: ApiCredential = Depends(customer_credential),
) -> dict:
    """Customer-key metadata probe used by integration setup screens."""
    if not ({"agents:run", "runs:read"} & set(cred.scopes or [])):
        raise AppError("forbidden", "Credential lacks agents:run or runs:read scope.", 403)
    agent = _require_agent(db, cred, agent_id)
    deployment = latest_deployment(db, agent.id)
    return {
        "id": agent.id,
        "name": agent.name,
        "provider": agent.provider,
        "provider_resource_kind": agent.provider_resource_kind,
        "lifecycle_status": agent.lifecycle_status,
        "archived": agent.archived_at is not None,
        "deployment": (
            {
                "id": deployment.id,
                "status": deployment.status,
                "health_status": deployment.health_status,
                "environment": deployment.environment,
            }
            if deployment
            else None
        ),
        "created_at": agent.created_at.isoformat(),
    }


@router.post("/api/v1/agents/{agent_id}/runs")
def gateway_run(
    agent_id: str,
    body: RunRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    cred: ApiCredential = Depends(customer_credential),
) -> dict:
    if "agents:run" not in (cred.scopes or []):
        raise AppError("forbidden", "Credential lacks agents:run scope.", 403)
    enforce_rate_limit(cred.id, settings.gateway_rate_limit_per_minute)
    idem = _idempotency_key(request)
    existing = _idempotent_run(db, cred, agent_id, idem)
    if existing is not None:
        return _gateway_response(existing)

    agent = _require_agent(db, cred, agent_id)

    cred.last_used_at = datetime.now(UTC)
    correlation = getattr(request.state, "request_id", None) or new_id("corr")
    try:
        run = execute_agent(
            db,
            settings,
            agent=agent,
            payload=body.input,
            conversation_id=body.conversation_id,
            metadata=body.metadata,
            source="gateway",
            credential=cred,
            correlation_id=correlation,
            user_label=cred.id,
            idempotency_key=idem,
        )
    except IntegrityError:
        replay = _replay_after_race(db, cred, agent_id, idem)
        if replay is not None:
            return _gateway_response(replay)
        raise
    return _gateway_response(run)


@router.post("/api/v1/agents/{agent_id}/runs/stream")
def gateway_stream(
    agent_id: str,
    body: RunRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    cred: ApiCredential = Depends(customer_credential),
):
    """Stream a gateway run as SSE using the same credential and limits."""
    if "agents:run" not in (cred.scopes or []):
        raise AppError("forbidden", "Credential lacks agents:run scope.", 403)
    enforce_rate_limit(cred.id, settings.gateway_rate_limit_per_minute)
    idem = _idempotency_key(request)
    existing = _idempotent_run(db, cred, agent_id, idem)
    if existing is not None:
        output = existing.output_summary or {}
        replay = StreamEvent(
            type="final",
            text=output.get("message"),
            data={
                "run_id": existing.id,
                "status": existing.status,
                "output": {
                    "message": output.get("message"),
                    "conversation_id": output.get("conversation_id"),
                },
                "provider_extension": output.get("provider_extension") or {},
                "replayed": True,
            },
        )
        return event_stream_response(iter([replay]), request=request)

    agent = _require_agent(db, cred, agent_id)
    cred.last_used_at = datetime.now(UTC)
    correlation = getattr(request.state, "request_id", None) or new_id("corr")
    try:
        ctx = prepare_execution(
            db,
            settings,
            agent=agent,
            payload=body.input,
            conversation_id=body.conversation_id,
            metadata=body.metadata,
            source="gateway",
            credential=cred,
            correlation_id=correlation,
            user_label=cred.id,
            idempotency_key=idem,
        )
    except IntegrityError:
        replay = _replay_after_race(db, cred, agent_id, idem)
        if replay is not None:
            output = replay.output_summary or {}
            return event_stream_response(
                iter(
                    [
                        StreamEvent(
                            type="final",
                            text=output.get("message"),
                            data={
                                "run_id": replay.id,
                                "status": replay.status,
                                "output": {
                                    "message": output.get("message"),
                                    "conversation_id": output.get("conversation_id"),
                                },
                                "provider_extension": output.get("provider_extension") or {},
                                "replayed": True,
                            },
                        )
                    ]
                ),
                request=request,
            )
        raise
    return event_stream_response(
        stream_execution(settings, ctx, body.input), request=request
    )


@router.post("/api/v1/agents/{agent_id}/runs/async")
def gateway_async(
    agent_id: str,
    body: RunRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    cred: ApiCredential = Depends(customer_credential),
) -> dict:
    """Enqueue an asynchronous provider run and return a run receipt."""
    if "agents:run" not in (cred.scopes or []):
        raise AppError("forbidden", "Credential lacks agents:run scope.", 403)
    enforce_rate_limit(cred.id, settings.gateway_rate_limit_per_minute)
    idem = _idempotency_key(request)
    existing = _idempotent_run(db, cred, agent_id, idem)
    if existing is not None:
        return _gateway_response(existing)

    agent = _require_agent(db, cred, agent_id)
    cred.last_used_at = datetime.now(UTC)
    correlation = getattr(request.state, "request_id", None) or new_id("corr")
    try:
        run = start_async_agent(
            db,
            settings,
            agent=agent,
            payload=body.input,
            conversation_id=body.conversation_id,
            metadata=body.metadata,
            source="gateway",
            credential=cred,
            correlation_id=correlation,
            user_label=cred.id,
            idempotency_key=idem,
        )
    except IntegrityError:
        replay = _replay_after_race(db, cred, agent_id, idem)
        if replay is not None:
            return _gateway_response(replay)
        raise
    return _gateway_response(run)
