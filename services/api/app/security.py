import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken

from app.config import Settings
from app.errors import AppError

CUSTOMER_KEY_PREFIX = "aaf_"


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    # bcrypt silently truncates beyond 72 bytes; reject instead of accepting a
    # password whose suffix has no effect.
    if len(encoded) > 72:
        raise ValueError("Password must be at most 72 bytes.")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    encoded = password.encode("utf-8")
    if len(encoded) > 72:
        return False
    try:
        return bcrypt.checkpw(encoded, password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(settings: Settings, subject: str) -> str:
    exp = datetime.now(UTC) + timedelta(minutes=settings.jwt_ttl_minutes)
    return jwt.encode(
        {"sub": subject, "exp": exp},
        settings.jwt_secret,
        algorithm="HS256",
    )


def decode_access_token(settings: Settings, token: str) -> str:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise AppError("unauthorized", "Invalid or expired session.", 401) from exc
    sub = payload.get("sub")
    if not sub:
        raise AppError("unauthorized", "Invalid session.", 401)
    return str(sub)


def create_org_token(settings: Settings, *, user_id: str, organization_id: str) -> str:
    exp = datetime.now(UTC) + timedelta(minutes=settings.jwt_ttl_minutes)
    return jwt.encode(
        {"sub": user_id, "org": organization_id, "kind": "active_org", "exp": exp},
        settings.jwt_secret,
        algorithm="HS256",
    )


def decode_org_token(settings: Settings, token: str, *, user_id: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    if payload.get("kind") != "active_org" or payload.get("sub") != user_id:
        return None
    organization_id = payload.get("org")
    return str(organization_id) if organization_id else None


def create_sso_state(
    settings: Settings, *, state_id: str, nonce: str, verifier: str, redirect: str
) -> str:
    exp = datetime.now(UTC) + timedelta(minutes=10)
    return jwt.encode(
        {
            "kind": "sso_state",
            "state_id": state_id,
            "nonce": nonce,
            "verifier": verifier,
            "redirect": redirect,
            "exp": exp,
        },
        settings.jwt_secret,
        algorithm="HS256",
    )


def decode_sso_state(settings: Settings, token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise AppError("unauthorized", "The SSO state expired. Try again.", 401) from exc
    if payload.get("kind") != "sso_state":
        raise AppError("unauthorized", "Invalid SSO state.", 401)
    return payload


def fernet_from_settings(settings: Settings) -> Fernet:
    key = settings.platform_secrets_key.strip()
    if not key:
        if settings.is_dev:
            key = Fernet.generate_key().decode()
            object.__setattr__(settings, "platform_secrets_key", key)
        else:
            raise AppError("misconfigured", "PLATFORM_SECRETS_KEY is required.", 500)
    try:
        return Fernet(key.encode("utf-8") if isinstance(key, str) else key)
    except Exception as exc:
        raise AppError("misconfigured", "PLATFORM_SECRETS_KEY is not a valid Fernet key.", 500) from exc


def encrypt_secret(settings: Settings, plaintext: str) -> str:
    return fernet_from_settings(settings).encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(settings: Settings, ciphertext: str) -> str:
    try:
        return fernet_from_settings(settings).decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise AppError("misconfigured", "Unable to decrypt provider credentials.", 500) from exc


def hash_api_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def generate_customer_secret() -> tuple[str, str, str]:
    raw = secrets.token_urlsafe(32)
    secret = f"{CUSTOMER_KEY_PREFIX}{raw}"
    prefix = secret[:12]
    return secret, prefix, hash_api_secret(secret)
