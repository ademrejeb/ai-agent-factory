import re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.deps import AuthContext, auth_context
from app.errors import AppError
from app.ids import new_id
from app.lifecycle import CONFIGURED, DRAFT, MONITORED, PUBLISHED, VALIDATED, transition
from app.models import (
    Agent,
    AgentSecret,
    AgentVersion,
    AuditEvent,
    Deployment,
    LocalGraph,
    ProviderConnection,
    Run,
    Workspace,
)
from app.providers.registry import get_adapter
from app.security import encrypt_secret
from app.schemas import (
    AgentCreate,
    AgentFromTemplate,
    AgentLinkRequest,
    AgentSecretUpsert,
    AgentUpdate,
    LocalGraphDryRunRequest,
    LocalGraphRequest,
    RunRequest,
)
from app.services.execution import (
    draft_graph,
    execute_agent,
    latest_deployment,
    load_credentials,
    prepare_execution,
    start_async_agent,
    stream_execution,
)
from app.services.net import validate_outbound_url
from app.services.templates import ticketing_dispatch_graph
from app.services.local_graph import (
    GraphValidationError,
    default_graph,
    validate_graph,
)
from app.services.serialize import agent_out, deployment_out, run_out, version_out
from app.services.sse import event_stream_response

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


def _get_agent(db: Session, ctx: AuthContext, agent_id: str) -> Agent:
    agent = db.get(Agent, agent_id)
    if not agent or agent.organization_id != ctx.organization.id:
        raise AppError("not_found", "Agent not found.", 404)
    return agent




def _audit_workflow(
    db: Session,
    ctx: AuthContext,
    agent: Agent,
    action: str,
    metadata: dict,
) -> None:
    db.add(
        AuditEvent(
            id=new_id("aud"),
            organization_id=ctx.organization.id,
            actor_user_id=ctx.user.id,
            action=action,
            resource_type="agent",
            resource_id=agent.id,
            metadata_json=metadata,
            created_at=datetime.now(UTC),
        )
    )


def _langchain_agent(db: Session, ctx: AuthContext, agent_id: str) -> Agent:
    agent = _get_agent(db, ctx, agent_id)
    if agent.provider != "langchain":
        raise AppError(
            "unsupported_capability",
            "The platform graph editor is available only for LangChain agents.",
            409,
            {"provider": agent.provider},
        )
    return agent


def _graph_revision(db: Session, agent_id: str) -> int:
    row = db.query(LocalGraph).filter(LocalGraph.agent_id == agent_id).first()
    return row.revision if row else 0


@router.get("")
def list_agents(ctx: AuthContext = Depends(auth_context), db: Session = Depends(get_db)) -> dict:
    rows = (
        db.query(Agent)
        .filter(Agent.organization_id == ctx.organization.id, Agent.archived_at.is_(None))
        .order_by(Agent.created_at.desc())
        .all()
    )
    return {"items": [agent_out(a, latest_deployment(db, a.id)) for a in rows]}


@router.post("")
def create_agent(
    body: AgentCreate,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
) -> dict:
    ws = db.get(Workspace, body.workspace_id)
    if not ws or ws.organization_id != ctx.organization.id:
        raise AppError("not_found", "Workspace not found.", 404)
    agent = Agent(
        id=new_id("agent"),
        organization_id=ctx.organization.id,
        workspace_id=ws.id,
        name=body.name,
        description=body.description,
        purpose=body.purpose,
        tags=body.tags,
        lifecycle_status=DRAFT,
        created_at=datetime.now(UTC),
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent_out(agent)


@router.post("/from-template")
def create_agent_from_template(
    body: AgentFromTemplate,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    if ctx.role not in {"owner", "admin"}:
        raise AppError("forbidden", "Insufficient role.", 403)
    ws = db.get(Workspace, body.workspace_id)
    if not ws or ws.organization_id != ctx.organization.id:
        raise AppError("not_found", "Workspace not found.", 404)
    conn = db.get(ProviderConnection, body.provider_connection_id)
    if not conn or conn.organization_id != ctx.organization.id:
        raise AppError("not_found", "Provider connection not found.", 404)
    if conn.provider != "langchain":
        raise AppError(
            "unsupported_capability",
            "Ticket dispatch templates currently require a LangChain connection.",
            409,
            {"provider": conn.provider},
        )
    validate_outbound_url(
        body.ticketing_base_url,
        allow_private=settings.private_urls_allowed,
        label="Ticketing base URL",
    )
    model = body.model or (conn.extra_config or {}).get("model")
    if not isinstance(model, str) or not model.strip():
        raise AppError(
            "invalid_request",
            "The LangChain connection must have a default model, or pass model explicitly.",
            400,
        )
    now = datetime.now(UTC)
    agent = Agent(
        id=new_id("agent"),
        organization_id=ctx.organization.id,
        workspace_id=ws.id,
        name=body.name.strip(),
        description=body.description,
        purpose=body.purpose
        or "Analyse incoming field-service requests and dispatch the most adaptable technician using real skills, proximity, load and history metrics.",
        tags=["ticketing", "dispatch", "field-service"],
        lifecycle_status=CONFIGURED,
        provider="langchain",
        provider_connection_id=conn.id,
        provider_resource_kind="graph",
        created_at=now,
    )
    db.add(agent)
    db.flush()
    graph = ticketing_dispatch_graph(
        ticketing_base_url=body.ticketing_base_url, model=model.strip()
    )
    db.add(
        LocalGraph(
            id=new_id("lgr"),
            organization_id=ctx.organization.id,
            agent_id=agent.id,
            revision=1,
            nodes=graph["nodes"],
            edges=graph["edges"],
            created_at=now,
            updated_at=now,
        )
    )
    db.add(
        AgentSecret(
            id=new_id("asec"),
            organization_id=ctx.organization.id,
            agent_id=agent.id,
            name="ticketing_agent_key",
            value_encrypted=encrypt_secret(settings, body.ticketing_agent_key),
            created_at=now,
            updated_at=now,
        )
    )
    _audit_workflow(
        db,
        ctx,
        agent,
        "agent.template.create",
        {
            "template": body.template,
            "provider_connection_id": conn.id,
            "ticketing_base_url": body.ticketing_base_url,
        },
    )
    db.commit()
    db.refresh(agent)
    return {**agent_out(agent), "graph": graph}


@router.get("/{agent_id}")
def get_agent(
    agent_id: str, ctx: AuthContext = Depends(auth_context), db: Session = Depends(get_db)
) -> dict:
    agent = _get_agent(db, ctx, agent_id)
    return agent_out(agent, latest_deployment(db, agent.id))


@router.patch("/{agent_id}")
def update_agent(
    agent_id: str,
    body: AgentUpdate,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
) -> dict:
    if ctx.role not in {"owner", "admin", "member"}:
        raise AppError("forbidden", "Insufficient role.", 403)
    agent = _get_agent(db, ctx, agent_id)
    if body.workspace_id is not None:
        ws = db.get(Workspace, body.workspace_id)
        if not ws or ws.organization_id != ctx.organization.id:
            raise AppError("not_found", "Workspace not found.", 404)
        agent.workspace_id = ws.id
    if body.name is not None:
        agent.name = body.name.strip()
        if not agent.name:
            raise AppError("invalid_request", "Agent name cannot be empty.", 400)
    if body.description is not None:
        agent.description = body.description
    if body.purpose is not None:
        agent.purpose = body.purpose
    if body.tags is not None:
        agent.tags = [tag.strip() for tag in body.tags if tag.strip()][:20]
    if body.skill_ids is not None:
        from app.models import Skill

        valid = {
            row.id
            for row in db.query(Skill)
            .filter(
                Skill.organization_id == ctx.organization.id,
                Skill.id.in_(body.skill_ids),
            )
            .all()
        }
        unknown = set(body.skill_ids) - valid
        if unknown:
            raise AppError(
                "invalid_request",
                "One or more skills do not belong to this organization.",
                400,
                {"skill_ids": sorted(unknown)},
            )
        agent.skill_ids = sorted(valid)
    db.commit()
    db.refresh(agent)
    return agent_out(agent, latest_deployment(db, agent.id))


SECRET_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{1,63}$")


@router.get("/{agent_id}/secrets")
def list_agent_secrets(
    agent_id: str, ctx: AuthContext = Depends(auth_context), db: Session = Depends(get_db)
) -> dict:
    agent = _get_agent(db, ctx, agent_id)
    rows = (
        db.query(AgentSecret)
        .filter(AgentSecret.agent_id == agent.id)
        .order_by(AgentSecret.name)
        .all()
    )
    return {
        "items": [
            {
                "name": row.name,
                "updated_at": row.updated_at.isoformat(),
                "present": True,
            }
            for row in rows
        ]
    }


@router.put("/{agent_id}/secrets/{name}")
def upsert_agent_secret(
    agent_id: str,
    name: str,
    body: AgentSecretUpsert,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    if ctx.role not in {"owner", "admin"}:
        raise AppError("forbidden", "Insufficient role.", 403)
    if not SECRET_NAME_RE.match(name):
        raise AppError(
            "invalid_request",
            "Secret names must start with a letter and contain letters, digits or underscores.",
            400,
        )
    agent = _get_agent(db, ctx, agent_id)
    if agent.archived_at:
        raise AppError("invalid_lifecycle", "Archived agents cannot be edited.", 409)
    now = datetime.now(UTC)
    row = (
        db.query(AgentSecret)
        .filter(AgentSecret.agent_id == agent.id, AgentSecret.name == name)
        .first()
    )
    if row is None:
        row = AgentSecret(
            id=new_id("asec"),
            organization_id=agent.organization_id,
            agent_id=agent.id,
            name=name,
            value_encrypted=encrypt_secret(settings, body.value),
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.value_encrypted = encrypt_secret(settings, body.value)
        row.updated_at = now
    _audit_workflow(db, ctx, agent, "agent.secret.set", {"name": name})
    db.commit()
    return {"name": name, "updated_at": now.isoformat(), "present": True}


@router.delete("/{agent_id}/secrets/{name}")
def delete_agent_secret(
    agent_id: str,
    name: str,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
) -> dict:
    if ctx.role not in {"owner", "admin"}:
        raise AppError("forbidden", "Insufficient role.", 403)
    agent = _get_agent(db, ctx, agent_id)
    row = (
        db.query(AgentSecret)
        .filter(AgentSecret.agent_id == agent.id, AgentSecret.name == name)
        .first()
    )
    if row is None:
        raise AppError("not_found", "Secret not found.", 404)
    db.delete(row)
    _audit_workflow(db, ctx, agent, "agent.secret.delete", {"name": name})
    db.commit()
    return {"ok": True}


@router.get("/{agent_id}/runs")
def agent_runs(
    agent_id: str,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    agent = _get_agent(db, ctx, agent_id)
    rows = (
        db.query(Run)
        .filter(Run.organization_id == ctx.organization.id, Run.agent_id == agent.id)
        .order_by(Run.started_at.desc())
        .limit(limit)
        .all()
    )
    return {"items": [run_out(row, agent_name=agent.name) for row in rows]}


@router.get("/{agent_id}/deployments")
def agent_deployments(
    agent_id: str,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
) -> dict:
    agent = _get_agent(db, ctx, agent_id)
    rows = (
        db.query(Deployment)
        .filter(
            Deployment.organization_id == ctx.organization.id,
            Deployment.agent_id == agent.id,
        )
        .order_by(Deployment.created_at.desc())
        .all()
    )
    return {"items": [deployment_out(row) for row in rows]}


@router.get("/{agent_id}/versions")
def agent_versions(
    agent_id: str,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
) -> dict:
    agent = _get_agent(db, ctx, agent_id)
    rows = (
        db.query(AgentVersion)
        .filter(
            AgentVersion.organization_id == ctx.organization.id,
            AgentVersion.agent_id == agent.id,
        )
        .order_by(AgentVersion.version.desc())
        .all()
    )
    return {"items": [version_out(row) for row in rows]}


@router.post("/{agent_id}/link")
def link_agent(
    agent_id: str,
    body: AgentLinkRequest,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    if ctx.role not in {"owner", "admin", "member"}:
        raise AppError("forbidden", "Insufficient role.", 403)
    agent = _get_agent(db, ctx, agent_id)
    conn = db.get(ProviderConnection, body.provider_connection_id)
    if not conn or conn.organization_id != ctx.organization.id:
        raise AppError("not_found", "Provider connection not found.", 404)
    validate_outbound_url(
        conn.base_url,
        allow_private=settings.private_urls_allowed,
        label="Provider base URL",
    )
    adapter = get_adapter(conn.provider)
    creds = load_credentials(settings, conn)
    check = adapter.check_connectivity(
        base_url=conn.base_url,
        credentials=creds,
        extra_config=conn.extra_config or {},
        timeout_seconds=min(settings.gateway_timeout_seconds, 20),
    )
    if not check.ok:
        agent.last_sync_error = check.error
        db.commit()
        raise AppError("provider_unreachable", check.error or "Provider check failed.", 502, check.details)

    resource_id = body.provider_resource_id
    kind = "graph"
    agent.provider = conn.provider
    agent.provider_connection_id = conn.id
    agent.provider_resource_id = resource_id
    agent.provider_resource_kind = kind
    # A "connected_limited" check means the provider answered but this
    # gateway cannot execute the resource. Keep the reason visible instead of
    # reporting a clean link.
    agent.last_sync_error = check.error if check.status == "connected_limited" else None
    if conn.provider == "langchain":
        existing = db.query(LocalGraph).filter(LocalGraph.agent_id == agent.id).first()
        if existing is None:
            model = (conn.extra_config or {}).get("model")
            graph = default_graph(model=model if isinstance(model, str) else None)
            db.add(
                LocalGraph(
                    id=new_id("lgr"),
                    organization_id=agent.organization_id,
                    agent_id=agent.id,
                    revision=1,
                    nodes=graph["nodes"],
                    edges=graph["edges"],
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )
    if agent.lifecycle_status == DRAFT:
        agent.lifecycle_status = transition(agent.lifecycle_status, CONFIGURED)
    db.commit()
    db.refresh(agent)
    return agent_out(agent)


@router.post("/{agent_id}/test")
def test_agent(
    agent_id: str,
    body: RunRequest,
    request: Request,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    agent = _get_agent(db, ctx, agent_id)
    if agent.lifecycle_status == DRAFT:
        raise AppError("invalid_lifecycle", "Link a provider resource before testing.", 409)
    correlation = getattr(request.state, "request_id", None) or new_id("corr")
    run = execute_agent(
        db,
        settings,
        agent=agent,
        payload=body.input,
        conversation_id=body.conversation_id,
        metadata=body.metadata,
        source="test",
        credential=None,
        correlation_id=correlation,
        user_label=ctx.user.id,
    )
    return run_out(run)


@router.post("/{agent_id}/test/stream")
def stream_test_agent(
    agent_id: str,
    body: RunRequest,
    request: Request,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """Stream a test run as Server-Sent Events.

    Events are ``chunk`` (incremental text), ``status`` (provider progress),
    ``final`` (normalized result incl. ``run_id``), and ``error``.
    """
    agent = _get_agent(db, ctx, agent_id)
    if agent.lifecycle_status == DRAFT:
        raise AppError("invalid_lifecycle", "Link a provider resource before testing.", 409)
    correlation = getattr(request.state, "request_id", None) or new_id("corr")
    ctx_exec = prepare_execution(
        db,
        settings,
        agent=agent,
        payload=body.input,
        conversation_id=body.conversation_id,
        metadata=body.metadata,
        source="test",
        credential=None,
        correlation_id=correlation,
        user_label=ctx.user.id,
    )
    return event_stream_response(
        stream_execution(settings, ctx_exec, body.input), request=request
    )


@router.post("/{agent_id}/test/async")
def start_async_test_agent(
    agent_id: str,
    body: RunRequest,
    request: Request,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Ask the adapter to enqueue an async run and return the receipt."""
    agent = _get_agent(db, ctx, agent_id)
    if agent.lifecycle_status == DRAFT:
        raise AppError("invalid_lifecycle", "Link a provider resource before testing.", 409)
    correlation = getattr(request.state, "request_id", None) or new_id("corr")
    run = start_async_agent(
        db,
        settings,
        agent=agent,
        payload=body.input,
        conversation_id=body.conversation_id,
        metadata=body.metadata,
        source="test",
        credential=None,
        correlation_id=correlation,
        user_label=ctx.user.id,
    )
    return run_out(run)


@router.get("/{agent_id}/graph")
def get_agent_graph(
    agent_id: str,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
) -> dict:
    """Read the platform-owned LangGraph draft for a LangChain agent."""
    agent = _langchain_agent(db, ctx, agent_id)
    row = db.query(LocalGraph).filter(LocalGraph.agent_id == agent.id).first()
    if row is not None:
        try:
            graph = validate_graph(row.nodes, row.edges)
        except GraphValidationError as exc:
            raise AppError(
                "invalid_graph", exc.message, 409, {"node_id": exc.node_id}
            ) from exc
        revision = row.revision
        updated_at = row.updated_at.isoformat()
    else:
        conn = (
            db.get(ProviderConnection, agent.provider_connection_id)
            if agent.provider_connection_id
            else None
        )
        model = (conn.extra_config or {}).get("model") if conn else None
        graph = default_graph(model=model if isinstance(model, str) else None)
        revision = 0
        updated_at = None
    return {
        "provider": "langchain",
        "agent_id": agent.id,
        "revision": revision,
        "source": "draft",
        "graph": graph,
        "updated_at": updated_at,
    }


@router.put("/{agent_id}/graph")
def put_agent_graph(
    agent_id: str,
    body: LocalGraphRequest,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
) -> dict:
    """Validate and save the LangGraph draft. Publishing snapshots it."""
    if ctx.role not in {"owner", "admin", "member"}:
        raise AppError("forbidden", "Insufficient role.", 403)
    agent = _langchain_agent(db, ctx, agent_id)
    if agent.archived_at:
        raise AppError("invalid_lifecycle", "Archived agents cannot be edited.", 409)
    try:
        graph = validate_graph(body.nodes, body.edges)
    except GraphValidationError as exc:
        raise AppError(
            "invalid_graph", exc.message, 400, {"node_id": exc.node_id}
        ) from exc

    row = db.query(LocalGraph).filter(LocalGraph.agent_id == agent.id).first()
    now = datetime.now(UTC)
    if row is None:
        row = LocalGraph(
            id=new_id("lgr"),
            organization_id=agent.organization_id,
            agent_id=agent.id,
            revision=1,
            nodes=graph["nodes"],
            edges=graph["edges"],
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.revision += 1
        row.nodes = graph["nodes"]
        row.edges = graph["edges"]
        row.updated_at = now
    _audit_workflow(
        db,
        ctx,
        agent,
        "graph.draft.replace",
        {
            "revision": row.revision,
            "nodes": len(graph["nodes"]),
            "edges": len(graph["edges"]),
        },
    )
    db.commit()
    db.refresh(row)
    return {
        "provider": "langchain",
        "agent_id": agent.id,
        "revision": row.revision,
        "source": "draft",
        "graph": graph,
        "updated_at": row.updated_at.isoformat(),
    }


@router.post("/{agent_id}/graph/validate")
def validate_agent_graph(
    agent_id: str,
    body: LocalGraphRequest,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
) -> dict:
    """Lint a graph without saving it or spending model tokens."""
    _langchain_agent(db, ctx, agent_id)
    try:
        graph = validate_graph(body.nodes, body.edges)
    except GraphValidationError as exc:
        return {
            "valid": False,
            "error": {"message": exc.message, "node_id": exc.node_id},
            "graph": None,
        }
    return {"valid": True, "error": None, "graph": graph}


@router.post("/{agent_id}/graph/dry_run")
def dry_run_agent_graph(
    agent_id: str,
    body: LocalGraphDryRunRequest,
    request: Request,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Execute the saved draft graph against the real model and record a run.

    This is intentionally a *real* run rather than a pretend dry run: it is
    the fastest way to prove a graph, and the resulting ``Run`` makes the cost
    and failure visible. Use ``/graph/validate`` for a free lint.
    """
    agent = _langchain_agent(db, ctx, agent_id)
    if agent.lifecycle_status == DRAFT:
        raise AppError("invalid_lifecycle", "Link a provider before running the graph.", 409)
    correlation = getattr(request.state, "request_id", None) or new_id("corr")
    run = execute_agent(
        db,
        settings,
        agent=agent,
        payload=body.input,
        conversation_id=None,
        metadata={"dry_run": True},
        source="test",
        credential=None,
        correlation_id=correlation,
        user_label=ctx.user.id,
    )
    return {
        "run": run_out(run),
        "revision": _graph_revision(db, agent.id),
        "graph": draft_graph(db, agent),
    }


@router.post("/{agent_id}/publish")
def publish_agent(
    agent_id: str,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    if ctx.role not in {"owner", "admin"}:
        raise AppError("forbidden", "Insufficient role.", 403)
    agent = _get_agent(db, ctx, agent_id)
    if agent.lifecycle_status not in {VALIDATED, PUBLISHED, MONITORED}:
        raise AppError(
            "invalid_lifecycle",
            "Publish requires a successful test (validated) configuration.",
            409,
            {"status": agent.lifecycle_status},
        )
    conn = db.get(ProviderConnection, agent.provider_connection_id) if agent.provider_connection_id else None
    if not conn:
        raise AppError("invalid_agent", "Provider connection missing.", 400)
    adapter = get_adapter(conn.provider)
    check = adapter.check_connectivity(
        base_url=conn.base_url,
        credentials=load_credentials(settings, conn),
        extra_config=conn.extra_config or {},
        timeout_seconds=min(settings.gateway_timeout_seconds, 20),
    )
    if not check.ok:
        raise AppError("provider_unreachable", check.error or "Provider not reachable.", 502)

    count = db.query(AgentVersion).filter(AgentVersion.agent_id == agent.id).count()
    snapshot = {
        "name": agent.name,
        "provider": agent.provider,
        "provider_connection_id": agent.provider_connection_id,
        "provider_resource_id": agent.provider_resource_id,
        "provider_resource_kind": agent.provider_resource_kind,
    }
    if agent.provider == "langchain":
        row = db.query(LocalGraph).filter(LocalGraph.agent_id == agent.id).first()
        try:
            graph = (
                validate_graph(row.nodes, row.edges)
                if row is not None
                else default_graph(
                    model=(conn.extra_config or {}).get("model")
                    if isinstance((conn.extra_config or {}).get("model"), str)
                    else None
                )
            )
        except GraphValidationError as exc:
            raise AppError(
                "invalid_graph",
                f"Cannot publish an invalid graph: {exc.message}",
                409,
                {"node_id": exc.node_id},
            ) from exc
        snapshot["graph"] = {
            "revision": row.revision if row is not None else 0,
            **graph,
        }
    version = AgentVersion(
        id=new_id("aver"),
        organization_id=agent.organization_id,
        agent_id=agent.id,
        version=count + 1,
        snapshot=snapshot,
        created_at=datetime.now(UTC),
    )
    db.add(version)
    db.flush()
    dep = Deployment(
        id=new_id("dep"),
        organization_id=agent.organization_id,
        agent_id=agent.id,
        version_id=version.id,
        environment="development",
        status="active",
        health_status="healthy" if check.ok else "unknown",
        last_health_check_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    db.add(dep)
    prev = (
        db.query(Deployment)
        .filter(Deployment.agent_id == agent.id, Deployment.id != dep.id, Deployment.status == "active")
        .all()
    )
    for item in prev:
        item.status = "superseded"
    if agent.lifecycle_status != PUBLISHED:
        agent.lifecycle_status = transition(agent.lifecycle_status, PUBLISHED)
    db.commit()
    db.refresh(agent)
    return agent_out(agent, dep)


@router.post("/{agent_id}/deactivate")
def deactivate_agent(
    agent_id: str, ctx: AuthContext = Depends(auth_context), db: Session = Depends(get_db)
) -> dict:
    if ctx.role not in {"owner", "admin"}:
        raise AppError("forbidden", "Insufficient role.", 403)
    agent = _get_agent(db, ctx, agent_id)
    agent.lifecycle_status = transition(agent.lifecycle_status, "deactivated")
    agent.archived_at = datetime.now(UTC)
    dep = latest_deployment(db, agent.id)
    if dep:
        dep.status = "inactive"
        dep.health_status = "unknown"
    db.commit()
    db.refresh(agent)
    return agent_out(agent, dep)


@router.post("/{agent_id}/reactivate")
def reactivate_agent(
    agent_id: str, ctx: AuthContext = Depends(auth_context), db: Session = Depends(get_db)
) -> dict:
    if ctx.role not in {"owner", "admin"}:
        raise AppError("forbidden", "Insufficient role.", 403)
    agent = _get_agent(db, ctx, agent_id)
    if agent.lifecycle_status != "deactivated":
        raise AppError("invalid_lifecycle", "Only deactivated agents can be reactivated.", 409)
    agent.lifecycle_status = transition(agent.lifecycle_status, "draft")
    agent.archived_at = None
    _audit_workflow(db, ctx, agent, "agent.reactivated", {})
    db.commit()
    db.refresh(agent)
    return agent_out(agent, latest_deployment(db, agent.id))



