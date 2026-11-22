"""Validation and pure helpers for platform-owned LangGraph definitions.

The graph model is deliberately small and explicit:

* exactly one ``input`` node;
* ``llm``, ``http`` and ``condition`` nodes in the middle;
* one or more terminal ``output`` nodes;
* no cycles and no merges, so each output is reached by exactly one path.

Keeping validation pure makes it usable from the API, from publish snapshots,
and from the runtime without importing FastAPI or SQLAlchemy.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any

MAX_NODES = 60
MAX_EDGES = 120
MAX_TEMPLATE_DEPTH = 8

NODE_TYPES = {
    "input",
    "llm",
    "http",
    "condition",
    "tool",
    "agent",
    "guardrail",
    "retrieval",
    "output",
}
HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
ROUTING_HANDLES = {"condition": {"true", "false"}, "guardrail": {"pass", "fail"}}
MAX_AGENT_STEPS = 12
CONDITION_OPERATORS = {
    "exists",
    "not_exists",
    "equals",
    "not_equals",
    "contains",
    "not_contains",
    "gt",
    "gte",
    "lt",
    "lte",
    "truthy",
    "falsy",
    "matches",
    "in",
    "not_in",
}
INPUT_FIELD_TYPES = {"string", "number", "boolean", "object", "array"}
GUARDRAIL_PRESETS = {"", "pii", "prompt_injection", "json_object", "safe_text"}
RESPONSE_FORMATS = {"text", "json_object"}
PII_PATTERNS = (
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "an email address"),
    (re.compile(r"(?<!\d)(?:\+?\d[\d .()-]{7,}\d)(?!\d)"), "a phone number"),
    (re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)"), "a card/IBAN number"),
)
PROMPT_INJECTION_TERMS = (
    "ignore previous instructions",
    "ignore all previous",
    "disregard previous",
    "reveal your system prompt",
    "show your system prompt",
    "you are now",
    "jailbreak",
    "developer mode",
)

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_TEMPLATE_RE = re.compile(r"\{\{\s*([A-Za-z0-9_.\[\]-]+)\s*\}\}")


class GraphValidationError(ValueError):
    """Raised when a graph cannot be saved or executed."""

    def __init__(self, message: str, *, node_id: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.node_id = node_id


class GraphRuntimeError(RuntimeError):
    """Raised when a valid graph fails while executing."""

    def __init__(
        self,
        message: str,
        *,
        node_id: str | None = None,
        steps: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.node_id = node_id
        self.steps = steps or []


def _fail(message: str, node_id: str | None = None) -> None:
    raise GraphValidationError(message, node_id=node_id)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _number(value: Any, label: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(f"{label} must be a number.")
    if minimum is not None and value < minimum:
        _fail(f"{label} must be at least {minimum}.")
    return float(value)


def _normalize_position(raw: Any, node_id: str) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {"x": 0.0, "y": 0.0}
    x = raw.get("x", 0)
    y = raw.get("y", 0)
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        _fail(f"Node '{node_id}' position.x must be a number.", node_id)
    if isinstance(y, bool) or not isinstance(y, (int, float)):
        _fail(f"Node '{node_id}' position.y must be a number.", node_id)
    return {"x": float(x), "y": float(y)}


def _normalize_input_config(config: dict[str, Any], node_id: str) -> dict[str, Any]:
    fields = config.get("fields", [])
    if fields is None:
        fields = []
    if not isinstance(fields, list):
        _fail(f"Input node '{node_id}' config.fields must be a list.", node_id)
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, field in enumerate(fields):
        if not isinstance(field, dict):
            _fail(f"Input field #{index} must be an object.", node_id)
        name = _text(field.get("name"))
        if not name:
            _fail(f"Input field #{index} needs a name.", node_id)
        if name in seen:
            _fail(f"Input field '{name}' is duplicated.", node_id)
        seen.add(name)
        kind = field.get("type", "string")
        if kind not in INPUT_FIELD_TYPES:
            _fail(
                f"Input field '{name}' type must be one of {sorted(INPUT_FIELD_TYPES)}.",
                node_id,
            )
        normalized.append(
            {
                "name": name,
                "type": kind,
                "required": bool(field.get("required", False)),
                "default": field.get("default"),
                "description": str(field.get("description") or ""),
            }
        )
    return {
        "fields": normalized,
        "description": str(config.get("description") or ""),
    }


def _normalize_context(config: dict[str, Any], node_id: str) -> dict[str, Any]:
    raw = config.get("context")
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        _fail(f"Node '{node_id}' context must be an object.", node_id)
    history = bool(raw.get("history", False))
    history_path = _text(raw.get("history_path")) or "history"
    if not _ID_RE.match(history_path.replace(".", "_")):
        _fail(f"Node '{node_id}' context.history_path is invalid.", node_id)
    max_messages = raw.get("max_history_messages", 6)
    if (
        isinstance(max_messages, bool)
        or not isinstance(max_messages, int)
        or not 0 <= max_messages <= 50
    ):
        _fail(f"Node '{node_id}' context.max_history_messages must be 0-50.", node_id)
    max_chars = raw.get("max_context_chars", 8000)
    if (
        isinstance(max_chars, bool)
        or not isinstance(max_chars, int)
        or not 500 <= max_chars <= 50000
    ):
        _fail(f"Node '{node_id}' context.max_context_chars must be 500-50000.", node_id)
    return {
        "history": history,
        "history_path": history_path,
        "max_history_messages": max_messages,
        "max_context_chars": max_chars,
    }


def _normalize_llm_config(config: dict[str, Any], node_id: str) -> dict[str, Any]:
    prompt = config.get("prompt", "")
    if not isinstance(prompt, str) or not prompt.strip():
        _fail(f"LLM node '{node_id}' needs a prompt.", node_id)
    system = config.get("system", "")
    if not isinstance(system, str):
        _fail(f"LLM node '{node_id}' config.system must be a string.", node_id)
    model = config.get("model")
    if model is not None and (not isinstance(model, str) or not model.strip()):
        _fail(f"LLM node '{node_id}' config.model must be a non-empty string.", node_id)
    temperature = config.get("temperature")
    if temperature is not None:
        temperature = _number(temperature, f"LLM node '{node_id}' temperature", minimum=0)
        if temperature > 2:
            _fail(f"LLM node '{node_id}' temperature must be at most 2.", node_id)
    max_tokens = config.get("max_tokens")
    if max_tokens is not None:
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens < 1:
            _fail(f"LLM node '{node_id}' max_tokens must be a positive integer.", node_id)
    output_key = config.get("output_key") or node_id
    if not isinstance(output_key, str) or not _ID_RE.match(output_key):
        _fail(f"LLM node '{node_id}' output_key is invalid.", node_id)
    response_format = config.get("response_format") or "text"
    if response_format not in RESPONSE_FORMATS:
        _fail(f"LLM node '{node_id}' response_format is invalid.", node_id)
    return {
        "prompt": prompt,
        "system": system,
        "model": model.strip() if isinstance(model, str) else None,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "context": _normalize_context(config, node_id),
        "response_format": response_format,
        "output_key": output_key,
    }


def _normalize_http_config(config: dict[str, Any], node_id: str) -> dict[str, Any]:
    method = str(config.get("method") or "GET").upper()
    if method not in HTTP_METHODS:
        _fail(f"HTTP node '{node_id}' method must be one of {sorted(HTTP_METHODS)}.", node_id)
    url = config.get("url")
    if not isinstance(url, str) or not url.strip():
        _fail(f"HTTP node '{node_id}' needs a URL.", node_id)
    headers = config.get("headers", {})
    if headers is None:
        headers = {}
    if not isinstance(headers, dict):
        _fail(f"HTTP node '{node_id}' headers must be an object.", node_id)
    clean_headers: dict[str, str] = {}
    for key, value in headers.items():
        if not isinstance(key, str) or not key.strip():
            _fail(f"HTTP node '{node_id}' header names must be non-empty strings.", node_id)
        clean_headers[key.strip()] = str(value)
    timeout = config.get("timeout_seconds", 30)
    timeout = _number(timeout, f"HTTP node '{node_id}' timeout_seconds", minimum=1)
    if timeout > 120:
        _fail(f"HTTP node '{node_id}' timeout_seconds must be at most 120.", node_id)
    output_key = config.get("output_key") or node_id
    if not isinstance(output_key, str) or not _ID_RE.match(output_key):
        _fail(f"HTTP node '{node_id}' output_key is invalid.", node_id)
    body = config.get("body")
    if body is not None and method in {"GET", "DELETE"}:
        _fail(f"HTTP node '{node_id}' cannot send a body with {method}.", node_id)
    return {
        "method": method,
        "url": url.strip(),
        "headers": clean_headers,
        "body": body,
        "timeout_seconds": timeout,
        "output_key": output_key,
    }


def _normalize_condition_config(config: dict[str, Any], node_id: str) -> dict[str, Any]:
    path = config.get("path")
    if not isinstance(path, str) or not path.strip():
        _fail(f"Condition node '{node_id}' needs a path.", node_id)
    operator = config.get("operator", "truthy")
    if operator not in CONDITION_OPERATORS:
        _fail(
            f"Condition node '{node_id}' operator must be one of "
            f"{sorted(CONDITION_OPERATORS)}.",
            node_id,
        )
    value = config.get("value")
    if operator in {"equals", "not_equals", "contains", "not_contains", "gt", "gte", "lt", "lte", "matches", "in", "not_in"} and value is None:
        _fail(f"Condition node '{node_id}' operator '{operator}' needs a value.", node_id)
    if operator == "matches":
        try:
            re.compile(str(value))
        except re.error as exc:
            _fail(f"Condition node '{node_id}' has an invalid regular expression.", node_id)
            raise exc
    return {"path": path.strip(), "operator": operator, "value": value}


def _string_list(value: Any, *, label: str, node_id: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        _fail(f"{label} must be a list of strings.", node_id)
    return [item.strip() for item in value if item.strip()]


def _normalize_tool_config(config: dict[str, Any], node_id: str) -> dict[str, Any]:
    tool_id = config.get("tool_id")
    if not isinstance(tool_id, str) or not tool_id.strip():
        _fail(f"Tool node '{node_id}' needs a tool.", node_id)
    arguments = config.get("arguments", {})
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        _fail(f"Tool node '{node_id}' arguments must be an object.", node_id)
    output_key = config.get("output_key") or node_id
    if not isinstance(output_key, str) or not _ID_RE.match(output_key):
        _fail(f"Tool node '{node_id}' output_key is invalid.", node_id)
    return {
        "tool_id": tool_id.strip(),
        "arguments": arguments,
        "output_key": output_key,
    }


def _normalize_agent_config(config: dict[str, Any], node_id: str) -> dict[str, Any]:
    prompt = config.get("prompt", "")
    if not isinstance(prompt, str) or not prompt.strip():
        _fail(f"Agent node '{node_id}' needs a prompt.", node_id)
    system = config.get("system", "")
    if not isinstance(system, str):
        _fail(f"Agent node '{node_id}' config.system must be a string.", node_id)
    model = config.get("model")
    if model is not None and (not isinstance(model, str) or not model.strip()):
        _fail(f"Agent node '{node_id}' config.model must be a non-empty string.", node_id)
    temperature = config.get("temperature")
    if temperature is not None:
        temperature = _number(temperature, f"Agent node '{node_id}' temperature", minimum=0)
        if temperature > 2:
            _fail(f"Agent node '{node_id}' temperature must be at most 2.", node_id)
    max_tokens = config.get("max_tokens")
    if max_tokens is not None:
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens < 1:
            _fail(f"Agent node '{node_id}' max_tokens must be a positive integer.", node_id)
    max_steps = config.get("max_steps", 6)
    if isinstance(max_steps, bool) or not isinstance(max_steps, int) or not 1 <= max_steps <= MAX_AGENT_STEPS:
        _fail(
            f"Agent node '{node_id}' max_steps must be between 1 and {MAX_AGENT_STEPS}.",
            node_id,
        )
    output_key = config.get("output_key") or node_id
    if not isinstance(output_key, str) or not _ID_RE.match(output_key):
        _fail(f"Agent node '{node_id}' output_key is invalid.", node_id)
    return {
        "prompt": prompt,
        "system": system,
        "model": model.strip() if isinstance(model, str) else None,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "tool_ids": _string_list(config.get("tool_ids"), label="tool_ids", node_id=node_id),
        "skill_ids": _string_list(config.get("skill_ids"), label="skill_ids", node_id=node_id),
        "max_steps": max_steps,
        "context": _normalize_context(config, node_id),
        "output_key": output_key,
        "final_tool": config.get("final_tool") if isinstance(config.get("final_tool"), str) else None,
    }


def _normalize_guardrail_config(config: dict[str, Any], node_id: str) -> dict[str, Any]:
    path = config.get("path")
    if not isinstance(path, str) or not path.strip():
        _fail(f"Guardrail node '{node_id}' needs a value path.", node_id)
    max_chars = config.get("max_chars")
    if max_chars is not None:
        if isinstance(max_chars, bool) or not isinstance(max_chars, int) or max_chars < 1:
            _fail(f"Guardrail node '{node_id}' max_chars must be a positive integer.", node_id)
    pattern = config.get("pattern")
    if pattern is not None:
        if not isinstance(pattern, str):
            _fail(f"Guardrail node '{node_id}' pattern must be a string.", node_id)
        if pattern:
            try:
                re.compile(pattern)
            except re.error as exc:
                _fail(f"Guardrail node '{node_id}' has an invalid regular expression.", node_id)
                raise exc
    preset = str(config.get("preset") or "")
    if preset not in GUARDRAIL_PRESETS:
        _fail(
            f"Guardrail node '{node_id}' preset must be one of {sorted(GUARDRAIL_PRESETS)}.",
            node_id,
        )
    min_chars = config.get("min_chars")
    if min_chars is not None:
        if isinstance(min_chars, bool) or not isinstance(min_chars, int) or min_chars < 0:
            _fail(f"Guardrail node '{node_id}' min_chars must be a positive integer.", node_id)
    return {
        "path": path.strip(),
        "preset": preset,
        "max_chars": max_chars,
        "deny_terms": _string_list(config.get("deny_terms"), label="deny_terms", node_id=node_id),
        "require_terms": _string_list(
            config.get("require_terms"), label="require_terms", node_id=node_id
        ),
        "pattern": pattern or "",
        "pattern_mode": "allow" if config.get("pattern_mode") == "allow" else "deny",
        "min_chars": min_chars,
        "case_sensitive": bool(config.get("case_sensitive", False)),
    }


def _normalize_retrieval_config(config: dict[str, Any], node_id: str) -> dict[str, Any]:
    knowledge_base_id = config.get("knowledge_base_id")
    if not isinstance(knowledge_base_id, str) or not knowledge_base_id.strip():
        _fail(f"Retrieval node '{node_id}' needs a knowledge base.", node_id)
    query = config.get("query")
    if not isinstance(query, str) or not query.strip():
        _fail(f"Retrieval node '{node_id}' needs a query template.", node_id)
    top_k = config.get("top_k", 5)
    if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 20:
        _fail(f"Retrieval node '{node_id}' top_k must be between 1 and 20.", node_id)
    min_score = config.get("min_score")
    if min_score is not None:
        min_score = _number(min_score, f"Retrieval node '{node_id}' min_score", minimum=0)
        if min_score > 1:
            _fail(f"Retrieval node '{node_id}' min_score must be at most 1.", node_id)
    output_key = config.get("output_key") or node_id
    if not isinstance(output_key, str) or not _ID_RE.match(output_key):
        _fail(f"Retrieval node '{node_id}' output_key is invalid.", node_id)
    return {
        "knowledge_base_id": knowledge_base_id.strip(),
        "query": query,
        "top_k": top_k,
        "min_score": min_score,
        "output_key": output_key,
    }


def _normalize_output_config(config: dict[str, Any], node_id: str) -> dict[str, Any]:
    template = config.get("template")
    path = config.get("path")
    if template is not None and not isinstance(template, str):
        _fail(f"Output node '{node_id}' template must be a string.", node_id)
    if path is not None and not isinstance(path, str):
        _fail(f"Output node '{node_id}' path must be a string.", node_id)
    if isinstance(path, str) and not path.strip():
        path = None
    return {
        "template": template or "",
        "path": path.strip() if isinstance(path, str) else "",
    }


def _normalize_node(raw: Any, node_id: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        _fail(f"Node '{node_id}' must be an object.", node_id)
    if raw.get("id", node_id) != node_id:
        _fail(f"Node key '{node_id}' must match its id field.", node_id)
    kind = raw.get("type")
    if kind not in NODE_TYPES:
        _fail(f"Node '{node_id}' type must be one of {sorted(NODE_TYPES)}.", node_id)
    name = _text(raw.get("name")) or node_id
    config = raw.get("config", {})
    if config is None:
        config = {}
    if not isinstance(config, dict):
        _fail(f"Node '{node_id}' config must be an object.", node_id)
    if kind == "input":
        normalized_config = _normalize_input_config(config, node_id)
    elif kind == "llm":
        normalized_config = _normalize_llm_config(config, node_id)
    elif kind == "http":
        normalized_config = _normalize_http_config(config, node_id)
    elif kind == "condition":
        normalized_config = _normalize_condition_config(config, node_id)
    elif kind == "tool":
        normalized_config = _normalize_tool_config(config, node_id)
    elif kind == "agent":
        normalized_config = _normalize_agent_config(config, node_id)
    elif kind == "guardrail":
        normalized_config = _normalize_guardrail_config(config, node_id)
    elif kind == "retrieval":
        normalized_config = _normalize_retrieval_config(config, node_id)
    else:
        normalized_config = _normalize_output_config(config, node_id)
    return {
        "id": node_id,
        "type": kind,
        "name": name[:120],
        "position": _normalize_position(raw.get("position"), node_id),
        "config": normalized_config,
    }


def validate_graph(nodes: Any, edges: Any) -> dict[str, Any]:
    """Validate and normalize a graph, returning a detached copy.

    Raises :class:`GraphValidationError` with a user-facing message. The
    returned graph is safe to persist; every node has a name, position, and
    normalized config, and every edge has an id and normalized handle.
    """

    if not isinstance(nodes, dict) or not nodes:
        _fail("Graph must contain at least one node.")
    if not isinstance(edges, list):
        _fail("Graph edges must be a list.")
    if len(nodes) > MAX_NODES:
        _fail(f"A graph may contain at most {MAX_NODES} nodes.")
    if len(edges) > MAX_EDGES:
        _fail(f"A graph may contain at most {MAX_EDGES} edges.")

    normalized_nodes: dict[str, dict[str, Any]] = {}
    for node_id, raw in nodes.items():
        if not isinstance(node_id, str) or not _ID_RE.match(node_id):
            _fail(f"Node id '{node_id}' is invalid. Use letters, digits, '_' or '-'.")
        if node_id.startswith("__"):
            _fail(f"Node id '{node_id}' is reserved by the runtime.")
        normalized_nodes[node_id] = _normalize_node(raw, node_id)

    input_nodes = [n for n in normalized_nodes.values() if n["type"] == "input"]
    output_nodes = [n for n in normalized_nodes.values() if n["type"] == "output"]
    if len(input_nodes) != 1:
        _fail("A graph must contain exactly one input node.")
    if not output_nodes:
        _fail("A graph must contain at least one output node.")

    normalized_edges: list[dict[str, Any]] = []
    edge_ids: set[str] = set()
    outgoing: dict[str, list[dict[str, Any]]] = {node_id: [] for node_id in normalized_nodes}
    incoming: dict[str, list[dict[str, Any]]] = {node_id: [] for node_id in normalized_nodes}
    for raw in edges:
        if not isinstance(raw, dict):
            _fail("Each edge must be an object.")
        edge_id = _text(raw.get("id"))
        if not edge_id:
            _fail("Each edge needs a non-empty id.")
        if edge_id in edge_ids:
            _fail(f"Edge id '{edge_id}' is duplicated.")
        edge_ids.add(edge_id)
        source = raw.get("source")
        target = raw.get("target")
        if source not in normalized_nodes or target not in normalized_nodes:
            _fail(f"Edge '{edge_id}' references a node that is not in the graph.")
        handle = raw.get("sourceHandle")
        if handle is not None:
            handle = str(handle).strip() or None
        if handle is not None and handle not in {
            "true",
            "false",
            "pass",
            "fail",
        }:
            _fail(
                f"Edge '{edge_id}' sourceHandle must be true/false, pass/fail, or null."
            )
        edge = {
            "id": edge_id,
            "source": source,
            "target": target,
            "sourceHandle": handle,
        }
        normalized_edges.append(edge)
        outgoing[source].append(edge)
        incoming[target].append(edge)

    for node in normalized_nodes.values():
        node_id = node["id"]
        kind = node["type"]
        out = outgoing[node_id]
        inc = incoming[node_id]
        if kind == "input":
            if inc:
                _fail("The input node cannot have incoming connections.", node_id)
            if len(out) != 1:
                _fail("The input node must connect to exactly one node.", node_id)
        elif kind == "output":
            if out:
                _fail("Output nodes are terminal and cannot have outgoing connections.", node_id)
            if len(inc) != 1:
                _fail("Each output node must have exactly one incoming connection.", node_id)
        elif kind in ROUTING_HANDLES:
            if len(inc) != 1:
                _fail(f"A {kind} node must have exactly one incoming connection.", node_id)
            if len(out) != 2:
                _fail(f"A {kind} node must have exactly two outgoing connections.", node_id)
            expected = sorted(ROUTING_HANDLES[kind])
            handles = sorted(edge["sourceHandle"] for edge in out)
            if handles != expected:
                _fail(
                    f"A {kind} node needs one '{expected[0]}' and one '{expected[1]}' "
                    "outgoing connection.",
                    node_id,
                )
        else:
            if len(inc) != 1:
                _fail(f"{kind.upper()} nodes must have exactly one incoming connection.", node_id)
            if len(out) != 1:
                _fail(f"{kind.upper()} nodes must connect to exactly one next node.", node_id)
            if out[0]["sourceHandle"] is not None:
                _fail(f"{kind.upper()} nodes cannot use a branch handle.", node_id)

    # No merges: every incoming connection was already constrained to one.
    for edge in normalized_edges:
        source_kind = normalized_nodes[edge["source"]]["type"]
        if edge["sourceHandle"] is not None and source_kind not in ROUTING_HANDLES:
            _fail(
                f"Edge '{edge['id']}' uses a branch handle from a non-routing node.",
                edge["source"],
            )

    # Every node reachable from the input.
    seen: set[str] = set()
    stack = [input_nodes[0]["id"]]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(edge["target"] for edge in outgoing[current])
    if seen != set(normalized_nodes):
        missing = sorted(set(normalized_nodes) - seen)
        _fail(f"Every node must be reachable from the input node. Unreachable: {missing}.")

    # Every branch terminates at an output.
    reverse: dict[str, list[str]] = {node_id: [] for node_id in normalized_nodes}
    for edge in normalized_edges:
        reverse[edge["target"]].append(edge["source"])
    terminates: set[str] = set()
    stack = [node["id"] for node in output_nodes]
    while stack:
        current = stack.pop()
        if current in terminates:
            continue
        terminates.add(current)
        stack.extend(reverse[current])
    if terminates != set(normalized_nodes):
        missing = sorted(set(normalized_nodes) - terminates)
        _fail(f"Every branch must terminate in an output node. Missing: {missing}.")

    # Explicit cycle check. The degree rules above make cycles unlikely, but a
    # reader should not have to infer that from the other checks.
    indegree = {node_id: len(incoming[node_id]) for node_id in normalized_nodes}
    ready = [node_id for node_id, degree in indegree.items() if degree == 0]
    visited = 0
    while ready:
        current = ready.pop()
        visited += 1
        for edge in outgoing[current]:
            indegree[edge["target"]] -= 1
            if indegree[edge["target"]] == 0:
                ready.append(edge["target"])
    if visited != len(normalized_nodes):
        _fail("Graphs cannot contain cycles.")

    return {"nodes": normalized_nodes, "edges": normalized_edges}


def default_graph(*, model: str | None = None) -> dict[str, Any]:
    """A minimal, valid starter graph for a newly linked LangChain agent."""

    graph = {
        "nodes": {
            "input": {
                "id": "input",
                "type": "input",
                "name": "Input",
                "position": {"x": 40, "y": 160},
                "config": {
                    "fields": [
                        {
                            "name": "message",
                            "type": "string",
                            "required": True,
                            "default": None,
                            "description": "The user message sent to the graph.",
                        }
                    ],
                    "description": "Values supplied by the caller.",
                },
            },
            "answer": {
                "id": "answer",
                "type": "llm",
                "name": "Answer with the model",
                "position": {"x": 360, "y": 140},
                "config": {
                    "prompt": "{{ message }}",
                    "system": "You are a helpful assistant.",
                    "model": model,
                    "temperature": None,
                    "max_tokens": None,
                    "output_key": "answer",
                },
            },
            "output": {
                "id": "output",
                "type": "output",
                "name": "Output",
                "position": {"x": 680, "y": 160},
                "config": {"template": "", "path": "answer"},
            },
        },
        "edges": [
            {"id": "e_input_answer", "source": "input", "target": "answer", "sourceHandle": None},
            {"id": "e_answer_output", "source": "answer", "target": "output", "sourceHandle": None},
        ],
    }
    return validate_graph(graph["nodes"], graph["edges"])


def resolve_path(values: Any, path: str) -> Any:
    """Resolve ``a.b[0].c`` against nested dictionaries and lists."""

    if not path:
        return values
    current = values
    for part in path.replace("[", ".").replace("]", "").split("."):
        if not part:
            continue
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
        if current is None:
            return None
    return current


def stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    return str(value)


def template_paths(text: str) -> list[str]:
    return _TEMPLATE_RE.findall(text)


def render_template(text: str, values: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        return stringify(resolve_path(values, match.group(1)))

    return _TEMPLATE_RE.sub(replace, text)


def render_value(value: Any, values: dict[str, Any], depth: int = 0) -> Any:
    if depth > MAX_TEMPLATE_DEPTH:
        raise GraphRuntimeError("HTTP body nesting is too deep.")
    if isinstance(value, str):
        match = _TEMPLATE_RE.fullmatch(value.strip())
        if match:
            return resolve_path(values, match.group(1))
        return render_template(value, values)
    if isinstance(value, dict):
        return {key: render_value(item, values, depth + 1) for key, item in value.items()}
    if isinstance(value, list):
        return [render_value(item, values, depth + 1) for item in value]
    return value


def _as_comparable(left: Any, right: Any) -> tuple[Any, Any, bool]:
    if isinstance(left, bool) or isinstance(right, bool):
        return bool(left), bool(right), True
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return float(left), float(right), True
    if isinstance(left, str) and isinstance(right, str):
        try:
            return float(left), float(right), True
        except ValueError:
            return left, right, True
    return left, right, False


def evaluate_condition(config: dict[str, Any], values: dict[str, Any]) -> bool:
    left = resolve_path(values, str(config.get("path") or ""))
    operator = config.get("operator") or "truthy"
    right = render_value(config.get("value"), values)

    if operator == "exists":
        return left is not None and left != ""
    if operator == "not_exists":
        return left is None or left == ""
    if operator == "truthy":
        return bool(left)
    if operator == "falsy":
        return not bool(left)
    if operator == "equals":
        return left == right
    if operator == "not_equals":
        return left != right
    if operator == "contains":
        if isinstance(left, (list, tuple, set)):
            return right in left
        return stringify(right) in stringify(left)
    if operator == "not_contains":
        if isinstance(left, (list, tuple, set)):
            return right not in left
        return stringify(right) not in stringify(left)
    if operator == "matches":
        try:
            return re.search(str(right), stringify(left)) is not None
        except re.error as exc:
            raise GraphRuntimeError("Condition contains an invalid regular expression.") from exc
    if operator == "in":
        if isinstance(right, (list, tuple, set, str, dict)):
            return left in right
        return False
    if operator == "not_in":
        if isinstance(right, (list, tuple, set, str, dict)):
            return left not in right
        return True
    if operator in {"gt", "gte", "lt", "lte"}:
        a, b, comparable = _as_comparable(left, right)
        if not comparable:
            return False
        if operator == "gt":
            return a > b
        if operator == "gte":
            return a >= b
        if operator == "lt":
            return a < b
        return a <= b
    raise GraphRuntimeError(f"Unsupported condition operator '{operator}'.")


def evaluate_guardrail(config: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    """Return a pass/fail decision plus the reasons shown in the run timeline."""

    raw = resolve_path(values, str(config.get("path") or ""))
    text = stringify(raw)
    haystack = text if config.get("case_sensitive") else text.lower()
    reasons: list[str] = []

    preset = str(config.get("preset") or "")
    if preset == "pii":
        for pattern, label in PII_PATTERNS:
            if pattern.search(text):
                reasons.append(f"Contains {label}; remove personal data before continuing.")
    elif preset == "prompt_injection":
        for term in PROMPT_INJECTION_TERMS:
            if term in haystack:
                reasons.append(f"Contains a prompt-injection phrase ('{term}').")
    elif preset == "json_object":
        try:
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                reasons.append("The value must be a JSON object.")
        except ValueError:
            reasons.append("The value is not valid JSON.")

    max_chars = config.get("max_chars")
    if isinstance(max_chars, int) and len(text) > max_chars:
        reasons.append(f"Text is {len(text)} characters; the limit is {max_chars}.")
    min_chars = config.get("min_chars")
    if isinstance(min_chars, int) and len(text) < min_chars:
        reasons.append(f"Text is shorter than the {min_chars}-character minimum.")

    for term in config.get("deny_terms") or []:
        probe = term if config.get("case_sensitive") else term.lower()
        if probe and probe in haystack:
            reasons.append(f"Contains blocked term '{term}'.")
    for term in config.get("require_terms") or []:
        probe = term if config.get("case_sensitive") else term.lower()
        if probe and probe not in haystack:
            reasons.append(f"Missing required term '{term}'.")

    pattern = str(config.get("pattern") or "")
    if pattern:
        try:
            matched = re.search(pattern, text) is not None
        except re.error as exc:
            raise GraphRuntimeError("Guardrail contains an invalid regular expression.") from exc
        if config.get("pattern_mode") == "allow" and not matched:
            reasons.append("Text does not match the required pattern.")
        if config.get("pattern_mode") != "allow" and matched:
            reasons.append("Text matches a blocked pattern.")

    passed = not reasons
    return {
        "passed": passed,
        "reasons": reasons,
        "value": text[:4000],
    }


def clone_graph(graph: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(graph)
