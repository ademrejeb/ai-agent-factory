"""Validation and defaults for the per-agent runtime settings.

Settings are stored as JSON on ``agents.settings`` so the model, context window,
guardrails and RAG attachment can evolve without a table per knob. Everything is
re-normalised on write and again before a run so old rows stay safe.
"""

from __future__ import annotations

from typing import Any

from app.services.local_graph import GUARDRAIL_PRESETS

MAX_KNOWLEDGE_BASES = 10

_NUMBER_RULES: tuple[tuple[str, float, float, type], ...] = (
    ("temperature", 0.0, 2.0, float),
    ("max_tokens", 1, 32_000, int),
    ("context_window_tokens", 512, 200_000, int),
    ("max_history_messages", 0, 50, int),
    ("rag_top_k", 1, 20, int),
    ("rag_min_score", 0.0, 1.0, float),
)


def normalize_agent_settings(raw: Any) -> dict[str, Any]:
    """Return only known, in-range settings. Unknown keys are dropped."""

    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}

    model = raw.get("model")
    if isinstance(model, str) and model.strip():
        out["model"] = model.strip()[:200]

    for key, low, high, cast in _NUMBER_RULES:
        value = raw.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            out[key] = min(high, max(low, cast(value)))

    for key in ("guardrail_input", "guardrail_output"):
        value = raw.get(key)
        if isinstance(value, str) and value in GUARDRAIL_PRESETS and value:
            out[key] = value

    deny_terms = raw.get("deny_terms")
    if isinstance(deny_terms, list):
        out["deny_terms"] = [
            term.strip()[:80]
            for term in deny_terms
            if isinstance(term, str) and term.strip()
        ][:20]

    kb_ids = raw.get("knowledge_base_ids")
    if isinstance(kb_ids, list):
        out["knowledge_base_ids"] = [
            item
            for item in kb_ids
            if isinstance(item, str) and 0 < len(item) <= 64
        ][:MAX_KNOWLEDGE_BASES]

    system_prompt = raw.get("system_prompt")
    if isinstance(system_prompt, str) and system_prompt.strip():
        out["system_prompt"] = system_prompt.strip()[:8000]

    embedding_model = raw.get("embedding_model")
    if isinstance(embedding_model, str) and embedding_model.strip():
        out["embedding_model"] = embedding_model.strip()[:200]

    return out


def guardrail_config(settings: dict[str, Any], scope: str) -> dict[str, Any] | None:
    """Build the evaluator config for an agent-level input/output guardrail."""

    preset = settings.get(f"guardrail_{scope}") or ""
    deny_terms = settings.get("deny_terms") or []
    if not preset and not deny_terms:
        return None
    return {
        "path": scope,
        "preset": preset,
        "deny_terms": list(deny_terms),
        "case_sensitive": False,
    }
