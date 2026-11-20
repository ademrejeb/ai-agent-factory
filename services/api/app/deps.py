from dataclasses import dataclass

from fastapi import Cookie, Depends, Header
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.errors import AppError
from app.models import ApiCredential, Membership, Organization, User
from app.security import (
    CUSTOMER_KEY_PREFIX,
    decode_access_token,
    decode_org_token,
    hash_api_secret,
)


@dataclass
class AuthContext:
    user: User
    organization: Organization
    membership: Membership
    role: str


def current_user(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    factory_session: str | None = Cookie(default=None),
    authorization: str | None = Header(default=None),
) -> User:
    token = factory_session
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization.split(" ", 1)[1]
        if not bearer.startswith(CUSTOMER_KEY_PREFIX):
            token = bearer
    if not token:
        raise AppError("unauthorized", "Authentication required.", 401)
    user_id = decode_access_token(settings, token)
    user = db.get(User, user_id)
    if not user:
        raise AppError("unauthorized", "User not found.", 401)
    return user


def auth_context(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
    factory_org: str | None = Cookie(default=None),
) -> AuthContext:
    memberships = (
        db.query(Membership)
        .filter(Membership.user_id == user.id)
        .order_by(Membership.created_at.asc())
        .all()
    )
    if not memberships:
        raise AppError("forbidden", "No organization membership.", 403)
    active_id = decode_org_token(settings, factory_org, user_id=user.id) if factory_org else None
    membership = next(
        (row for row in memberships if row.organization_id == active_id),
        memberships[0],
    )
    org = db.get(Organization, membership.organization_id)
    if not org:
        raise AppError("forbidden", "Organization missing.", 403)
    return AuthContext(user=user, organization=org, membership=membership, role=membership.role)


def require_roles(*roles: str):
    def inner(ctx: AuthContext = Depends(auth_context)) -> AuthContext:
        if ctx.role not in roles:
            raise AppError("forbidden", "Insufficient role.", 403)
        return ctx

    return inner


def customer_credential(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
) -> ApiCredential:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AppError("unauthorized", "API credential required.", 401)
    secret = authorization.split(" ", 1)[1].strip()
    if not secret.startswith(CUSTOMER_KEY_PREFIX):
        raise AppError("unauthorized", "Invalid API credential.", 401)
    digest = hash_api_secret(secret)
    cred = db.query(ApiCredential).filter(ApiCredential.secret_hash == digest).first()
    if not cred or cred.revoked_at is not None:
        raise AppError("unauthorized", "Invalid or revoked API credential.", 401)
    return cred
