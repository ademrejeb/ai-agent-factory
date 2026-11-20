"""Verified provider metadata used by the control plane UI.

Only one execution engine remains: the platform-owned LangGraph runtime,
running against an OpenAI-compatible model endpoint. Keeping the catalog
explicit stops the UI from advertising integrations this repository cannot
actually configure end to end.
"""

from typing import Any

PROVIDERS: list[dict[str, Any]] = [
    {
        "id": "langchain",
        "name": "OpenAI-compatible model",
        "summary": "Platform-owned agent graphs with any OpenAI-compatible model, including local Ollama.",
        "setup": (
            "Point the connection at an OpenAI-compatible API root. For Ollama use "
            "http://localhost:11434/v1 with any API key value, then pick a local model "
            "such as qwen2.5:7b or llama3.2:3b. The platform verifies GET /models and "
            "runs every graph with the real model."
        ),
        "base_url_placeholder": "http://localhost:11434/v1",
        "base_url_help": "Include /v1. Ollama, LM Studio, vLLM, LiteLLM, OpenAI, and compatible gateways all work.",
        "auth_field": "api_key",
        "auth_label": "API key (use any value for local Ollama)",
        "requires_workspace_id": False,
        "requires_model": True,
        "resource_kind": "graph",
        "docs_url": "https://platform.openai.com/docs/api-reference",
        "capabilities": {
            "execute": "verified",
            "blocking": "verified",
            "streaming": "verified",
            "graph": "platform_owned",
            "visual_authoring": "verified",
            "run_lookup": "not_supported",
            "resource_creation": "platform_owned",
            "resource_listing": "platform_owned",
            "tools": "http_mcp",
            "agent_loop": "verified",
            "guardrails": "verified",
        },
        "limitations": [
            "The platform executes graphs; it does not host models. The configured endpoint owns model availability and cost.",
            "Connectivity uses GET /models. An endpoint without that route cannot be checked, even if chat completions work.",
            "Async runs are not supported because there is no external queue; blocking and streaming are real.",
            "HTTP and MCP tools make outbound calls. Only trusted operators should edit graphs and tool connections.",
        ],
    },
]

_BY_ID = {item["id"]: item for item in PROVIDERS}


def list_providers() -> list[dict[str, Any]]:
    return PROVIDERS


def get_provider(provider: str) -> dict[str, Any] | None:
    return _BY_ID.get(provider)
