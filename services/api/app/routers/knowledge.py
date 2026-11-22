from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.deps import AuthContext, auth_context
from app.errors import AppError
from app.ids import new_id
from app.models import (
    AuditEvent,
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
    ProviderConnection,
)
from app.schemas import (
    KnowledgeBaseCreate,
    KnowledgeBaseUpdate,
    KnowledgeDocumentCreate,
    KnowledgeSearchRequest,
)
from app.services.knowledge import (
    format_context,
    ingest_text,
    search_base,
    slugify,
)

router = APIRouter(prefix="/api/v1/knowledge-bases", tags=["knowledge"])


def _base_out(
    db: Session,
    base: KnowledgeBase,
    *,
    include_documents: bool = False,
) -> dict[str, Any]:
    document_count = (
        db.query(func.count(KnowledgeDocument.id))
        .filter(KnowledgeDocument.knowledge_base_id == base.id)
        .scalar()
        or 0
    )
    chunk_count = (
        db.query(func.count(KnowledgeChunk.id))
        .filter(KnowledgeChunk.knowledge_base_id == base.id)
        .scalar()
        or 0
    )
    payload: dict[str, Any] = {
        "id": base.id,
        "name": base.name,
        "slug": base.slug,
        "description": base.description,
        "mode": base.mode,
        "embedding_connection_id": base.embedding_connection_id,
        "embedding_model": base.embedding_model,
        "chunk_size": base.chunk_size,
        "chunk_overlap": base.chunk_overlap,
        "document_count": document_count,
        "chunk_count": chunk_count,
        "created_at": base.created_at.isoformat(),
        "updated_at": base.updated_at.isoformat(),
    }
    if include_documents:
        documents = (
            db.query(KnowledgeDocument)
            .filter(KnowledgeDocument.knowledge_base_id == base.id)
            .order_by(KnowledgeDocument.created_at.desc())
            .all()
        )
        payload["documents"] = [
            {
                "id": doc.id,
                "name": doc.name,
                "source_type": doc.source_type,
                "mime_type": doc.mime_type,
                "size_bytes": doc.size_bytes,
                "chunk_count": doc.chunk_count,
                "created_at": doc.created_at.isoformat(),
            }
            for doc in documents
        ]
    return payload


def _require_base(db: Session, ctx: AuthContext, base_id: str) -> KnowledgeBase:
    base = db.get(KnowledgeBase, base_id)
    if base is None or base.organization_id != ctx.organization.id:
        raise AppError("not_found", "Knowledge base not found.", 404)
    return base


def _audit(
    db: Session,
    ctx: AuthContext,
    action: str,
    *,
    resource_id: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditEvent(
            id=new_id("aud"),
            organization_id=ctx.organization.id,
            actor_user_id=ctx.user.id,
            action=action,
            resource_type="knowledge_base",
            resource_id=resource_id,
            metadata_json=metadata or {},
            created_at=datetime.now(UTC),
        )
    )


def _validate_embedding(
    db: Session,
    ctx: AuthContext,
    connection_id: str | None,
    model: str | None,
    mode: str,
) -> None:
    if mode == "vector":
        if not connection_id or not (model or "").strip():
            raise AppError(
                "embedding_config_required",
                "Vector search needs an embeddings connection and model.",
                400,
            )
    if connection_id:
        connection = db.get(ProviderConnection, connection_id)
        if not connection or connection.organization_id != ctx.organization.id:
            raise AppError("not_found", "Embedding connection not found.", 404)


def _unique_slug(db: Session, organization_id: str, name: str, *, exclude_id: str | None = None) -> str:
    base_slug = slugify(name)
    slug = base_slug
    counter = 2
    while True:
        query = db.query(KnowledgeBase).filter(
            KnowledgeBase.organization_id == organization_id,
            KnowledgeBase.slug == slug,
        )
        if exclude_id:
            query = query.filter(KnowledgeBase.id != exclude_id)
        if query.first() is None:
            return slug
        slug = f"{base_slug}-{counter}"
        counter += 1


@router.get("")
def list_bases(
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
) -> dict:
    rows = (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.organization_id == ctx.organization.id)
        .order_by(KnowledgeBase.name.asc())
        .all()
    )
    return {"items": [_base_out(db, row) for row in rows]}


@router.post("")
def create_base(
    body: KnowledgeBaseCreate,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
) -> dict:
    if ctx.role not in {"owner", "admin"}:
        raise AppError("forbidden", "Only owners and admins can create knowledge bases.", 403)
    _validate_embedding(db, ctx, body.embedding_connection_id, body.embedding_model, body.mode)
    now = datetime.now(UTC)
    base = KnowledgeBase(
        id=new_id("kb"),
        organization_id=ctx.organization.id,
        name=body.name.strip(),
        slug=_unique_slug(db, ctx.organization.id, body.name),
        description=body.description,
        mode=body.mode,
        embedding_connection_id=body.embedding_connection_id,
        embedding_model=(body.embedding_model or "").strip() or None,
        chunk_size=body.chunk_size,
        chunk_overlap=body.chunk_overlap,
        created_at=now,
        updated_at=now,
    )
    db.add(base)
    _audit(db, ctx, "knowledge_base.create", resource_id=base.id, metadata={"name": base.name})
    db.commit()
    db.refresh(base)
    return _base_out(db, base)


@router.get("/{base_id}")
def get_base(
    base_id: str,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
) -> dict:
    return _base_out(db, _require_base(db, ctx, base_id), include_documents=True)


@router.patch("/{base_id}")
def update_base(
    base_id: str,
    body: KnowledgeBaseUpdate,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
) -> dict:
    if ctx.role not in {"owner", "admin"}:
        raise AppError("forbidden", "Only owners and admins can edit knowledge bases.", 403)
    base = _require_base(db, ctx, base_id)

    mode = body.mode or base.mode
    connection_id = (
        body.embedding_connection_id
        if "embedding_connection_id" in body.model_fields_set
        else base.embedding_connection_id
    )
    model = (
        (body.embedding_model or "").strip() or None
        if "embedding_model" in body.model_fields_set
        else base.embedding_model
    )
    _validate_embedding(db, ctx, connection_id, model, mode)

    if body.name is not None:
        base.name = body.name.strip()
        base.slug = _unique_slug(db, ctx.organization.id, base.name, exclude_id=base.id)
    if body.description is not None:
        base.description = body.description
    base.mode = mode
    base.embedding_connection_id = connection_id
    base.embedding_model = model
    if body.chunk_size is not None:
        base.chunk_size = body.chunk_size
    if body.chunk_overlap is not None:
        base.chunk_overlap = body.chunk_overlap
    base.updated_at = datetime.now(UTC)
    _audit(db, ctx, "knowledge_base.update", resource_id=base.id, metadata={"name": base.name})
    db.commit()
    db.refresh(base)
    return _base_out(db, base)


@router.delete("/{base_id}")
def delete_base(
    base_id: str,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
) -> dict:
    if ctx.role not in {"owner", "admin"}:
        raise AppError("forbidden", "Only owners and admins can delete knowledge bases.", 403)
    base = _require_base(db, ctx, base_id)
    db.query(KnowledgeChunk).filter(KnowledgeChunk.knowledge_base_id == base.id).delete()
    db.query(KnowledgeDocument).filter(KnowledgeDocument.knowledge_base_id == base.id).delete()
    _audit(db, ctx, "knowledge_base.delete", resource_id=base.id, metadata={"name": base.name})
    db.delete(base)
    db.commit()
    return {"ok": True}


@router.post("/{base_id}/documents")
def add_document(
    base_id: str,
    body: KnowledgeDocumentCreate,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    if ctx.role not in {"owner", "admin"}:
        raise AppError("forbidden", "Only owners and admins can add documents.", 403)
    base = _require_base(db, ctx, base_id)
    document = ingest_text(
        db,
        settings,
        base,
        name=body.name.strip(),
        text=body.text,
        mime_type=body.mime_type,
        source_type="text",
    )
    _audit(
        db,
        ctx,
        "knowledge_base.document.add",
        resource_id=base.id,
        metadata={"document_id": document.id, "name": document.name},
    )
    db.commit()
    return {
        "document": {
            "id": document.id,
            "name": document.name,
            "chunk_count": document.chunk_count,
            "size_bytes": document.size_bytes,
            "created_at": document.created_at.isoformat(),
        },
        "knowledge_base": _base_out(db, base),
    }


@router.delete("/{base_id}/documents/{document_id}")
def delete_document(
    base_id: str,
    document_id: str,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
) -> dict:
    if ctx.role not in {"owner", "admin"}:
        raise AppError("forbidden", "Only owners and admins can remove documents.", 403)
    base = _require_base(db, ctx, base_id)
    document = db.get(KnowledgeDocument, document_id)
    if not document or document.knowledge_base_id != base.id:
        raise AppError("not_found", "Document not found.", 404)
    db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == document.id).delete()
    _audit(
        db,
        ctx,
        "knowledge_base.document.delete",
        resource_id=base.id,
        metadata={"document_id": document.id, "name": document.name},
    )
    db.delete(document)
    base.updated_at = datetime.now(UTC)
    db.commit()
    return {"ok": True}


@router.post("/{base_id}/search")
def search(
    base_id: str,
    body: KnowledgeSearchRequest,
    ctx: AuthContext = Depends(auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    base = _require_base(db, ctx, base_id)
    results = search_base(db, settings, base, body.query.strip(), body.top_k)
    return {
        "mode": base.mode,
        "query": body.query.strip(),
        "results": [item.as_dict() for item in results],
        "context": format_context(results),
    }
