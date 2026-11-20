from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import AuthContext, auth_context
from app.ids import new_id
from app.models import Workspace
from app.schemas import WorkspaceCreate
from app.services.serialize import workspace_out

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])


@router.get("")
def list_workspaces(
    ctx: AuthContext = Depends(auth_context), db: Session = Depends(get_db)
) -> dict:
    rows = (
        db.query(Workspace)
        .filter(Workspace.organization_id == ctx.organization.id)
        .order_by(Workspace.created_at.asc())
        .all()
    )
    return {"items": [workspace_out(w) for w in rows]}


@router.post("")
def create_workspace(
    body: WorkspaceCreate,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
) -> dict:
    if ctx.role not in {"owner", "admin"}:
        from app.errors import AppError

        raise AppError("forbidden", "Insufficient role.", 403)
    slug_base = "".join(ch.lower() if ch.isalnum() else "-" for ch in body.name).strip("-")[:40]
    ws = Workspace(
        id=new_id("ws"),
        organization_id=ctx.organization.id,
        name=body.name,
        slug=f"{slug_base}-{new_id('s')[-6:]}",
        kind=body.kind if body.kind in {"experiment", "production"} else "experiment",
        created_at=datetime.now(UTC),
    )
    db.add(ws)
    db.commit()
    db.refresh(ws)
    return workspace_out(ws)
