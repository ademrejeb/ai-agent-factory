from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import AuthContext, auth_context
from app.errors import AppError
from app.ids import new_id
from app.models import AuditEvent, Skill
from app.schemas import SkillCreate, SkillUpdate

router = APIRouter(prefix="/api/v1/skills", tags=["skills"])


def skill_out(skill: Skill) -> dict:
    return {
        "id": skill.id,
        "name": skill.name,
        "description": skill.description,
        "instructions": skill.instructions,
        "created_at": skill.created_at.isoformat(),
        "updated_at": skill.updated_at.isoformat(),
    }


def _require_skill(db: Session, ctx: AuthContext, skill_id: str) -> Skill:
    skill = db.get(Skill, skill_id)
    if skill is None or skill.organization_id != ctx.organization.id:
        raise AppError("not_found", "Skill not found.", 404)
    return skill


def _audit(db: Session, ctx: AuthContext, action: str, skill: Skill) -> None:
    db.add(
        AuditEvent(
            id=new_id("aud"),
            organization_id=ctx.organization.id,
            actor_user_id=ctx.user.id,
            action=action,
            resource_type="skill",
            resource_id=skill.id,
            metadata_json={"name": skill.name},
            created_at=datetime.now(UTC),
        )
    )


@router.get("")
def list_skills(
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
) -> dict:
    rows = (
        db.query(Skill)
        .filter(Skill.organization_id == ctx.organization.id)
        .order_by(Skill.name.asc())
        .all()
    )
    return {"items": [skill_out(row) for row in rows]}


@router.post("")
def create_skill(
    body: SkillCreate,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
) -> dict:
    if ctx.role not in {"owner", "admin"}:
        raise AppError("forbidden", "Only owners and admins can create skills.", 403)
    now = datetime.now(UTC)
    skill = Skill(
        id=new_id("skill"),
        organization_id=ctx.organization.id,
        name=body.name.strip(),
        description=body.description,
        instructions=body.instructions,
        created_at=now,
        updated_at=now,
    )
    db.add(skill)
    _audit(db, ctx, "skill.create", skill)
    db.commit()
    db.refresh(skill)
    return skill_out(skill)


@router.patch("/{skill_id}")
def update_skill(
    skill_id: str,
    body: SkillUpdate,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
) -> dict:
    if ctx.role not in {"owner", "admin"}:
        raise AppError("forbidden", "Only owners and admins can edit skills.", 403)
    skill = _require_skill(db, ctx, skill_id)
    if body.name is not None:
        skill.name = body.name.strip()
    if body.description is not None:
        skill.description = body.description
    if body.instructions is not None:
        skill.instructions = body.instructions
    skill.updated_at = datetime.now(UTC)
    _audit(db, ctx, "skill.update", skill)
    db.commit()
    db.refresh(skill)
    return skill_out(skill)


@router.delete("/{skill_id}")
def delete_skill(
    skill_id: str,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
) -> dict:
    if ctx.role not in {"owner", "admin"}:
        raise AppError("forbidden", "Only owners and admins can delete skills.", 403)
    skill = _require_skill(db, ctx, skill_id)
    _audit(db, ctx, "skill.delete", skill)
    db.delete(skill)
    db.commit()
    return {"ok": True}
