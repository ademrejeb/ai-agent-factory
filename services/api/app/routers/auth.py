from datetime import UTC, datetime

from fastapi import APIRouter, Cookie, Depends, Request, Response
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.deps import current_user
from app.errors import AppError
from app.ids import new_id
from app.models import AuditEvent, Membership, Organization, User, Workspace
from app.schemas import LoginRequest, OrganizationSwitch, RegisterRequest
from app.security import (
    create_access_token,
    create_org_token,
    decode_org_token,
    hash_password,
    verify_password,
)
from app.services.limiter import enforce_rate_limit

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _client_ip(request: Request, settings: Settings) -> str:
    if settings.trust_forwarded_for:
        forwarded = request.headers.get("x-forwarded-for", "")
        hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
        if hops:
            return hops[-1]
    return request.client.host if request.client else "unknown"


def _slug(name: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in name).strip("-")
    return (cleaned or "org")[:60]


def _set_session(response: Response, settings: Settings, user: User, org: Organization) -> None:
    response.set_cookie(
        "factory_session",
        create_access_token(settings, user.id),
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.jwt_ttl_minutes * 60,
    )
    response.set_cookie(
        "factory_org",
        create_org_token(settings, user_id=user.id, organization_id=org.id),
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.jwt_ttl_minutes * 60,
    )


def _organization_rows(db: Session, user: User) -> list[dict]:
    rows = (
        db.query(Membership, Organization)
        .join(Organization, Organization.id == Membership.organization_id)
        .filter(Membership.user_id == user.id)
        .order_by(Organization.name.asc())
        .all()
    )
    return [
        {"id": org.id, "name": org.name, "slug": org.slug, "role": membership.role}
        for membership, org in rows
    ]


@router.post("/register")
def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    ip = _client_ip(request, settings)
    enforce_rate_limit(
        f"auth:register:ip:{ip}",
        settings.register_rate_limit_per_minute,
        window_seconds=300,
    )
    email = body.email.strip().lower()
    if db.query(User).filter(User.email == email).first():
        raise AppError("conflict", "Email already registered.", 409)
    now = datetime.now(UTC)
    user = User(id=new_id("user"), email=email, password_hash=hash_password(body.password), created_at=now)
    org = Organization(
        id=new_id("org"),
        name=body.organization_name.strip(),
        slug=f"{_slug(body.organization_name)}-{new_id('s')[-8:]}",
        created_at=now,
    )
    membership = Membership(
        id=new_id("mem"),
        user_id=user.id,
        organization_id=org.id,
        role="owner",
        created_at=now,
    )
    workspace = Workspace(
        id=new_id("ws"),
        organization_id=org.id,
        name="Experiments",
        slug="experiments",
        kind="experiment",
        created_at=now,
    )
    # Flush the parent rows first. AuditEvent has no ORM relationships, so
    # SQLAlchemy's unit of work does not derive an insert order from its foreign
    # keys; without this it may insert the audit row before the organization on
    # databases that enforce foreign keys (PostgreSQL).
    db.add_all([user, org])
    db.flush()
    db.add_all(
        [
            membership,
            workspace,
            AuditEvent(
                id=new_id("aud"),
                organization_id=org.id,
                actor_user_id=user.id,
                action="auth.register",
                resource_type="organization",
                resource_id=org.id,
                metadata_json={},
                created_at=now,
            ),
        ]
    )
    db.commit()
    _set_session(response, settings, user, org)
    return {
        "user": {"id": user.id, "email": user.email},
        "organization": {"id": org.id, "name": org.name},
        "organizations": _organization_rows(db, user),
        "workspace": {"id": workspace.id, "name": workspace.name},
    }


@router.post("/login")
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    ip = _client_ip(request, settings)
    email = body.email.strip().lower()
    enforce_rate_limit(
        f"auth:login:ip:{ip}",
        settings.login_rate_limit_per_minute,
        window_seconds=60,
    )
    enforce_rate_limit(
        f"auth:login:pair:{ip}:{email}",
        5,
        window_seconds=300,
    )
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise AppError("unauthorized", "Invalid email or password.", 401)
    membership = (
        db.query(Membership)
        .filter(Membership.user_id == user.id)
        .order_by(Membership.created_at.asc())
        .first()
    )
    org = db.get(Organization, membership.organization_id) if membership else None
    if org is None:
        raise AppError("forbidden", "No organization membership.", 403)
    _set_session(response, settings, user, org)
    return {
        "user": {"id": user.id, "email": user.email},
        "organization": {"id": org.id, "name": org.name},
        "role": membership.role,
        "organizations": _organization_rows(db, user),
    }


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie("factory_session")
    response.delete_cookie("factory_org")
    return {"ok": True}


@router.get("/sso/config")
def sso_config(settings: Settings = Depends(get_settings)) -> dict:
    return {
        "enabled": settings.sso_enabled,
        "label": settings.sso_button_label,
        "button_label": settings.sso_button_label,
    }


@router.get("/me")
def me(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    factory_org: str | None = Cookie(default=None),
) -> dict:
    orgs = _organization_rows(db, user)
    if not orgs:
        return {
            "user": {"id": user.id, "email": user.email},
            "organization": None,
            "role": None,
            "organizations": [],
            "sso_enabled": settings.sso_enabled,
        }
    active_id = decode_org_token(settings, factory_org, user_id=user.id) if factory_org else None
    active = next((row for row in orgs if row["id"] == active_id), orgs[0])
    return {
        "user": {"id": user.id, "email": user.email},
        "organization": {"id": active["id"], "name": active["name"]},
        "role": active["role"],
        "organizations": orgs,
        "sso_enabled": settings.sso_enabled,
    }


@router.post("/organization")
def switch_organization(
    body: OrganizationSwitch,
    response: Response,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    membership = (
        db.query(Membership)
        .filter(
            Membership.user_id == user.id,
            Membership.organization_id == body.organization_id,
        )
        .first()
    )
    if membership is None:
        raise AppError("forbidden", "You are not a member of that organization.", 403)
    org = db.get(Organization, membership.organization_id)
    if org is None:
        raise AppError("not_found", "Organization not found.", 404)
    response.set_cookie(
        "factory_org",
        create_org_token(settings, user_id=user.id, organization_id=org.id),
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.jwt_ttl_minutes * 60,
    )
    return {
        "organization": {"id": org.id, "name": org.name},
        "role": membership.role,
        "organizations": _organization_rows(db, user),
    }
