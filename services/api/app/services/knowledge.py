"""Knowledge bases: chunking, embedding, and retrieval.

The search path is deliberately dependency-free: vectors are stored as JSON on
`knowledge_chunks` and scored in Python. A base can also run in `lexical` mode
without any embeddings endpoint, which keeps the feature usable on local models
that do not expose `/embeddings`.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.config import Settings
from app.db import SessionLocal
from app.errors import AppError
from app.ids import new_id
from app.models import (
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
    ProviderConnection,
)
from app.services.embeddings import embed_texts

MAX_CHUNKS_PER_DOCUMENT = 2000
MAX_TOP_K = 20

_WORD_RE = re.compile(r"[0-9a-zàâäçéèêëîïôöùûüÿœæ']+", re.IGNORECASE)
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does", "for",
    "from", "how", "i", "in", "is", "it", "of", "on", "or", "the", "to", "was",
    "what", "when", "where", "which", "who", "why", "with", "you", "your",
    "le", "la", "les", "un", "une", "des", "de", "du", "et", "en", "est", "que",
    "qui", "quel", "quelle", "pour", "dans", "sur", "au", "aux", "ce", "cette",
}


def slugify(value: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:60]
    return base or "knowledge"


def chunk_text(text: str, size: int = 1200, overlap: int = 200) -> list[str]:
    """Split text into overlapping windows, preferring paragraph/line breaks."""
    clean = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not clean:
        return []
    if len(clean) <= size:
        return [clean]

    size = max(200, size)
    overlap = max(0, min(overlap, size - 1))
    chunks: list[str] = []
    start = 0
    while start < len(clean) and len(chunks) < MAX_CHUNKS_PER_DOCUMENT:
        end = min(len(clean), start + size)
        if end < len(clean):
            window = clean[start:end]
            candidates = [window.rfind("\n\n"), window.rfind("\n"), window.rfind(" ")]
            cut = max(candidates)
            if cut >= int(size * 0.55):
                end = start + cut
        piece = clean[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(clean):
            break
        start = max(end - overlap, start + 1)
    return chunks


def _tokens(text: str) -> list[str]:
    return [
        token.lower()
        for token in _WORD_RE.findall(text)
        if len(token) > 1 and token.lower() not in STOPWORDS
    ]


def lexical_score(query: str, content: str) -> float:
    """Deterministic term-coverage score in [0, 1], with a small frequency bonus."""
    query_terms = set(_tokens(query))
    if not query_terms:
        return 0.0
    content_counts = Counter(_tokens(content))

    def matches(term: str) -> bool:
        if term in content_counts:
            return True
        # Cheap stemming: "refund" should match "refunded"/"refunds".
        stem = term[: max(4, len(term) - 2)]
        return any(key.startswith(stem) for key in content_counts)

    covered = sum(1 for term in query_terms if matches(term))
    coverage = covered / len(query_terms)
    hits = sum(content_counts[term] for term in query_terms if term in content_counts)
    return round(coverage * 0.9 + min(hits, 20) / 20 * 0.1, 4)


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return round(dot / (norm_a * norm_b), 4)


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    document_name: str
    ordinal: int
    content: str
    score: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "document_name": self.document_name,
            "ordinal": self.ordinal,
            "content": self.content,
            "score": self.score,
        }


def _embedding_profile(
    db: Session, settings: Settings, base: KnowledgeBase
) -> tuple[ProviderConnection, str] | None:
    if base.mode != "vector" or not base.embedding_connection_id or not base.embedding_model:
        return None
    connection = db.get(ProviderConnection, base.embedding_connection_id)
    if not connection or connection.organization_id != base.organization_id:
        raise AppError(
            "embedding_connection_missing",
            "The knowledge base embedding connection no longer exists.",
            409,
        )
    return connection, base.embedding_model


def search_base(
    db: Session,
    settings: Settings,
    base: KnowledgeBase,
    query: str,
    top_k: int,
) -> list[RetrievedChunk]:
    top_k = max(1, min(top_k, MAX_TOP_K))
    chunks = (
        db.query(KnowledgeChunk, KnowledgeDocument.name)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .filter(KnowledgeChunk.knowledge_base_id == base.id)
        .order_by(KnowledgeChunk.ordinal.asc())
        .limit(settings.knowledge_max_chunks_per_run)
        .all()
    )
    if not chunks:
        return []

    profile = _embedding_profile(db, settings, base)
    query_vector: list[float] | None = None
    if profile is not None:
        connection, model = profile
        query_vector = embed_texts(settings, connection, model, [query])[0]

    scored: list[RetrievedChunk] = []
    for chunk, document_name in chunks:
        if query_vector is not None and isinstance(chunk.embedding, list):
            score = cosine(query_vector, chunk.embedding)
        else:
            score = lexical_score(query, chunk.content)
        if score <= 0:
            continue
        scored.append(
            RetrievedChunk(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                document_name=document_name,
                ordinal=chunk.ordinal,
                content=chunk.content,
                score=score,
            )
        )
    scored.sort(key=lambda item: item.score, reverse=True)
    return scored[:top_k]


def format_context(results: list[RetrievedChunk]) -> str:
    if not results:
        return ""
    blocks = []
    for index, result in enumerate(results, start=1):
        blocks.append(
            f"[{index}] {result.document_name} (relevance {result.score:.2f})\n{result.content}"
        )
    return "\n\n".join(blocks)


def ingest_text(
    db: Session,
    settings: Settings,
    base: KnowledgeBase,
    *,
    name: str,
    text: str,
    mime_type: str = "text/plain",
    source_type: str = "text",
) -> KnowledgeDocument:
    chunks = chunk_text(text, base.chunk_size, base.chunk_overlap)
    if not chunks:
        raise AppError("empty_document", "The document has no readable text.", 400)

    vectors: list[list[float]] | None = None
    profile = _embedding_profile(db, settings, base)
    if profile is not None:
        connection, model = profile
        vectors = embed_texts(settings, connection, model, chunks)

    now = datetime.now(UTC)
    document = KnowledgeDocument(
        id=new_id("kdoc"),
        organization_id=base.organization_id,
        knowledge_base_id=base.id,
        name=name[:240],
        source_type=source_type,
        mime_type=mime_type[:120],
        size_bytes=len(text.encode("utf-8")),
        content=text,
        chunk_count=len(chunks),
        created_at=now,
    )
    db.add(document)
    db.flush()
    for ordinal, content in enumerate(chunks):
        db.add(
            KnowledgeChunk(
                id=new_id("kchk"),
                organization_id=base.organization_id,
                knowledge_base_id=base.id,
                document_id=document.id,
                ordinal=ordinal,
                content=content,
                embedding=vectors[ordinal] if vectors is not None else None,
                created_at=now,
            )
        )
    base.updated_at = now
    db.commit()
    db.refresh(document)
    return document


def make_retriever(
    settings: Settings,
    organization_id: str,
) -> Callable[[str, str, int], dict[str, Any]]:
    """Build the runtime retrieval callback.

    The callback owns its database session so graph execution stays free of
    ORM objects; it re-checks the tenant on every call.
    """

    def retrieve(
        knowledge_base_id: str,
        query: str,
        top_k: int = 5,
        min_score: float | None = None,
    ) -> dict[str, Any]:
        with SessionLocal() as db:
            base = db.get(KnowledgeBase, knowledge_base_id)
            if not base or base.organization_id != organization_id:
                raise AppError(
                    "knowledge_base_missing",
                    "The knowledge base used by this node no longer exists.",
                    409,
                )
            results = search_base(db, settings, base, query, top_k)
            if min_score is not None:
                results = [item for item in results if item.score >= min_score]
            return {
                "mode": base.mode,
                "query": query,
                "context": format_context(results),
                "results": [item.as_dict() for item in results],
            }

    return retrieve


def reembed_base(db: Session, settings: Settings, base: KnowledgeBase) -> int:
    """Recompute embeddings for every chunk of a base.

    Used when a base switches to vector mode or changes embedding model. Runs
    before the caller commits, so a failed embeddings call leaves the previous
    configuration intact after rollback.
    """
    chunks = (
        db.query(KnowledgeChunk)
        .filter(KnowledgeChunk.knowledge_base_id == base.id)
        .order_by(KnowledgeChunk.ordinal.asc())
        .all()
    )
    if not chunks:
        return 0
    profile = _embedding_profile(db, settings, base)
    if profile is None:
        raise AppError(
            "embedding_config_required",
            "Vector search needs an embeddings connection and model.",
            400,
        )
    connection, model = profile
    vectors = embed_texts(settings, connection, model, [chunk.content for chunk in chunks])
    for chunk, vector in zip(chunks, vectors):
        chunk.embedding = vector
    return len(chunks)
