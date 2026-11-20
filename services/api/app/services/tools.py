"""Reusable tool execution for HTTP endpoints and MCP servers.

Tool definitions are organization-owned. Authorizations live in an encrypted
column and are only decrypted in the control plane, never returned to the UI.
The same executor is used by the Tools page test button and by graph nodes, so
testing a tool proves the path the agent will take.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.config import Settings
from app.errors import AppError
from app.models import Tool
from app.security import decrypt_secret, encrypt_secret
from app.services.local_graph import render_template, render_value
from app.services.net import validate_outbound_url

HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
MAX_MCP_BYTES = 2_000_000


def normalize_tool_config(kind: str, config: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(config, dict):
        raise AppError("invalid_request", "Tool configuration must be an object.", 400)
    if kind == "http":
        method = str(config.get("method") or "GET").upper()
        if method not in HTTP_METHODS:
            raise AppError("invalid_request", "Tool method is not supported.", 400)
        url = str(config.get("url") or "").strip()
        if not url:
            raise AppError("invalid_request", "HTTP tools need a URL.", 400)
        body = config.get("body")
        if body is not None and method in {"GET", "DELETE"}:
            raise AppError(
                "invalid_request", f"{method} tools cannot send a JSON body.", 400
            )
        return {
            "method": method,
            "url": url,
            "body": body,
            "timeout_seconds": min(
                120.0, max(1.0, float(config.get("timeout_seconds") or 30))
            ),
        }
    if kind == "mcp":
        server_url = str(config.get("server_url") or "").strip()
        tool_name = str(config.get("tool_name") or "").strip()
        if not server_url or not tool_name:
            raise AppError(
                "invalid_request",
                "MCP tools need a server URL and a remote tool name.",
                400,
            )
        return {
            "server_url": server_url,
            "tool_name": tool_name,
            "timeout_seconds": min(
                120.0, max(1.0, float(config.get("timeout_seconds") or 30))
            ),
        }
    raise AppError("invalid_request", "Tool kind must be 'http' or 'mcp'.", 400)


def normalize_input_schema(schema: dict[str, Any] | None) -> dict[str, Any]:
    if schema is None or not schema:
        return {"type": "object", "properties": {}, "additionalProperties": True}
    if not isinstance(schema, dict) or schema.get("type", "object") != "object":
        raise AppError(
            "invalid_request",
            "Tool input schema must be a JSON Schema object.",
            400,
        )
    properties = schema.get("properties")
    if properties is not None and not isinstance(properties, dict):
        raise AppError("invalid_request", "input_schema.properties must be an object.", 400)
    return {
        "type": "object",
        "properties": properties or {},
        "required": schema.get("required") or [],
        "additionalProperties": schema.get("additionalProperties", True),
    }


def store_headers(settings: Settings, headers: dict[str, str] | None) -> str:
    clean = {str(key): str(value) for key, value in (headers or {}).items() if str(key).strip()}
    if not clean:
        return ""
    return encrypt_secret(settings, json.dumps(clean))


def load_headers(settings: Settings, tool: Tool) -> dict[str, str]:
    if not tool.headers_encrypted:
        return {}
    try:
        parsed = json.loads(decrypt_secret(settings, tool.headers_encrypted))
    except (ValueError, AppError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(key): str(value) for key, value in parsed.items()}


def tool_out(tool: Tool, settings: Settings) -> dict[str, Any]:
    config = dict(tool.config or {})
    # Never expose the encrypted blob, only the header names so the operator
    # can confirm an authorization is configured.
    header_names = sorted(load_headers(settings, tool).keys())
    config.pop("headers", None)
    return {
        "id": tool.id,
        "name": tool.name,
        "kind": tool.kind,
        "description": tool.description,
        "config": config,
        "input_schema": tool.input_schema,
        "headers_configured": header_names,
        "enabled": tool.enabled,
        "created_at": tool.created_at.isoformat(),
        "updated_at": tool.updated_at.isoformat(),
    }


def _render_headers(headers: dict[str, str], args: dict[str, Any], secrets: dict[str, str]) -> dict[str, str]:
    values = {**args, "secrets": secrets}
    return {key: render_template(value, values) for key, value in headers.items()}


def _render_url(template: str, args: dict[str, Any], secrets: dict[str, str]) -> str:
    return render_template(template, {**args, "secrets": secrets})


def _decode_response(response: httpx.Response, label: str, max_bytes: int) -> Any:
    if len(response.content) > max_bytes:
        raise AppError(
            "tool_response_too_large",
            f"{label} returned more than {max_bytes} bytes.",
            502,
        )
    if response.status_code >= 400:
        preview = response.text[:500]
        raise AppError(
            "tool_failed",
            f"{label} returned HTTP {response.status_code}: {preview}",
            502,
            {"status": response.status_code},
        )
    try:
        return response.json()
    except ValueError:
        return response.text


def _mcp_body(response: httpx.Response) -> Any:
    """Decode a JSON-RPC response, including Streamable HTTP SSE frames."""

    if len(response.content) > MAX_MCP_BYTES:
        raise AppError(
            "tool_response_too_large",
            f"MCP server returned more than {MAX_MCP_BYTES} bytes.",
            502,
        )
    if response.status_code >= 400:
        preview = response.text[:500]
        raise AppError(
            "tool_failed",
            f"MCP server returned HTTP {response.status_code}: {preview}",
            502,
            {"status": response.status_code},
        )
    content_type = response.headers.get("content-type", "")
    if "text/event-stream" not in content_type:
        try:
            return response.json()
        except ValueError as exc:
            raise AppError(
                "tool_failed", "MCP server returned a non-JSON response.", 502
            ) from exc
    last: Any = None
    for block in response.text.replace("\r\n", "\n").split("\n\n"):
        data = "\n".join(
            line[5:].lstrip() for line in block.split("\n") if line.startswith("data:")
        )
        if not data:
            continue
        try:
            last = json.loads(data)
        except ValueError:
            continue
    if last is None:
        raise AppError("tool_failed", "MCP server sent an empty event stream.", 502)
    return last


def call_mcp(
    *,
    server_url: str,
    headers: dict[str, str],
    method: str,
    params: dict[str, Any],
    timeout: float,
    allow_private: bool,
    http_client: httpx.Client | None = None,
) -> Any:
    """Call an MCP tool over Streamable HTTP JSON-RPC.

    Streamable HTTP servers require initialize + notifications/initialized and
    may attach a session id. Plain JSON-RPC servers often reject initialize, so
    a non-2xx initialize falls back to a direct call instead of failing the
    user's tool.
    """

    validate_outbound_url(
        server_url,
        allow_private=allow_private,
        label="MCP server URL",
    )
    common_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        **headers,
    }
    client, owned = (http_client, False) if http_client is not None else (
        httpx.Client(timeout=timeout),
        True,
    )
    try:
        try:
            init = client.post(
                server_url,
                headers=common_headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "ai-agent-factory", "version": "0.1.0"},
                    },
                },
            )
        except httpx.TimeoutException as exc:
            raise AppError("tool_timeout", "MCP server timed out.", 504) from exc
        except httpx.RequestError as exc:
            raise AppError("tool_unreachable", "MCP server is unreachable.", 502) from exc
        session_id = init.headers.get("mcp-session-id")
        if init.status_code < 400 and session_id:
            common_headers["Mcp-Session-Id"] = session_id
        if init.status_code < 400:
            try:
                client.post(
                    server_url,
                    headers=common_headers,
                    json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                )
            except httpx.HTTPError:
                # Notifications are advisory; a server that does not implement
                # them can still answer tools/call.
                pass
        try:
            response = client.post(
                server_url,
                headers=common_headers,
                json={"jsonrpc": "2.0", "id": 2, "method": method, "params": params},
            )
        except httpx.TimeoutException as exc:
            raise AppError("tool_timeout", "MCP server timed out.", 504) from exc
        except httpx.RequestError as exc:
            raise AppError("tool_unreachable", "MCP server is unreachable.", 502) from exc
    finally:
        if owned:
            client.close()
    body = _mcp_body(response)
    if not isinstance(body, dict):
        raise AppError("tool_failed", "MCP server returned an invalid JSON-RPC response.", 502)
    if body.get("error"):
        error = body["error"]
        message = error.get("message") if isinstance(error, dict) else str(error)
        raise AppError("tool_failed", f"MCP tool failed: {message}", 502)
    return body.get("result")


def execute_tool(
    settings: Settings,
    tool: Tool,
    arguments: dict[str, Any],
    *,
    secrets: dict[str, str] | None = None,
    timeout_seconds: float | None = None,
    allow_private: bool | None = None,
    http_client: httpx.Client | None = None,
) -> Any:
    if not tool.enabled:
        raise AppError("tool_disabled", f"Tool '{tool.name}' is disabled.", 409)
    args = arguments if isinstance(arguments, dict) else {}
    secrets = secrets or {}
    headers = _render_headers(load_headers(settings, tool), args, secrets)
    config = tool.config or {}
    allow_private = (
        settings.private_urls_allowed if allow_private is None else allow_private
    )
    if tool.kind == "http":
        method = str(config.get("method") or "GET").upper()
        url = _render_url(str(config.get("url") or ""), args, secrets)
        validate_outbound_url(url, allow_private=allow_private, label="Tool URL")
        timeout = float(timeout_seconds or config.get("timeout_seconds") or 30)
        body = (
            render_value(config.get("body"), {**args, "secrets": secrets})
            if config.get("body") is not None
            else (args if method in {"POST", "PUT", "PATCH"} else None)
        )
        params = args if method == "GET" and not config.get("body") else None
        client, owned = (http_client, False) if http_client is not None else (
            httpx.Client(timeout=timeout),
            True,
        )
        try:
            response = client.request(
                method,
                url,
                headers=headers,
                json=body,
                params=params,
            )
        except httpx.TimeoutException as exc:
            raise AppError("tool_timeout", f"Tool '{tool.name}' timed out.", 504) from exc
        except httpx.RequestError as exc:
            raise AppError("tool_unreachable", f"Tool '{tool.name}' is unreachable.", 502) from exc
        finally:
            if owned:
                client.close()
        return _decode_response(response, f"Tool '{tool.name}'", settings.http_node_max_response_bytes)
    if tool.kind == "mcp":
        return call_mcp(
            server_url=_render_url(str(config.get("server_url") or ""), args, secrets),
            headers=headers,
            method="tools/call",
            params={"name": config.get("tool_name"), "arguments": render_value(args, {**args, "secrets": secrets})},
            timeout=float(timeout_seconds or config.get("timeout_seconds") or 30),
            allow_private=allow_private,
            http_client=http_client,
        )
    raise AppError("invalid_tool", "Tool kind is not supported.", 400)


def call_tool_by_id(
    settings: Settings,
    tools: dict[str, dict[str, Any]],
    tool_id: str,
    arguments: dict[str, Any],
    *,
    secrets: dict[str, str] | None = None,
    allow_private: bool | None = None,
) -> Any:
    """Execute a tool from the runtime snapshot shape (no ORM imports)."""

    tool = tools.get(tool_id)
    if tool is None:
        raise AppError("tool_not_found", f"Tool '{tool_id}' is not available.", 404)
    if not tool.get("enabled", True):
        raise AppError("tool_disabled", f"Tool '{tool.get('name')}' is disabled.", 409)
    class _RuntimeTool:
        name = tool.get("name") or tool_id
        kind = tool.get("kind")
        config = tool.get("config") or {}
        headers_encrypted = ""
        enabled = True

    # The runtime snapshot carries decrypted headers because the execution
    # context already runs server-side; they never leave the API process.
    headers = tool.get("headers") or {}
    args = arguments if isinstance(arguments, dict) else {}
    secrets = secrets or {}
    allow_private = settings.private_urls_allowed if allow_private is None else allow_private
    rendered_headers = _render_headers(headers, args, secrets)
    config = tool.get("config") or {}
    if tool.get("kind") == "http":
        method = str(config.get("method") or "GET").upper()
        url = _render_url(str(config.get("url") or ""), args, secrets)
        validate_outbound_url(url, allow_private=allow_private, label="Tool URL")
        timeout = float(config.get("timeout_seconds") or 30)
        body = (
            render_value(config.get("body"), {**args, "secrets": secrets})
            if config.get("body") is not None
            else (args if method in {"POST", "PUT", "PATCH"} else None)
        )
        params = args if method == "GET" and not config.get("body") else None
        try:
            response = httpx.request(
                method,
                url,
                headers=rendered_headers,
                json=body,
                params=params,
                timeout=timeout,
            )
        except httpx.TimeoutException as exc:
            raise AppError("tool_timeout", f"Tool '{_RuntimeTool.name}' timed out.", 504) from exc
        except httpx.RequestError as exc:
            raise AppError("tool_unreachable", f"Tool '{_RuntimeTool.name}' is unreachable.", 502) from exc
        return _decode_response(
            response, f"Tool '{_RuntimeTool.name}'", settings.http_node_max_response_bytes
        )
    if tool.get("kind") == "mcp":
        return call_mcp(
            server_url=_render_url(str(config.get("server_url") or ""), args, secrets),
            headers=rendered_headers,
            method="tools/call",
            params={"name": config.get("tool_name"), "arguments": render_value(args, {**args, "secrets": secrets})},
            timeout=float(config.get("timeout_seconds") or 30),
            allow_private=allow_private,
        )
    raise AppError("invalid_tool", "Tool kind is not supported.", 400)


def discover_mcp_tools(
    *,
    server_url: str,
    headers: dict[str, str],
    timeout: float,
    allow_private: bool,
    http_client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    result = call_mcp(
        server_url=server_url,
        headers=headers,
        method="tools/list",
        params={},
        timeout=timeout,
        allow_private=allow_private,
        http_client=http_client,
    )
    rows = result.get("tools") if isinstance(result, dict) else result
    if not isinstance(rows, list):
        return []
    items: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("name"):
            continue
        items.append(
            {
                "name": str(row["name"]),
                "description": str(row.get("description") or ""),
                "input_schema": row.get("inputSchema") or {"type": "object", "properties": {}},
            }
        )
    return items
