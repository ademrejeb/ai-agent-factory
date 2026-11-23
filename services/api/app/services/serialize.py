from app.models import Agent, AgentVersion, ApiCredential, Deployment, ProviderConnection, Run, Workspace


def workspace_out(ws: Workspace) -> dict:
    return {
        "id": ws.id,
        "name": ws.name,
        "slug": ws.slug,
        "kind": ws.kind,
        "organization_id": ws.organization_id,
        "created_at": ws.created_at.isoformat(),
    }


def connection_out(conn: ProviderConnection) -> dict:
    extra = dict(conn.extra_config or {})
    extra.pop("api_key", None)
    return {
        "id": conn.id,
        "name": conn.name,
        "provider": conn.provider,
        "base_url": conn.base_url,
        "status": conn.status,
        "last_error": conn.last_error,
        "last_checked_at": conn.last_checked_at.isoformat() if conn.last_checked_at else None,
        "capabilities": conn.capabilities,
        "extra_config": extra,
        "has_credentials": True,
        "created_at": conn.created_at.isoformat(),
    }


def agent_out(agent: Agent, deployment: Deployment | None = None) -> dict:
    return {
        "id": agent.id,
        "workspace_id": agent.workspace_id,
        "name": agent.name,
        "description": agent.description,
        "purpose": agent.purpose,
        "tags": agent.tags,
        "skill_ids": agent.skill_ids or [],
        "settings": agent.settings or {},
        "lifecycle_status": agent.lifecycle_status,
        "provider": agent.provider,
        "provider_connection_id": agent.provider_connection_id,
        "provider_resource_id": agent.provider_resource_id,
        "provider_resource_kind": agent.provider_resource_kind,
        "last_sync_error": agent.last_sync_error,
        "archived_at": agent.archived_at.isoformat() if agent.archived_at else None,
        "deployment": deployment_out(deployment) if deployment else None,
        "created_at": agent.created_at.isoformat(),
    }


def deployment_out(dep: Deployment) -> dict:
    return {
        "id": dep.id,
        "status": dep.status,
        "health_status": dep.health_status,
        "environment": dep.environment,
        "last_health_check_at": dep.last_health_check_at.isoformat()
        if dep.last_health_check_at
        else None,
        "last_error": dep.last_error,
        "created_at": dep.created_at.isoformat(),
    }


def run_out(run: Run, agent_name: str | None = None) -> dict:
    return {
        "run_id": run.id,
        "agent_id": run.agent_id,
        "agent_name": agent_name,
        "deployment_id": run.deployment_id,
        "status": run.status,
        "source": run.source,
        "provider": run.provider,
        "provider_run_id": run.provider_run_id,
        "correlation_id": run.correlation_id,
        "input": run.input_summary,
        "output": run.output_summary,
        "error_category": run.error_category,
        "error_message": run.error_message,
        "duration_ms": run.duration_ms,
        "token_count": run.token_count,
        "token_count_is_estimate": run.token_count_is_estimate,
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def version_out(version: AgentVersion) -> dict:
    return {
        "id": version.id,
        "agent_id": version.agent_id,
        "version": version.version,
        "snapshot": version.snapshot,
        "created_at": version.created_at.isoformat(),
    }


def credential_out(cred: ApiCredential, secret: str | None = None) -> dict:
    payload = {
        "id": cred.id,
        "name": cred.name,
        "prefix": cred.prefix,
        "scopes": cred.scopes,
        "revoked_at": cred.revoked_at.isoformat() if cred.revoked_at else None,
        "last_used_at": cred.last_used_at.isoformat() if cred.last_used_at else None,
        "created_at": cred.created_at.isoformat(),
    }
    if secret:
        payload["secret"] = secret
        payload["warning"] = "This secret is shown only once. Store it now."
    return payload
