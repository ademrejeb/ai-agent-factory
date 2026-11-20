from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.deps import AuthContext, auth_context
from app.errors import AppError
from app.ids import new_id
from app.models import AuditEvent, Tool
from app.schemas import McpDiscoverRequest, ToolCreate, ToolTestRequest, ToolUpdate
from app.services.net import validate_outbound_url
from app.services.tools import (
    discover_mcp_tools,
    execute_tool,
    load_headers,
    normalize_input_schema,
    normalize_tool_config,
    store_headers,
    tool_out,
)

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


def _require_tool(db: Session, ctx: AuthContext, tool_id: str) -> Tool:
    tool = db.get(Tool, tool_id)
    if tool is None or tool.organization_id != ctx.organization.id:
        raise AppError("not_found", "Tool not found.", 404)
    return tool


def _audit(db: Session, ctx: AuthContext, action: str, tool: Tool) -> None:
    db.add(
        AuditEvent(
            id=new_id("aud"),
            organization_id=ctx.organization.id,
            actor_user_id=ctx.user.id,
            action=action,
            resource_type="tool",
            resource_id=tool.id,
            metadata_json={"name": tool.name, "kind": tool.kind},
            created_at=datetime.now(UTC),
        )
    )


@router.get("")
def list_tools(
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    rows = (
        db.query(Tool)
        .filter(Tool.organization_id == ctx.organization.id)
        .order_by(Tool.name.asc())
        .all()
    )
    return {"items": [tool_out(row, settings) for row in rows]}


@router.post("")
def create_tool(
    body: ToolCreate,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    if ctx.role not in {"owner", "admin"}:
        raise AppError("forbidden", "Only owners and admins can create tools.", 403)
    config = normalize_tool_config(body.kind, body.config)
    url = config.get("url") or config.get("server_url")
    validate_outbound_url(str(url), allow_private=settings.private_urls_allowed, label="Tool URL")
    now = datetime.now(UTC)
    tool = Tool(
        id=new_id("tool"),
        organization_id=ctx.organization.id,
        name=body.name.strip(),
        kind=body.kind,
        description=body.description,
        config=config,
        headers_encrypted=store_headers(settings, body.headers),
        input_schema=normalize_input_schema(body.input_schema),
        enabled=body.enabled,
        created_at=now,
        updated_at=now,
    )
    db.add(tool)
    _audit(db, ctx, "tool.create", tool)
    db.commit()
    db.refresh(tool)
    return tool_out(tool, settings)


@router.patch("/{tool_id}")
def update_tool(
    tool_id: str,
    body: ToolUpdate,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    if ctx.role not in {"owner", "admin"}:
        raise AppError("forbidden", "Only owners and admins can edit tools.", 403)
    tool = _require_tool(db, ctx, tool_id)
    if body.name is not None:
        tool.name = body.name.strip()
    if body.description is not None:
        tool.description = body.description
    if body.kind is not None:
        tool.kind = body.kind
    if body.config is not None:
        tool.config = normalize_tool_config(tool.kind, body.config)
    if body.headers is not None:
        tool.headers_encrypted = store_headers(settings, body.headers)
    if body.input_schema is not None:
        tool.input_schema = normalize_input_schema(body.input_schema)
    if body.enabled is not None:
        tool.enabled = body.enabled
    tool.updated_at = datetime.now(UTC)
    _audit(db, ctx, "tool.update", tool)
    db.commit()
    db.refresh(tool)
    return tool_out(tool, settings)


@router.delete("/{tool_id}")
def delete_tool(
    tool_id: str,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
) -> dict:
    if ctx.role not in {"owner", "admin"}:
        raise AppError("forbidden", "Only owners and admins can delete tools.", 403)
    tool = _require_tool(db, ctx, tool_id)
    _audit(db, ctx, "tool.delete", tool)
    db.delete(tool)
    db.commit()
    return {"ok": True}


@router.post("/{tool_id}/test")
def test_tool(
    tool_id: str,
    body: ToolTestRequest,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    tool = _require_tool(db, ctx, tool_id)
    try:
        result = execute_tool(
            settings,
            tool,
            body.arguments,
            allow_private=settings.private_urls_allowed,
        )
    except AppError as exc:
        raise AppError(exc.code, exc.message, exc.status_code, {**exc.details, "tool_id": tool.id}) from exc
    _audit(db, ctx, "tool.test", tool)
    db.commit()
    return {"ok": True, "result": result, "headers": sorted(load_headers(settings, tool).keys())}


@router.post("/discover/mcp")
def discover_mcp(
    body: McpDiscoverRequest,
    ctx: AuthContext = Depends(auth_context),
    settings: Settings = Depends(get_settings),
) -> dict:
    if ctx.role not in {"owner", "admin"}:
        raise AppError("forbidden", "Only owners and admins can discover MCP tools.", 403)
    validate_outbound_url(
        body.server_url,
        allow_private=settings.private_urls_allowed,
        label="MCP server URL",
    )
    items = discover_mcp_tools(
        server_url=body.server_url,
        headers=body.headers,
        timeout=min(settings.gateway_timeout_seconds, 20),
        allow_private=settings.private_urls_allowed,
    )
    return {"items": items}
