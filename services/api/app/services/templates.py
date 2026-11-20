"""Reusable agent blueprints for the console.

Templates create real platform graphs; they do not bypass validation or
execution. The ticketing dispatcher calls the ticketing service's authenticated
context endpoint, then asks the configured model to choose one candidate from
the returned ranking.
"""

from __future__ import annotations

from typing import Any

from app.services.local_graph import validate_graph

TICKETING_DISPATCH = "ticketing_dispatch"

DISPATCH_SYSTEM = (
    "You are a senior field-service dispatcher. You receive one ticket and a "
    "ranked list of real technicians with skill match, travel ETA, current load, "
    "rating, completion history and average resolution time. Choose exactly one "
    "technician from the supplied candidates. Never invent an id. Prefer an "
    "eligible technician with the strongest combined metrics; explain the tradeoffs "
    "in one short paragraph. Return strict JSON only, with no markdown fences: "
    '{"recommended_technician_id": "<id>", "summary": "<one paragraph>", '
    '"reasons": ["..."], "confidence": <0.0-1.0>}'
)

DISPATCH_PROMPT = (
    "Dispatch this request.\n\n"
    "Context JSON:\n{{ context }}\n\n"
    "Return only the JSON object described in the system prompt."
)


def ticketing_dispatch_graph(
    *, ticketing_base_url: str, model: str | None = None
) -> dict[str, Any]:
    base = ticketing_base_url.rstrip("/")
    nodes = {
        "input": {
            "id": "input",
            "type": "input",
            "name": "Ticket input",
            "position": {"x": 40, "y": 180},
            "config": {
                "fields": [
                    {
                        "name": "ticketId",
                        "type": "string",
                        "required": True,
                        "default": None,
                        "description": "Ticketing ticket id.",
                    },
                    {
                        "name": "tenantId",
                        "type": "string",
                        "required": True,
                        "default": None,
                        "description": "Ticketing tenant id.",
                    },
                ],
                "description": "The ticket the dispatcher must assign.",
            },
        },
        "context": {
            "id": "context",
            "type": "http",
            "name": "Load dispatch metrics",
            "position": {"x": 360, "y": 180},
            "config": {
                "method": "POST",
                "url": f"{base}/api/agents/dispatch-context",
                "headers": {
                    "Authorization": "Bearer {{secrets.ticketing_agent_key}}",
                    "Content-Type": "application/json",
                },
                "body": {
                    "ticketId": "{{ ticketId }}",
                    "tenantId": "{{ tenantId }}",
                },
                "timeout_seconds": 20,
                "output_key": "context",
            },
        },
        "decision": {
            "id": "decision",
            "type": "llm",
            "name": "Choose technician",
            "position": {"x": 680, "y": 180},
            "config": {
                "prompt": DISPATCH_PROMPT,
                "system": DISPATCH_SYSTEM,
                "model": model,
                "temperature": 0.1,
                "max_tokens": 700,
                "output_key": "decision",
            },
        },
        "check": {
            "id": "check",
            "type": "guardrail",
            "name": "Guard the decision format",
            "position": {"x": 1000, "y": 180},
            "config": {
                "path": "decision",
                "max_chars": 4000,
                "deny_terms": [],
                "require_terms": ["recommended_technician_id", "summary"],
                "pattern": "",
                "pattern_mode": "deny",
                "min_chars": 10,
                "case_sensitive": False,
            },
        },
        "output": {
            "id": "output",
            "type": "output",
            "name": "Dispatch decision",
            "position": {"x": 1320, "y": 90},
            "config": {"template": "{{ decision }}", "path": None},
        },
        "invalid": {
            "id": "invalid",
            "type": "output",
            "name": "Invalid decision fallback",
            "position": {"x": 1320, "y": 290},
            "config": {
                "template": "{\"error\":\"invalid_decision\",\"summary\":\"The model did not return the required JSON fields.\"}",
                "path": None,
            },
        },
    }
    edges = [
        {
            "id": "e_input_context",
            "source": "input",
            "target": "context",
            "sourceHandle": None,
        },
        {
            "id": "e_context_decision",
            "source": "context",
            "target": "decision",
            "sourceHandle": None,
        },
        {
            "id": "e_decision_check",
            "source": "decision",
            "target": "check",
            "sourceHandle": None,
        },
        {
            "id": "e_check_pass",
            "source": "check",
            "target": "output",
            "sourceHandle": "pass",
        },
        {
            "id": "e_check_fail",
            "source": "check",
            "target": "invalid",
            "sourceHandle": "fail",
        },
    ]
    return validate_graph(nodes, edges)
