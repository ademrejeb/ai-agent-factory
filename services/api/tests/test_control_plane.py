"""Control-plane endpoints added for the operator UI."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.providers.base import ConnectivityResult, ExecutionResult


def _lc_ok() -> ConnectivityResult:
    return ConnectivityResult(
        ok=True,
        status="connected",
        capabilities={"execute": True, "streaming": True, "graph": True},
        resource_label="test-model",
        details={"model": "test-model"},
    )


def _exec_ok() -> ExecutionResult:
    return ExecutionResult(
        status="completed",
        output={"message": "ok"},
        provider_run_id="msg_1",
        token_count=10,
    )


def _make_agent(client: TestClient, name: str = "Support agent") -> dict:
    ws = client.get("/api/v1/workspaces").json()["items"][0]
    response = client.post("/api/v1/agents", json={"workspace_id": ws["id"], "name": name})
    assert response.status_code == 200, response.text
    return response.json()


def _linked_agent(client: TestClient) -> tuple[dict, dict]:
    with patch(
        "app.providers.langchain.LangChainProvider.check_connectivity",
        return_value=_lc_ok(),
    ):
        conn = client.post(
            "/api/v1/provider-connections",
            json={
                "provider": "langchain",
                "name": "Local model",
                "base_url": "http://localhost:11434/v1",
                "api_key": "ollama",
                "model": "test-model",
            },
        )
        assert conn.status_code == 200, conn.text
        agent = _make_agent(client)
        linked = client.post(
            f"/api/v1/agents/{agent['id']}/link",
            json={"provider_connection_id": conn.json()["id"]},
        )
        assert linked.status_code == 200, linked.text
    return conn.json(), linked.json()


def test_provider_catalog_is_verified_only(client: TestClient, user_a: dict) -> None:
    response = client.get("/api/v1/providers")
    assert response.status_code == 200
    items = {item["id"]: item for item in response.json()["items"]}
    assert set(items) == {"langchain"}
    assert items["langchain"]["requires_model"] is True
    assert items["langchain"]["capabilities"]["agent_loop"] == "verified"


def test_overview_empty_organization_is_honest(client: TestClient, user_a: dict) -> None:
    response = client.get("/api/v1/overview")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["counts"]["runs_total"] == 0
    assert body["counts"]["success_rate"] is None
    assert body["counts"]["p95_latency_ms"] is None
    assert len(body["runs_by_day"]) == 7
    assert body["recent_runs"] == []


def test_agent_patch_and_tenant_isolation(
    client: TestClient, user_a: dict, user_b: dict
) -> None:
    client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "correct-horse-battery"},
    )
    agent = _make_agent(client, "Before")
    updated = client.patch(
        f"/api/v1/agents/{agent['id']}",
        json={"name": "After", "tags": ["billing", " support "]},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "After"
    assert updated.json()["tags"] == ["billing", "support"]

    client.post(
        "/api/v1/auth/login",
        json={"email": "b@example.com", "password": "correct-horse-battery"},
    )
    assert client.patch(f"/api/v1/agents/{agent['id']}", json={"name": "Hijack"}).status_code == 404


def test_tool_and_skill_crud(client: TestClient, user_a: dict) -> None:
    tool = client.post(
        "/api/v1/tools",
        json={
            "name": "Search knowledge base",
            "kind": "http",
            "description": "Looks up an error code.",
            "config": {"method": "GET", "url": "https://example.com/search"},
            "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}},
        },
    )
    assert tool.status_code == 200, tool.text
    assert tool.json()["headers_configured"] == []
    listed = client.get("/api/v1/tools").json()["items"]
    assert [item["name"] for item in listed] == ["Search knowledge base"]

    skill = client.post(
        "/api/v1/skills",
        json={
            "name": "Safety rules",
            "description": "Never invent identifiers.",
            "instructions": "Only use ids returned by a tool.",
        },
    )
    assert skill.status_code == 200, skill.text
    agent = _make_agent(client)
    updated = client.patch(
        f"/api/v1/agents/{agent['id']}", json={"skill_ids": [skill.json()["id"]]}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["skill_ids"] == [skill.json()["id"]]


def test_run_filters_pagination_and_republish(client: TestClient, user_a: dict) -> None:
    with (
        patch("app.providers.langchain.LangChainProvider.check_connectivity", return_value=_lc_ok()),
        patch("app.providers.langchain.LangChainProvider.execute", return_value=_exec_ok()),
    ):
        _, agent = _linked_agent(client)
        assert client.post(f"/api/v1/agents/{agent['id']}/test", json={"input": {"message": "a"}}).status_code == 200
        assert client.post(f"/api/v1/agents/{agent['id']}/test", json={"input": {"message": "b"}}).status_code == 200

        filtered = client.get("/api/v1/runs", params={"status": "completed", "provider": "langchain", "limit": 1})
        assert filtered.status_code == 200
        body = filtered.json()
        assert body["total"] == 2
        assert len(body["items"]) == 1
        assert body["items"][0]["agent_name"] == "Support agent"

        assert client.get("/api/v1/runs", params={"status": "bogus"}).status_code == 400

        published = client.post(f"/api/v1/agents/{agent['id']}/publish")
        assert published.status_code == 200, published.text
        assert published.json()["lifecycle_status"] == "published"
        assert published.json()["deployment"]["health_status"] == "healthy"

        secret = client.post("/api/v1/credentials", json={"name": "ci"}).json()["secret"]
        gateway = client.post(
            f"/api/v1/agents/{agent['id']}/runs",
            json={"input": {"message": "hi"}},
            headers={"Authorization": f"Bearer {secret}"},
        )
        assert gateway.status_code == 200, gateway.text
        assert client.get(f"/api/v1/agents/{agent['id']}").json()["lifecycle_status"] == "monitored"

        republished = client.post(f"/api/v1/agents/{agent['id']}/publish")
        assert republished.status_code == 200, republished.text

        detail = client.get(f"/api/v1/agents/{agent['id']}")
        assert detail.json()["deployment"] is not None
        versions = client.get(f"/api/v1/agents/{agent['id']}/versions").json()
        assert versions["items"][0]["version"] == 2
        deployments = client.get(f"/api/v1/agents/{agent['id']}/deployments").json()
        assert len(deployments["items"]) == 2


def test_run_detail_cross_org_customer_key(
    client: TestClient, user_a: dict, user_b: dict
) -> None:
    client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "correct-horse-battery"},
    )
    with (
        patch("app.providers.langchain.LangChainProvider.check_connectivity", return_value=_lc_ok()),
        patch("app.providers.langchain.LangChainProvider.execute", return_value=_exec_ok()),
    ):
        _, agent = _linked_agent(client)
        client.post(f"/api/v1/agents/{agent['id']}/test", json={"input": {"message": "a"}})
        run_id = client.get("/api/v1/runs").json()["items"][0]["run_id"]
        secret_a = client.post("/api/v1/credentials", json={"name": "a"}).json()["secret"]

    client.post(
        "/api/v1/auth/login",
        json={"email": "b@example.com", "password": "correct-horse-battery"},
    )
    secret_b = client.post("/api/v1/credentials", json={"name": "b"}).json()["secret"]

    assert client.get(f"/api/v1/runs/{run_id}", headers={"Authorization": f"Bearer {secret_a}"}).status_code == 200
    assert client.get(f"/api/v1/runs/{run_id}", headers={"Authorization": f"Bearer {secret_b}"}).status_code == 404


def test_validation_error_shape(client: TestClient, user_a: dict) -> None:
    response = client.post("/api/v1/agents", json={"name": "missing workspace"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    assert response.json()["error"]["details"]["fields"]
