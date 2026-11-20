from datetime import UTC, datetime

from fastapi import APIRouter, Cookie, Depends, Header, Query
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import AuthContext, auth_context
from app.errors import AppError
from app.models import Agent, ApiCredential, Membership, Run, User
from app.security import CUSTOMER_KEY_PREFIX, decode_access_token, hash_api_secret
from app.services.execution import refresh_run
from app.services.serialize import run_out

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])

RUN_STATUSES = {"queued", "running", "completed", "failed", "cancelled"}
RUN_SOURCES = {"test", "gateway"}


def _membership_for_token(db: Session, token: str) -> Membership:
    user_id = decode_access_token(get_settings(), token)
    user = db.get(User, user_id)
    if not user:
        raise AppError("unauthorized", "User not found.", 401)
    membership = db.query(Membership).filter(Membership.user_id == user.id).first()
    if not membership:
        raise AppError("forbidden", "No organization membership.", 403)
    return membership


def _organization_id_for_request(
    db: Session,
    authorization: str | None,
    factory_session: str | None,
) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        if token.startswith(CUSTOMER_KEY_PREFIX):
            digest = hash_api_secret(token)
            cred = db.query(ApiCredential).filter(ApiCredential.secret_hash == digest).first()
            if not cred or cred.revoked_at is not None:
                raise AppError("unauthorized", "Invalid or revoked API credential.", 401)
            if not ({"agents:run", "runs:read"} & set(cred.scopes or [])):
                raise AppError(
                    "forbidden",
                    "Credential lacks agents:run or runs:read scope.",
                    403,
                )
            return cred.organization_id
        return _membership_for_token(db, token).organization_id
    if factory_session:
        return _membership_for_token(db, factory_session).organization_id
    raise AppError("unauthorized", "Authentication required.", 401)


def _parse_datetime(value: str | None, field: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AppError("invalid_request", f"{field} must be an ISO-8601 timestamp.", 400) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _bind_datetime(db: Session, value: datetime | None) -> datetime | None:
    """SQLite stores timezone-naive datetimes; Postgres keeps the tz."""
    if value is None:
        return None
    bind = db.get_bind()
    if bind is not None and bind.dialect.name == "sqlite":
        return value.replace(tzinfo=None)
    return value


def _agent_names(db: Session, runs: list[Run]) -> dict[str, str]:
    ids = {run.agent_id for run in runs}
    if not ids:
        return {}
    rows = db.query(Agent.id, Agent.name).filter(Agent.id.in_(ids)).all()
    return {row.id: row.name for row in rows}


@router.get("")
def list_runs(
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
    status: str | None = None,
    agent_id: str | None = None,
    provider: str | None = None,
    source: str | None = None,
    started_after: str | None = None,
    started_before: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    q = db.query(Run).filter(Run.organization_id == ctx.organization.id)
    if status:
        if status not in RUN_STATUSES:
            raise AppError("invalid_request", "Unknown run status filter.", 400)
        q = q.filter(Run.status == status)
    if agent_id:
        q = q.filter(Run.agent_id == agent_id)
    if provider:
        q = q.filter(Run.provider == provider)
    if source:
        if source not in RUN_SOURCES:
            raise AppError("invalid_request", "Unknown run source filter.", 400)
        q = q.filter(Run.source == source)
    after = _parse_datetime(started_after, "started_after")
    before = _parse_datetime(started_before, "started_before")
    if after:
        q = q.filter(Run.started_at >= _bind_datetime(db, after))
    if before:
        q = q.filter(Run.started_at <= _bind_datetime(db, before))

    total = q.count()
    rows = q.order_by(Run.started_at.desc()).offset(offset).limit(limit).all()
    names = _agent_names(db, rows)
    return {
        "items": [run_out(row, agent_name=names.get(row.agent_id)) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{run_id}")
def get_run(
    run_id: str,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    factory_session: str | None = Cookie(default=None),
) -> dict:
    org_id = _organization_id_for_request(db, authorization, factory_session)
    run = db.get(Run, run_id)
    if not run or run.organization_id != org_id:
        raise AppError("not_found", "Run not found.", 404)
    if run.status in {"queued", "running"} and run.provider_run_id:
        run = refresh_run(db, get_settings(), run)
    agent = db.get(Agent, run.agent_id)
    return run_out(run, agent_name=agent.name if agent else None)
