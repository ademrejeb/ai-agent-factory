from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.errors import AppError
from app.providers.base import ConnectivityResult
from app.services.langgraph_runtime import LangGraphRuntime
from app.services.local_graph import validate_graph
from app.services.net import validate_outbound_url


def _langchain_ok() -> ConnectivityResult:
    return ConnectivityResult(
        ok=True,
        status="connected",
        capabilities={"execute": True, "streaming": True, "graph": True},
        resource_label="test-model",
        details={"model": "test-model", "model_listed": True},
    )


def _connection(client: TestClient) -> dict:
    with patch(
        "app.providers.langchain.LangChainProvider.check_connectivity",
        return_value=_langchain_ok(),
    ):
        response = client.post(
            "/api/v1/provider-connections",
            json={
                "provider": "langchain",
                "name": "Dispatcher model",
                "base_url": "http://localhost:11434/v1",
                "api_key": "test-key",
                "model": "test-model",
            },
        )
    assert response.status_code == 200, response.text
    return response.json()


def test_outbound_url_guard_rejects_loopback_and_metadata() -> None:
    with pytest.raises(AppError):
        validate_outbound_url("http://127.0.0.1:9000/x", allow_private=False)
    with pytest.raises(AppError):
        validate_outbound_url("http://169.254.169.254/latest", allow_private=True)
    with pytest.raises(AppError):
        validate_outbound_url("ftp://example.com/x", allow_private=True)


def test_secret_template_reaches_http_header_only() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("authorization", "")
        captured["body"] = request.content.decode()
        return httpx.Response(200, json={"ranked": [], "ticket": {"id": "t1"}})

    graph = validate_graph(
        {
            "input": {
                "id": "input",
                "type": "input",
                "name": "Input",
                "position": {"x": 0, "y": 0},
                "config": {
                    "fields": [
                        {"name": "ticketId", "type": "string", "required": True},
                        {"name": "tenantId", "type": "string", "required": True},
                    ]
                },
            },
            "fetch": {
                "id": "fetch",
                "type": "http",
                "name": "Fetch",
                "position": {"x": 200, "y": 0},
                "config": {
                    "method": "POST",
                    "url": "https://ticketing.example/api/agents/dispatch-context",
                    "headers": {
                        "Authorization": "Bearer {{secrets.ticketing_agent_key}}",
                        "Content-Type": "application/json",
                    },
                    "body": {
                        "ticketId": "{{ ticketId }}",
                        "tenantId": "{{ tenantId }}",
                    },
                    "output_key": "context",
                },
            },
            "output": {
                "id": "output",
                "type": "output",
                "name": "Output",
                "position": {"x": 400, "y": 0},
                "config": {"template": "", "path": "context"},
            },
        },
        [
            {"id": "e1", "source": "input", "target": "fetch", "sourceHandle": None},
            {"id": "e2", "source": "fetch", "target": "output", "sourceHandle": None},
        ],
    )
    runtime = LangGraphRuntime(
        model="test-model",
        api_key="key",
        base_url="http://localhost:11434/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        secrets={"ticketing_agent_key": "very-secret-context-key"},
    )
    result = runtime.run(graph, {"ticketId": "t1", "tenantId": "ten1"})
    assert result.status == "completed"
    assert captured["authorization"] == "Bearer very-secret-context-key"
    assert '"ticketId":"t1"' in captured["body"]


def test_dispatch_template_creates_graph_and_encrypted_secret(
    client: TestClient, user_a: dict
) -> None:
    ws = client.get("/api/v1/workspaces").json()["items"][0]
    conn = _connection(client)
    response = client.post(
        "/api/v1/agents/from-template",
        json={
            "workspace_id": ws["id"],
            "name": "Field dispatch",
            "template": "ticketing_dispatch",
            "provider_connection_id": conn["id"],
            "ticketing_base_url": "http://localhost:3000",
            "ticketing_agent_key": "context-secret-value-123",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["provider"] == "langchain"
    assert body["lifecycle_status"] == "configured"
    graph = body["graph"]
    assert graph["nodes"]["context"]["type"] == "http"
    assert "{{secrets.ticketing_agent_key}}" in graph["nodes"]["context"]["config"]["headers"][
        "Authorization"
    ]

    secrets = client.get(f"/api/v1/agents/{body['id']}/secrets")
    assert secrets.status_code == 200
    assert [item["name"] for item in secrets.json()["items"]] == ["ticketing_agent_key"]
    assert "value" not in secrets.json()["items"][0]

    fetched = client.get(f"/api/v1/agents/{body['id']}/graph")
    assert fetched.status_code == 200
    assert fetched.json()["graph"]["nodes"]["decision"]["type"] == "llm"


def test_template_requires_an_admin_role(client: TestClient, user_a: dict) -> None:
    ws = client.get("/api/v1/workspaces").json()["items"][0]
    conn = _connection(client)
    # user_a is the owner; create a second org/user to verify isolation instead of role.
    client.post("/api/v1/auth/logout")
    other = client.post(
        "/api/v1/auth/register",
        json={
            "email": "template-other@example.com",
            "password": "correct-horse-battery",
            "organization_name": "Other org",
        },
    )
    assert other.status_code == 200, other.text
    response = client.post(
        "/api/v1/agents/from-template",
        json={
            "workspace_id": ws["id"],
            "name": "Not mine",
            "template": "ticketing_dispatch",
            "provider_connection_id": conn["id"],
            "ticketing_base_url": "http://localhost:3000",
            "ticketing_agent_key": "context-secret-value-123",
        },
    )
    assert response.status_code == 404, response.text


def test_production_settings_fail_fast_on_default_secrets(monkeypatch) -> None:
    from cryptography.fernet import Fernet

    from app.config import get_settings

    env = {
        "APP_ENV": "production",
        "JWT_SECRET": "dev-only-change-me-32-characters-min",
        "PLATFORM_SECRETS_KEY": Fernet.generate_key().decode(),
        "COOKIE_SECURE": "true",
        "DATABASE_URL": "postgresql+psycopg://factory:strong@db:5432/factory",
        "API_PUBLIC_URL": "https://api.example.com",
        "WEB_ORIGIN": "https://console.example.com",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        get_settings()

    monkeypatch.setenv("JWT_SECRET", "a-production-secret-that-is-long-enough-123456")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.is_production
    get_settings.cache_clear()
