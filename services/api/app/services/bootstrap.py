"""Optional startup provisioning for the ticketing dispatcher workflow.

The template is also available from the UI. This path exists so a deployment
can keep the agent across rebuilds instead of asking an operator to click the
same form after every reset. It never overwrites an existing agent.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.config import Settings
from app.ids import new_id
from app.models import Agent, AgentSecret, LocalGraph, Organization, ProviderConnection, Workspace
from app.security import encrypt_secret
from app.services.templates import ticketing_dispatch_graph

logger = logging.getLogger("app.bootstrap")


def ensure_ticketing_agent(settings: Settings, db: Session) -> Agent | None:
    base_url = settings.bootstrap_ticketing_base_url.strip()
    agent_key = settings.bootstrap_ticketing_agent_key.strip()
    if not base_url or len(agent_key) < 16:
        return None
    org_query = db.query(Organization)
    if settings.bootstrap_ticketing_org_slug.strip():
        org_query = org_query.filter(Organization.slug == settings.bootstrap_ticketing_org_slug.strip())
    org = org_query.order_by(Organization.created_at.asc()).first()
    if org is None:
        return None
    existing = (
        db.query(Agent)
        .filter(
            Agent.organization_id == org.id,
            Agent.tags.isnot(None),
            Agent.name == "Ticketing dispatcher",
        )
        .first()
    )
    if existing is not None:
        return existing
    conn = (
        db.query(ProviderConnection)
        .filter(
            ProviderConnection.organization_id == org.id,
            ProviderConnection.provider == "langchain",
        )
        .order_by(ProviderConnection.created_at.asc())
        .first()
    )
    if conn is None:
        logger.info("Ticketing bootstrap skipped: no OpenAI-compatible connection in %s", org.slug)
        return None
    workspace = (
        db.query(Workspace)
        .filter(Workspace.organization_id == org.id)
        .order_by(Workspace.created_at.asc())
        .first()
    )
    if workspace is None:
        logger.info("Ticketing bootstrap skipped: no workspace in %s", org.slug)
        return None
    model = settings.bootstrap_ticketing_model.strip() or str(
        (conn.extra_config or {}).get("model") or ""
    )
    if not model:
        logger.info("Ticketing bootstrap skipped: connection has no model")
        return None
    now = datetime.now(UTC)
    agent = Agent(
        id=new_id("agent"),
        organization_id=org.id,
        workspace_id=workspace.id,
        name="Ticketing dispatcher",
        description=(
            "Loads live dispatch metrics from the ticketing service, lets the model choose one "
            "eligible technician, and guards the JSON shape before returning it."
        ),
        purpose=(
            "Answer field-service dispatch requests with a real, checkable technician choice."
        ),
        tags=["ticketing", "dispatch", "field-service", "template"],
        skill_ids=[],
        lifecycle_status="configured",
        provider="langchain",
        provider_connection_id=conn.id,
        provider_resource_kind="graph",
        created_at=now,
    )
    db.add(agent)
    db.flush()
    graph = ticketing_dispatch_graph(ticketing_base_url=base_url, model=model)
    db.add(
        LocalGraph(
            id=new_id("lgr"),
            organization_id=org.id,
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
            organization_id=org.id,
            agent_id=agent.id,
            name="ticketing_agent_key",
            value_encrypted=encrypt_secret(settings, agent_key),
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()
    db.refresh(agent)
    logger.info("Ticketing dispatcher agent provisioned for %s", org.slug)
    return agent
