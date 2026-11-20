import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.deps import AuthContext, auth_context
from app.errors import AppError
from app.ids import new_id
from app.models import Agent, ProviderConnection
from app.providers.catalog import get_provider
from app.providers.registry import get_adapter
from app.schemas import ProviderConnectionCreate, ProviderConnectionUpdate
from app.security import encrypt_secret
from app.services.execution import load_credentials
from app.services.net import validate_outbound_url
from app.services.serialize import connection_out

router = APIRouter(prefix="/api/v1/provider-connections", tags=["providers"])


def _validate_connection_url(conn: ProviderConnection, settings: Settings) -> None:
    validate_outbound_url(
        conn.base_url,
        allow_private=settings.private_urls_allowed,
        label="Provider base URL",
    )


def _apply_check(conn: ProviderConnection, result) -> dict:
    """Persist a connectivity result and non-secret provider metadata."""
    extra = dict(conn.extra_config or {})
    details = result.details or {}
    mode = details.get("mode")
    if mode:
        extra["mode"] = mode
    if details.get("model"):
        extra["model"] = details["model"]
    if "model_listed" in details:
        extra["model_listed"] = bool(details["model_listed"])
    if "model_count" in details:
        extra["model_count"] = details["model_count"]
    if details.get("warning"):
        extra["warning"] = details["warning"]
    elif result.ok:
        extra.pop("warning", None)
    if result.resource_label:
        extra["resource_label"] = result.resource_label
    conn.extra_config = extra
    conn.status = result.status
    conn.last_error = result.error
    conn.last_checked_at = datetime.now(UTC)
    conn.capabilities = result.capabilities
    return extra



@router.get("")
def list_connections(ctx: AuthContext = Depends(auth_context), db: Session = Depends(get_db)) -> dict:
    rows = (
        db.query(ProviderConnection)
        .filter(ProviderConnection.organization_id == ctx.organization.id)
        .order_by(ProviderConnection.created_at.desc())
        .all()
    )
    return {"items": [connection_out(r) for r in rows]}


@router.post("")
def create_connection(
    body: ProviderConnectionCreate,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    if ctx.role not in {"owner", "admin"}:
        raise AppError("forbidden", "Insufficient role.", 403)
    descriptor = get_provider(body.provider)
    if descriptor is None:
        raise AppError("unsupported_provider", "Unknown provider.", 400)
    if descriptor.get("requires_model") and not (body.model or "").strip():
        raise AppError(
            "invalid_request",
            "A model name is required for this provider.",
            400,
            {"fields": [{"path": ["body", "model"], "message": "Required"}]},
        )
    validate_outbound_url(
        body.base_url,
        allow_private=settings.private_urls_allowed,
        label="Provider base URL",
    )
    adapter = get_adapter(body.provider)
    extra = {}
    if body.workspace_id:
        extra["workspace_id"] = body.workspace_id.strip()
    if body.model:
        extra["model"] = body.model.strip()
    creds = {"api_key": body.api_key}
    if body.workspace_id:
        creds["workspace_id"] = extra["workspace_id"]
    conn = ProviderConnection(
        id=new_id("pcon"),
        organization_id=ctx.organization.id,
        provider=body.provider,
        name=body.name,
        base_url=body.base_url.rstrip("/"),
        credentials_encrypted=encrypt_secret(settings, json.dumps(creds)),
        extra_config=extra,
        status="unknown",
        capabilities={},
        created_at=datetime.now(UTC),
    )
    result = adapter.check_connectivity(
        base_url=conn.base_url,
        credentials=creds,
        extra_config=extra,
        timeout_seconds=min(settings.gateway_timeout_seconds, 20),
    )
    _apply_check(conn, result)
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return connection_out(conn)


@router.patch("/{connection_id}")
def update_connection(
    connection_id: str,
    body: ProviderConnectionUpdate,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    if ctx.role not in {"owner", "admin"}:
        raise AppError("forbidden", "Insufficient role.", 403)
    conn = _require_connection(db, ctx, connection_id)
    if body.base_url is not None:
        validate_outbound_url(
            body.base_url,
            allow_private=settings.private_urls_allowed,
            label="Provider base URL",
        )
        conn.base_url = body.base_url.rstrip("/")
        conn.status = "unknown"
    if body.name is not None:
        conn.name = body.name.strip()
    creds = load_credentials(settings, conn)
    extra = dict(conn.extra_config or {})
    changed_credentials = False
    if body.api_key is not None:
        creds["api_key"] = body.api_key
        changed_credentials = True
    if body.workspace_id is not None:
        extra["workspace_id"] = body.workspace_id.strip()
        creds["workspace_id"] = body.workspace_id.strip()
        changed_credentials = True
    if body.model is not None:
        extra["model"] = body.model.strip()
    if changed_credentials:
        conn.credentials_encrypted = encrypt_secret(settings, json.dumps(creds))
    conn.extra_config = extra
    db.commit()
    db.refresh(conn)
    return connection_out(conn)


@router.delete("/{connection_id}")
def delete_connection(
    connection_id: str,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
) -> dict:
    if ctx.role not in {"owner", "admin"}:
        raise AppError("forbidden", "Insufficient role.", 403)
    conn = _require_connection(db, ctx, connection_id)
    linked = db.query(Agent).filter(Agent.provider_connection_id == conn.id).first()
    if linked:
        raise AppError(
            "conflict",
            "This connection is linked to an agent. Unlink or archive that agent first.",
            409,
            {"agent_id": linked.id},
        )
    db.delete(conn)
    db.commit()
    return {"ok": True}


@router.post("/{connection_id}/check")
def check_connection(
    connection_id: str,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    conn = db.get(ProviderConnection, connection_id)
    if not conn or conn.organization_id != ctx.organization.id:
        raise AppError("not_found", "Provider connection not found.", 404)
    _validate_connection_url(conn, settings)
    adapter = get_adapter(conn.provider)
    creds = load_credentials(settings, conn)
    result = adapter.check_connectivity(
        base_url=conn.base_url,
        credentials=creds,
        extra_config=conn.extra_config or {},
        timeout_seconds=min(settings.gateway_timeout_seconds, 20),
    )
    _apply_check(conn, result)
    db.commit()
    db.refresh(conn)
    return connection_out(conn)


@router.get("/{connection_id}/resources")
def list_resources(
    connection_id: str,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """List linkable resources for a connection.

    The platform runtime owns its graph, so this returns one platform-owned
    resource. The endpoint remains for clients that used the older discovery
    flow and to keep the link step explicit.
    """
    conn = db.get(ProviderConnection, connection_id)
    if not conn or conn.organization_id != ctx.organization.id:
        raise AppError("not_found", "Provider connection not found.", 404)
    _validate_connection_url(conn, settings)
    adapter = get_adapter(conn.provider)
    lister = getattr(adapter, "list_resources", None)
    if lister is None:
        raise AppError(
            "unsupported_capability",
            f"{conn.provider} does not expose resource listing in this adapter.",
            409,
        )
    items = lister(
        base_url=conn.base_url,
        credentials=load_credentials(settings, conn),
        extra_config=conn.extra_config or {},
        timeout_seconds=min(settings.gateway_timeout_seconds, 20),
    )
    return {"provider": conn.provider, "items": items}


def _require_connection(db: Session, ctx: AuthContext, connection_id: str) -> ProviderConnection:
    conn = db.get(ProviderConnection, connection_id)
    if not conn or conn.organization_id != ctx.organization.id:
        raise AppError("not_found", "Provider connection not found.", 404)
    return conn


@router.get("/{connection_id}/models")
def list_models(
    connection_id: str,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Return the live model list from GET /models.

    This is the difference between typing a model name and knowing it exists.
    Ollama exposes every pulled local model here.
    """
    conn = _require_connection(db, ctx, connection_id)
    _validate_connection_url(conn, settings)
    adapter = get_adapter(conn.provider)
    creds = load_credentials(settings, conn)
    result = adapter.check_connectivity(
        base_url=conn.base_url,
        credentials=creds,
        extra_config=conn.extra_config or {},
        timeout_seconds=min(settings.gateway_timeout_seconds, 20),
    )
    if not result.ok:
        raise AppError("provider_unreachable", result.error or "Model list unavailable.", 502)
    details = result.details or {}
    return {
        "provider": conn.provider,
        "models": details.get("models_sample") or [],
        "model_count": details.get("model_count", 0),
        "selected": details.get("model"),
        "warning": details.get("warning"),
    }
