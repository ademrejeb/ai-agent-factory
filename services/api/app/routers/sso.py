"""In-app OIDC single sign-on.

The platform never sends an unauthenticated visitor to an external login page
unless they click the SSO button. Password login stays available. SSO uses the
authorization-code flow with PKCE, validates the ID token issuer/audience, and
provisions users and tenant memberships on first login.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import UTC, datetime
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, Cookie, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.errors import AppError
from app.ids import new_id
from app.models import AuditEvent, Membership, Organization, User
from app.security import (
    create_access_token,
    create_org_token,
    create_sso_state,
    decode_sso_state,
)
from app.services.limiter import enforce_rate_limit

router = APIRouter(prefix="/api/v1/auth/sso", tags=["auth"])

STATE_COOKIE = "factory_sso_state"
ALLOWED_ROLES = {"owner", "admin", "member", "viewer"}


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _discovery(settings: Settings) -> dict:
    issuer = settings.sso_issuer.rstrip("/")
    try:
        response = httpx.get(
            f"{issuer}/.well-known/openid-configuration",
            timeout=15,
            follow_redirects=True,
        )
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise AppError(
            "sso_unavailable",
            "The identity provider discovery document could not be loaded.",
            502,
        ) from exc
    if not isinstance(body, dict):
        raise AppError("sso_unavailable", "Invalid identity provider metadata.", 502)
    return body


def _claim_role(claims: dict, settings: Settings) -> str:
    raw = claims.get(settings.sso_role_claim)
    values = raw if isinstance(raw, list) else [raw]
    for value in values:
        role = str(value or "").strip().lower()
        if role in ALLOWED_ROLES:
            return role
    return settings.sso_default_role if settings.sso_default_role in ALLOWED_ROLES else "member"


def _email_domain(email: str) -> str:
    return email.split("@", 1)[1].lower() if "@" in email else ""


def _tenant_for(db: Session, user: User, email: str, settings: Settings) -> Organization:
    domain = _email_domain(email)
    if domain and domain not in settings.sso_domains and settings.sso_domains:
        raise AppError(
            "forbidden",
            f"Your email domain ({domain}) is not allowed by this workspace.",
            403,
        )
    org = None
    if settings.sso_default_org_slug.strip():
        org = (
            db.query(Organization)
            .filter(Organization.slug == settings.sso_default_org_slug.strip())
            .first()
        )
    if org is None and domain:
        org = db.query(Organization).filter(Organization.sso_domain == domain).first()
    if org is None:
        existing = (
            db.query(Organization)
            .join(Membership, Membership.organization_id == Organization.id)
            .filter(Membership.user_id == user.id)
            .first()
        )
        if existing is not None:
            return existing
    if org is None:
        if not settings.sso_auto_create_org:
            raise AppError("forbidden", "No tenant is configured for this account.", 403)
        name = domain or "Workspace"
        org = Organization(
            id=new_id("org"),
            name=name.replace(".", " ").title(),
            slug=f"{domain.replace('.', '-') or 'sso'}-{new_id('s')[-8:]}",
            sso_domain=domain or None,
            created_at=datetime.now(UTC),
        )
        db.add(org)
        db.flush()
    return org


def _provision(db: Session, claims: dict, settings: Settings) -> tuple[User, Organization]:
    email = str(claims.get("email") or "").strip().lower()
    if not email or "@" not in email:
        raise AppError("sso_invalid", "The identity provider did not return an email address.", 401)
    verified = claims.get("email_verified")
    if verified is False:
        raise AppError("sso_invalid", "The identity provider has not verified this email.", 401)
    now = datetime.now(UTC)
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        user = User(
            id=new_id("user"),
            email=email,
            # SSO-only accounts cannot use password login. An empty hash can
            # never match bcrypt and is explicit rather than a magic sentinel.
            password_hash="",
            created_at=now,
        )
        db.add(user)
        db.flush()
    org = _tenant_for(db, user, email, settings)
    membership = (
        db.query(Membership)
        .filter(Membership.user_id == user.id, Membership.organization_id == org.id)
        .first()
    )
    role = _claim_role(claims, settings)
    if membership is None:
        db.add(
            Membership(
                id=new_id("mem"),
                user_id=user.id,
                organization_id=org.id,
                role=role,
                created_at=now,
            )
        )
    db.add(
        AuditEvent(
            id=new_id("aud"),
            organization_id=org.id,
            actor_user_id=user.id,
            action="auth.sso.login",
            resource_type="organization",
            resource_id=org.id,
            metadata_json={"email": email, "issuer": settings.sso_issuer},
            created_at=now,
        )
    )
    db.commit()
    return user, org


@router.get("/start")
def start(settings: Settings = Depends(get_settings)) -> RedirectResponse:
    if not settings.sso_enabled:
        raise AppError("sso_disabled", "SSO is not configured on this deployment.", 404)
    discovery = _discovery(settings)
    endpoint = discovery.get("authorization_endpoint")
    if not isinstance(endpoint, str):
        raise AppError("sso_unavailable", "Identity provider has no authorization endpoint.", 502)
    nonce = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(64)
    state_id = secrets.token_urlsafe(24)
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    state_cookie = create_sso_state(
        settings,
        state_id=state_id,
        nonce=nonce,
        verifier=verifier,
        redirect="/overview",
    )
    scopes = " ".join(settings.sso_scopes.split())
    query = urlencode(
        {
            "client_id": settings.sso_client_id,
            "response_type": "code",
            "redirect_uri": settings.sso_callback_url,
            "scope": scopes,
            "state": state_id,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    response = RedirectResponse(f"{endpoint}?{query}")
    response.set_cookie(
        STATE_COOKIE,
        state_cookie,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=600,
    )
    return response


@router.get("/callback")
def callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    state_cookie: str | None = Cookie(default=None, alias=STATE_COOKIE),
) -> RedirectResponse:
    web = settings.web_origin.rstrip("/")

    def failure(message: str) -> RedirectResponse:
        detail = f"{message}: {error_description}" if error_description else message
        query = urlencode({"sso_error": detail[:300]})
        return RedirectResponse(f"{web}/login?{query}")

    if not settings.sso_enabled:
        return failure("SSO is not configured")
    if error:
        return failure(error)
    if not code or not state or not state_cookie:
        return failure("The SSO response was incomplete. Try again.")
    try:
        payload = decode_sso_state(settings, state_cookie)
        if not secrets.compare_digest(state, str(payload.get("state_id") or "")):
            return failure("The SSO state did not match. Try again.")
        discovery = _discovery(settings)
        token_endpoint = discovery.get("token_endpoint")
        if not isinstance(token_endpoint, str):
            return failure("Identity provider has no token endpoint")
        response = httpx.post(
            token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.sso_callback_url,
                "client_id": settings.sso_client_id,
                "client_secret": settings.sso_client_secret,
                "code_verifier": payload.get("verifier", ""),
            },
            timeout=20,
        )
        response.raise_for_status()
        tokens = response.json()
        access_token = tokens.get("access_token")
        id_token = tokens.get("id_token")
        claims: dict = {}
        if id_token:
            # Signature validation requires the provider JWKS; pyjwt can fetch
            # it directly from the discovery document's jwks_uri.
            jwks_uri = discovery.get("jwks_uri")
            if not isinstance(jwks_uri, str):
                return failure("Identity provider has no signing keys")
            header = jwt.get_unverified_header(id_token)
            jwks = httpx.get(jwks_uri, timeout=15)
            jwks.raise_for_status()
            key = next(
                (item for item in jwks.json().get("keys", []) if item.get("kid") == header.get("kid")),
                None,
            )
            if key is None:
                return failure("Identity provider signing key was not found")
            claims = jwt.decode(
                id_token,
                jwt.PyJWK(key).key,
                algorithms=[header.get("alg", "RS256")],
                audience=settings.sso_client_id,
                issuer=settings.sso_issuer.rstrip("/"),
                options={"require": ["exp", "iss", "aud"]},
            )
            if payload.get("nonce") and claims.get("nonce") != payload.get("nonce"):
                return failure("SSO nonce mismatch")
        elif access_token:
            userinfo = discovery.get("userinfo_endpoint")
            if not isinstance(userinfo, str):
                return failure("Identity provider has no userinfo endpoint")
            info = httpx.get(
                userinfo,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=20,
            )
            info.raise_for_status()
            claims = info.json()
        else:
            return failure("Identity provider returned no identity token")
        user, org = _provision(db, claims, settings)
    except (httpx.HTTPError, ValueError, AppError, jwt.PyJWTError) as exc:
        message = exc.message if isinstance(exc, AppError) else "SSO login failed."
        return failure(message)

    target = str(payload.get("redirect") or "/overview")
    if not target.startswith("/") or target.startswith("//"):
        target = "/overview"
    redirect = RedirectResponse(f"{web}{target}")
    redirect.set_cookie(
        "factory_session",
        create_access_token(settings, user.id),
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.jwt_ttl_minutes * 60,
    )
    redirect.set_cookie(
        "factory_org",
        create_org_token(settings, user_id=user.id, organization_id=org.id),
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.jwt_ttl_minutes * 60,
    )
    redirect.delete_cookie(STATE_COOKIE, secure=settings.cookie_secure, httponly=True, samesite="lax")
    return redirect


@router.get("/directory")
def directory(
    email: str = Query(min_length=3, max_length=320),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Small discovery helper for the login screen (domain hints only)."""
    if not settings.sso_enabled:
        raise AppError("sso_disabled", "SSO is not configured on this deployment.", 404)
    enforce_rate_limit("sso:directory", 60, window_seconds=60)
    domain = _email_domain(email)
    return {
        "domain": domain,
        "allowed": not settings.sso_domains or domain in settings.sso_domains,
    }
