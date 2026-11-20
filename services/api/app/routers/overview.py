import math
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import AuthContext, auth_context
from app.lifecycle import FAILED, MONITORED, PUBLISHED
from app.models import Agent, Deployment, ProviderConnection, Run
from app.services.serialize import connection_out, run_out

router = APIRouter(prefix="/api/v1/overview", tags=["overview"])

COMPLETED = "completed"


def _percentile(values: list[int], fraction: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(fraction * len(ordered)))
    return ordered[rank - 1]


def _latest_deployments(db: Session, organization_id: str) -> dict[str, Deployment]:
    rows = (
        db.query(Deployment)
        .filter(Deployment.organization_id == organization_id)
        .order_by(Deployment.created_at.desc())
        .all()
    )
    latest: dict[str, Deployment] = {}
    for row in rows:
        latest.setdefault(row.agent_id, row)
    return latest


def _as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; Postgres returns aware ones."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


@router.get("")
def overview(
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
    days: int = Query(default=7, ge=1, le=90),
) -> dict:
    """Aggregated control-plane metrics computed from persisted rows.

    There is no synthetic data: when the organization has no runs the metrics
    are null/zero and the UI shows an empty state.
    """
    now = datetime.now(UTC)
    window_start = now - timedelta(days=days)
    org_id = ctx.organization.id

    agents = (
        db.query(Agent)
        .filter(Agent.organization_id == org_id, Agent.archived_at.is_(None))
        .all()
    )
    connections = (
        db.query(ProviderConnection)
        .filter(ProviderConnection.organization_id == org_id)
        .order_by(ProviderConnection.created_at.desc())
        .all()
    )
    deployments = _latest_deployments(db, org_id)
    bind = db.get_bind()
    window_start_bind = (
        window_start.replace(tzinfo=None)
        if bind is not None and bind.dialect.name == "sqlite"
        else window_start
    )
    window = db.query(Run).filter(
        Run.organization_id == org_id, Run.started_at >= window_start_bind
    )

    status_counts = dict(
        window.with_entities(Run.status, func.count()).group_by(Run.status).all()
    )
    completed_count = int(status_counts.get(COMPLETED, 0))
    failed_count = int(status_counts.get("failed", 0))
    runs_total = sum(int(value) for value in status_counts.values())

    durations = [
        int(value)
        for (value,) in window.with_entities(Run.duration_ms)
        .filter(Run.duration_ms.isnot(None))
        .all()
        if value is not None
    ]
    reported_tokens = int(
        window.with_entities(
            func.coalesce(
                func.sum(
                    case(
                        (Run.token_count_is_estimate.is_(False), Run.token_count),
                        else_=0,
                    )
                ),
                0,
            )
        ).scalar()
        or 0
    )
    estimated_tokens = int(
        window.with_entities(
            func.coalesce(
                func.sum(
                    case(
                        (Run.token_count_is_estimate.is_(True), Run.token_count),
                        else_=0,
                    )
                ),
                0,
            )
        ).scalar()
        or 0
    )

    by_day_rows = (
        window.with_entities(func.date(Run.started_at), Run.status, func.count())
        .group_by(func.date(Run.started_at), Run.status)
        .all()
    )
    by_day: dict[str, dict[str, int]] = defaultdict(
        lambda: {"completed": 0, "failed": 0, "other": 0}
    )
    for day_value, status_value, count in by_day_rows:
        day = str(day_value)[:10]
        bucket = by_day[day]
        if status_value == COMPLETED:
            bucket["completed"] += int(count)
        elif status_value == "failed":
            bucket["failed"] += int(count)
        else:
            bucket["other"] += int(count)
    series = []
    for offset in range(days - 1, -1, -1):
        day = (now - timedelta(days=offset)).date().isoformat()
        series.append({"date": day, **by_day.get(day, {"completed": 0, "failed": 0, "other": 0})})

    per_agent_rows = (
        window.with_entities(
            Run.agent_id,
            func.count(),
            func.sum(case((Run.status == "failed", 1), else_=0)),
        )
        .group_by(Run.agent_id)
        .order_by(func.count(Run.id).desc())
        .limit(5)
        .all()
    )
    names = {agent.id: agent.name for agent in agents}
    top_agents_out = [
        {
            "agent_id": agent_id,
            "name": names.get(agent_id, "Unknown agent"),
            "runs": int(total),
            "failed": int(failed or 0),
        }
        for agent_id, total, failed in per_agent_rows
    ]

    attention: list[dict] = []
    for agent in agents:
        deployment = deployments.get(agent.id)
        reason = None
        if agent.last_sync_error:
            reason = "Provider link needs attention"
        elif deployment and deployment.health_status == "unhealthy":
            reason = "Latest deployment reported an unhealthy run"
        elif agent.lifecycle_status == FAILED:
            reason = "Agent is in a failed lifecycle state"
        if reason:
            attention.append(
                {
                    "agent_id": agent.id,
                    "name": agent.name,
                    "reason": reason,
                    "lifecycle_status": agent.lifecycle_status,
                }
            )
    attention = attention[:6]

    recent_runs = [
        run_out(run, agent_name=names.get(run.agent_id))
        for run in window.order_by(Run.started_at.desc()).limit(8).all()
    ]
    recent_failures = [
        run_out(run, agent_name=names.get(run.agent_id))
        for run in window.filter(Run.status == "failed")
        .order_by(Run.started_at.desc())
        .limit(6)
        .all()
    ]

    published = sum(1 for agent in agents if agent.lifecycle_status in {PUBLISHED, MONITORED})
    connected = sum(1 for conn in connections if str(conn.status).startswith("connected"))

    return {
        "generated_at": now.isoformat(),
        "window_days": days,
        "counts": {
            "agents_total": len(agents),
            "agents_published": published,
            "agents_needs_attention": len(attention),
            "provider_connections": len(connections),
            "provider_connected": connected,
            "runs_total": runs_total,
            "runs_completed": completed_count,
            "runs_failed": failed_count,
            "success_rate": (
                round(completed_count / runs_total, 4) if runs_total else None
            ),
            "avg_latency_ms": (
                round(sum(durations) / len(durations)) if durations else None
            ),
            "p50_latency_ms": _percentile(durations, 0.5),
            "p95_latency_ms": _percentile(durations, 0.95),
            "tokens_reported": reported_tokens,
            "tokens_estimated": estimated_tokens,
        },
        "runs_by_day": series,
        "top_agents": top_agents_out,
        "recent_runs": recent_runs,
        "recent_failures": recent_failures,
        "attention": attention,
        "provider_connections": [connection_out(conn) for conn in connections],
    }
