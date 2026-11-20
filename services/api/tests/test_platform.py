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
        output={"message": "Reset via the account page."},
        token_count=12,
        provider_extension={"langchain": {"steps": []}},
    )


def _linked(client: TestClient, name: str = "Password helper") -> dict:
    ws = client.get("/api/v1/workspaces").json()["items"][0]
    with patch(
        "app.providers.langchain.LangChainProvider.check_connectivity",
        return_value=_lc_ok(),
    ):
        conn = client.post(
            "/api/v1/provider-connections",
            json={
                "provider": "langchain",
                "name": "Local Ollama",
                "base_url": "http://localhost:11434/v1",
                "api_key": "ollama",
                "model": "test-model",
            },
        )
        assert conn.status_code == 200, conn.text
        agent = client.post(
            "/api/v1/agents",
            json={"workspace_id": ws["id"], "name": name, "purpose": "Answer questions"},
        ).json()
        linked = client.post(
            f"/api/v1/agents/{agent['id']}/link",
            json={"provider_connection_id": conn.json()["id"]},
        )
        assert linked.status_code == 200, linked.text
        assert linked.json()["lifecycle_status"] == "configured"
    return agent


def test_health(client: TestClient) -> None:
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/ready").json()["status"] == "ready"


def test_register_and_me(client: TestClient, user_a: dict) -> None:
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "a@example.com"
    assert len(me.json()["organizations"]) == 1
    workspaces = client.get("/api/v1/workspaces")
    assert workspaces.status_code == 200
    assert len(workspaces.json()["items"]) == 1


def test_tenant_isolation(client: TestClient, user_a: dict, user_b: dict) -> None:
    client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "correct-horse-battery"},
    )
    ws = client.get("/api/v1/workspaces").json()["items"][0]
    created = client.post(
        "/api/v1/agents",
        json={"workspace_id": ws["id"], "name": "Secret agent", "purpose": "internal"},
    )
    assert created.status_code == 200
    agent_id = created.json()["id"]

    client.post(
        "/api/v1/auth/login",
        json={"email": "b@example.com", "password": "correct-horse-battery"},
    )
    assert client.get(f"/api/v1/agents/{agent_id}").status_code == 404


def test_vertical_slice_with_platform_runtime(client: TestClient, user_a: dict) -> None:
    agent = _linked(client)
    with patch(
        "app.providers.langchain.LangChainProvider.execute", return_value=_exec_ok()
    ):
        tested = client.post(
            f"/api/v1/agents/{agent['id']}/test",
            json={"input": {"message": "How can I reset my password?"}},
        )
        assert tested.status_code == 200, tested.text
        assert tested.json()["status"] == "completed"
        assert tested.json()["output"]["message"] == "Reset via the account page."

        published = client.post(f"/api/v1/agents/{agent['id']}/publish")
        assert published.status_code == 200, published.text
        assert published.json()["lifecycle_status"] == "published"

        cred = client.post("/api/v1/credentials", json={"name": "ci"})
        assert cred.status_code == 200
        secret = cred.json()["secret"]
        assert secret.startswith("aaf_")
        assert "secret" not in client.get("/api/v1/credentials").text

        gateway = client.post(
            f"/api/v1/agents/{agent['id']}/runs",
            json={"input": {"message": "reset"}},
            headers={"Authorization": f"Bearer {secret}"},
        )
        assert gateway.status_code == 200, gateway.text
        assert gateway.json()["status"] == "completed"
        assert len(client.get("/api/v1/runs").json()["items"]) == 2

        fetched = client.get(
            f"/api/v1/runs/{gateway.json()['run_id']}",
            headers={"Authorization": f"Bearer {secret}"},
        )
        assert fetched.status_code == 200


def test_run_correlation_matches_request_id(client: TestClient, user_a: dict) -> None:
    agent = _linked(client, "Correlation agent")
    with patch(
        "app.providers.langchain.LangChainProvider.execute", return_value=_exec_ok()
    ):
        client.post(
            f"/api/v1/agents/{agent['id']}/test", json={"input": {"message": "warm"}}
        )
        client.post(f"/api/v1/agents/{agent['id']}/publish")
        secret = client.post("/api/v1/credentials", json={"name": "corr"}).json()["secret"]
        gateway = client.post(
            f"/api/v1/agents/{agent['id']}/runs",
            json={"input": {"message": "hi"}},
            headers={
                "Authorization": f"Bearer {secret}",
                "X-Request-ID": "corr-gateway-1",
                "Idempotency-Key": "corr-idem-1",
            },
        )
        assert gateway.status_code == 200, gateway.text
        assert gateway.headers["x-request-id"] == "corr-gateway-1"
        assert gateway.json()["correlation_id"] == "corr-gateway-1"
        assert (
            client.get(
                f"/api/v1/runs/{gateway.json()['run_id']}",
                headers={"Authorization": f"Bearer {secret}"},
            ).json()["correlation_id"]
            == "corr-gateway-1"
        )


def test_gateway_rejects_draft(client: TestClient, user_a: dict) -> None:
    ws = client.get("/api/v1/workspaces").json()["items"][0]
    agent = client.post(
        "/api/v1/agents", json={"workspace_id": ws["id"], "name": "Drafty"}
    ).json()
    cred = client.post("/api/v1/credentials", json={"name": "ci"}).json()["secret"]
    response = client.post(
        f"/api/v1/agents/{agent['id']}/runs",
        json={"input": {"message": "hi"}},
        headers={"Authorization": f"Bearer {cred}"},
    )
    assert response.status_code == 409


def test_cross_org_credential(client: TestClient, user_a: dict, user_b: dict) -> None:
    client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "correct-horse-battery"},
    )
    secret_a = client.post("/api/v1/credentials", json={"name": "a"}).json()["secret"]
    ws = client.get("/api/v1/workspaces").json()["items"][0]
    agent_a = client.post(
        "/api/v1/agents", json={"workspace_id": ws["id"], "name": "A"}
    ).json()

    client.post(
        "/api/v1/auth/login",
        json={"email": "b@example.com", "password": "correct-horse-battery"},
    )
    response = client.post(
        f"/api/v1/agents/{agent_a['id']}/runs",
        json={"input": {"message": "nope"}},
        headers={"Authorization": f"Bearer {secret_a}"},
    )
    assert response.status_code in {404, 409}


def test_tenant_switch_requires_membership(
    client: TestClient, user_a: dict, user_b: dict
) -> None:
    client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "correct-horse-battery"},
    )
    org_a = client.get("/api/v1/auth/me").json()["organization"]["id"]
    assert client.post(
        "/api/v1/auth/organization", json={"organization_id": org_a}
    ).status_code == 200
    assert client.post(
        "/api/v1/auth/organization", json={"organization_id": "org_other"}
    ).status_code == 403


def test_sso_config_is_public_and_off_by_default(client: TestClient) -> None:
    response = client.get("/api/v1/auth/sso/config")
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is False
    assert body["button_label"]
