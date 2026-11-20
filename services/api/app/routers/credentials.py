from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import AuthContext, auth_context
from app.errors import AppError
from app.ids import new_id
from app.models import ApiCredential
from app.schemas import CredentialCreate
from app.security import generate_customer_secret
from app.services.serialize import credential_out

router = APIRouter(prefix="/api/v1/credentials", tags=["credentials"])


@router.get("")
def list_credentials(ctx: AuthContext = Depends(auth_context), db: Session = Depends(get_db)) -> dict:
    rows = (
        db.query(ApiCredential)
        .filter(ApiCredential.organization_id == ctx.organization.id)
        .order_by(ApiCredential.created_at.desc())
        .all()
    )
    return {"items": [credential_out(r) for r in rows]}


@router.post("")
def create_credential(
    body: CredentialCreate,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
) -> dict:
    if ctx.role not in {"owner", "admin"}:
        raise AppError("forbidden", "Insufficient role.", 403)
    secret, prefix, digest = generate_customer_secret()
    cred = ApiCredential(
        id=new_id("cred"),
        organization_id=ctx.organization.id,
        name=body.name,
        prefix=prefix,
        secret_hash=digest,
        scopes=body.scopes,
        created_at=datetime.now(UTC),
    )
    db.add(cred)
    db.commit()
    db.refresh(cred)
    return credential_out(cred, secret=secret)


@router.post("/{credential_id}/revoke")
def revoke_credential(
    credential_id: str,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
) -> dict:
    if ctx.role not in {"owner", "admin"}:
        raise AppError("forbidden", "Insufficient role.", 403)
    cred = db.get(ApiCredential, credential_id)
    if not cred or cred.organization_id != ctx.organization.id:
        raise AppError("not_found", "Credential not found.", 404)
    cred.revoked_at = datetime.now(UTC)
    db.commit()
    db.refresh(cred)
    return credential_out(cred)
