import json
from contextlib import contextmanager
from typing import Any, Iterator

import httpx

from app.errors import AppError


def provider_http_error(provider: str, response: httpx.Response) -> AppError:
    text = response.text[:500]
    return AppError(
        "provider_error",
        f"{provider} returned HTTP {response.status_code}.",
        502,
        {"provider": provider, "status_code": response.status_code, "body": text},
    )


def request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    json: dict[str, Any] | None = None,
    timeout: float,
    provider: str,
) -> httpx.Response:
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.request(method, url, headers=headers, json=json)
    except httpx.TimeoutException as exc:
        raise AppError("provider_timeout", f"{provider} request timed out.", 504) from exc
    except httpx.RequestError as exc:
        raise AppError("provider_unreachable", f"Could not reach {provider}.", 502) from exc
    return response


@contextmanager
def open_stream(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    json: dict[str, Any] | None = None,
    timeout: float,
    provider: str,
) -> Iterator[httpx.Response]:
    """Open an HTTP response as a stream and normalize transport failures.

    The caller owns SSE parsing. Error bodies are read eagerly so the original
    provider envelope survives instead of being replaced by a connection reset.
    """

    client = httpx.Client(timeout=timeout)
    try:
        try:
            request = client.build_request(method, url, headers=headers, json=json)
            response = client.send(request, stream=True)
        except httpx.TimeoutException as exc:
            raise AppError("provider_timeout", f"{provider} stream timed out.", 504) from exc
        except httpx.RequestError as exc:
            raise AppError("provider_unreachable", f"Could not reach {provider}.", 502) from exc
        try:
            if response.status_code >= 400:
                response.read()
                raise provider_http_error(provider, response)
            yield response
        finally:
            response.close()
    finally:
        client.close()


def iter_sse(response: httpx.Response) -> Iterator[tuple[str | None, str]]:
    """Yield ``(event_name, data)`` pairs from a Server-Sent Events response."""

    event: str | None = None
    data_lines: list[str] = []
    for raw in response.iter_lines():
        line = raw.rstrip("\r")
        if not line:
            if data_lines:
                yield event, "\n".join(data_lines)
            event = None
            data_lines = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event = line[6:].strip() or None
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
            continue
        # Some providers emit a bare JSON line without the SSE prefix.
        if line.startswith("{") or line.startswith("["):
            data_lines.append(line)
    if data_lines:
        yield event, "\n".join(data_lines)


def parse_sse_json(data: str) -> dict[str, Any] | None:
    if not data or data.strip() == "[DONE]":
        return None
    try:
        parsed = json.loads(data)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None
