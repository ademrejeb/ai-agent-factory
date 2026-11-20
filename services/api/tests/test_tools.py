import json
from datetime import UTC, datetime

import httpx

from app.config import get_settings
from app.models import Tool
from app.services.tools import discover_mcp_tools, execute_tool


def _tool(kind: str, config: dict) -> Tool:
    now = datetime.now(UTC)
    return Tool(
        id="tool_1",
        organization_id="org_1",
        name="Test tool",
        kind=kind,
        description="",
        config=config,
        headers_encrypted="",
        input_schema={"type": "object", "properties": {}},
        enabled=True,
        created_at=now,
        updated_at=now,
    )


def test_http_tool_renders_arguments_and_parses_json() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = execute_tool(
            get_settings(),
            _tool("http", {"method": "POST", "url": "http://127.0.0.1:8080/items/{{ id }}"}),
            {"id": "42", "q": "hello"},
            allow_private=True,
            http_client=client,
        )
    assert result == {"ok": True}
    assert seen["url"].endswith("/items/42")
    assert seen["body"] == {"id": "42", "q": "hello"}


def test_mcp_tool_initializes_and_reads_sse_response() -> None:
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        calls.append(payload)
        if payload["method"] == "initialize":
            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-06-18"}},
                headers={"mcp-session-id": "sess-1"},
            )
        if payload["method"] == "notifications/initialized":
            return httpx.Response(202)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text=(
                "event: message\n"
                'data: {"jsonrpc":"2.0","id":2,"result":{"content":'
                '[{"type":"text","text":"found"}]}}\n\n'
            ),
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = execute_tool(
            get_settings(),
            _tool(
                "mcp",
                {
                    "server_url": "http://127.0.0.1:8080/mcp",
                    "tool_name": "search",
                    "timeout_seconds": 5,
                },
            ),
            {"q": "E30"},
            allow_private=True,
            http_client=client,
        )
    assert result["content"][0]["text"] == "found"
    assert calls[0]["method"] == "initialize"
    assert calls[-1]["params"] == {"name": "search", "arguments": {"q": "E30"}}


def test_mcp_discovery_parses_tool_list() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        if payload["method"] == "initialize":
            return httpx.Response(400)
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "result": {
                    "tools": [
                        {
                            "name": "lookup",
                            "description": "Look up a code",
                            "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}},
                        }
                    ]
                },
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        items = discover_mcp_tools(
            server_url="http://127.0.0.1:8080/mcp",
            headers={},
            timeout=5,
            allow_private=True,
            http_client=client,
        )
    assert items[0]["name"] == "lookup"
    assert items[0]["input_schema"]["properties"]["q"]["type"] == "string"
