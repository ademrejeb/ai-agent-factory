"""OpenAI-compatible embeddings for knowledge bases.

Embeddings are computed through the same kind of connection the platform
already uses for chat: any endpoint that implements ``POST /embeddings``
(Ollama, LM Studio, vLLM, OpenAI, or a compatible gateway).
"""

from __future__ import annotations

import json
from typing import Any

from app.config import Settings
from app.errors import AppError
from app.models import ProviderConnection
from app.providers.http import request_json
from app.security import decrypt_secret
from app.services.net import validate_outbound_url

EMBED_BATCH = 32
TIMEOUT_SECONDS = 60.0


def _headers(settings: Settings, connection: ProviderConnection) -> dict[str, str]:
    credentials: dict[str, Any] = {}
    raw = decrypt_secret(settings, connection.credentials_encrypted)
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            credentials = parsed
    except ValueError:
        pass
    headers = {"Content-Type": "application/json"}
    key = credentials.get("api_key")
    if isinstance(key, str) and key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _normalize_vectors(payload: Any) -> list[list[float]]:
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        raise AppError(
            "embedding_failed",
            "The embeddings endpoint returned no vectors.",
            502,
        )
    ordered = sorted(
        (row for row in rows if isinstance(row, dict)),
        key=lambda row: row.get("index", 0),
    )
    vectors: list[list[float]] = []
    for row in ordered:
        vector = row.get("embedding")
        if not isinstance(vector, list) or not vector:
            raise AppError("embedding_failed", "An embedding vector was empty.", 502)
        try:
            vectors.append([float(item) for item in vector])
        except (TypeError, ValueError) as exc:
            raise AppError(
                "embedding_failed", "An embedding vector contained non-numeric values.", 502
            ) from exc
    if len(vectors) != len([row for row in rows if isinstance(row, dict)]):
        raise AppError("embedding_failed", "The embeddings response was malformed.", 502)
    return vectors


def embed_texts(
    settings: Settings,
    connection: ProviderConnection,
    model: str,
    texts: list[str],
) -> list[list[float]]:
    """Embed texts in batches, returning one vector per input in order."""
    if not model.strip():
        raise AppError(
            "embedding_model_missing",
            "This knowledge base has no embedding model configured.",
            400,
        )
    if not texts:
        return []

    url = f"{connection.base_url.rstrip('/')}/embeddings"
    validate_outbound_url(
        url,
        allow_private=settings.private_urls_allowed,
        label="Embeddings endpoint",
    )
    headers = _headers(settings, connection)

    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH):
        batch = texts[start : start + EMBED_BATCH]
        response = request_json(
            "POST",
            url,
            headers=headers,
            json={"model": model, "input": batch},
            timeout=TIMEOUT_SECONDS,
            provider="embeddings",
        )
        if response.status_code >= 400:
            raise AppError(
                "embedding_failed",
                f"The embeddings endpoint returned HTTP {response.status_code}.",
                502,
                {"body": response.text[:500]},
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise AppError(
                "embedding_failed", "The embeddings endpoint did not return JSON.", 502
            ) from exc
        batch_vectors = _normalize_vectors(payload)
        if len(batch_vectors) != len(batch):
            raise AppError(
                "embedding_failed",
                "The embeddings endpoint returned a different number of vectors than inputs.",
                502,
            )
        vectors.extend(batch_vectors)

    width = len(vectors[0]) if vectors else 0
    if any(len(vector) != width for vector in vectors):
        raise AppError("embedding_failed", "Embedding vector sizes are inconsistent.", 502)
    return vectors
