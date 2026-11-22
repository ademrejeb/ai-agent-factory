"""Knowledge base ingestion, search, and the RAG template."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.providers.base import ConnectivityResult
from app.services.knowledge import chunk_text, cosine, lexical_score


def _lc_ok() -> ConnectivityResult:
    return ConnectivityResult(
        ok=True,
        status="connected",
        capabilities={"execute": True, "streaming": True, "graph": True},
        resource_label="test-model",
        details={"model": "test-model"},
    )


def test_chunking_overlaps_and_stays_bounded() -> None:
    text = ("Refunds are available for 30 days. " * 80).strip()
    chunks = chunk_text(text, size=300, overlap=50)
    assert len(chunks) > 1
    assert all(len(chunk) <= 300 for chunk in chunks)
    # Adjacent chunks share the configured overlap (allowing the boundary trim).
    assert chunks[0][-40:] in chunks[1]


def test_lexical_score_prefers_the_relevant_chunk() -> None:
    relevant = "Annual plans can be refunded within 30 days of purchase."
    unrelated = "The office is closed on public holidays."
    assert lexical_score("annual refund", relevant) > lexical_score("annual refund", unrelated)


def test_cosine_handles_orthogonal_and_identical_vectors() -> None:
    assert cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert cosine([1.0], []) == 0.0


def test_knowledge_base_lifecycle_and_search(client: TestClient, user_a: dict) -> None:
    created = client.post(
        "/api/v1/knowledge-bases",
        json={
            "name": "Support policy",
            "description": "Refund and SLA rules",
            "mode": "lexical",
            "chunk_size": 400,
            "chunk_overlap": 50,
        },
    )
    assert created.status_code == 200, created.text
    base = created.json()
    assert base["mode"] == "lexical"
    assert base["document_count"] == 0

    document = client.post(
        f"/api/v1/knowledge-bases/{base['id']}/documents",
        json={
            "name": "refunds.md",
            "text": (
                "Annual plans can be refunded within 30 days of purchase. "
                "Monthly plans are not refundable. Contact billing@example.com for help."
            ),
        },
    )
    assert document.status_code == 200, document.text
    assert document.json()["document"]["chunk_count"] >= 1

    other = client.post(
        f"/api/v1/knowledge-bases/{base['id']}/documents",
        json={"name": "office.md", "text": "The Tunis office is closed on public holidays."},
    )
    assert other.status_code == 200, other.text

    search = client.post(
        f"/api/v1/knowledge-bases/{base['id']}/search",
        json={"query": "annual refund window", "top_k": 2},
    )
    assert search.status_code == 200, search.text
    results = search.json()["results"]
    assert results
    assert results[0]["document_name"] == "refunds.md"
    assert "30 days" in results[0]["content"]
    assert search.json()["context"].startswith("[1]")

    detail = client.get(f"/api/v1/knowledge-bases/{base['id']}").json()
    assert detail["document_count"] == 2
    assert len(detail["documents"]) == 2

    removed = client.delete(
        f"/api/v1/knowledge-bases/{base['id']}/documents/{results[0]['document_id']}"
    )
    assert removed.status_code == 200
    detail = client.get(f"/api/v1/knowledge-bases/{base['id']}").json()
    assert detail["document_count"] == 1


def test_vector_mode_requires_an_embedding_connection(client: TestClient, user_a: dict) -> None:
    response = client.post(
        "/api/v1/knowledge-bases",
        json={"name": "Vector base", "mode": "vector"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "embedding_config_required"


def test_rag_assistant_template_builds_a_real_graph(client: TestClient, user_a: dict) -> None:
    base = client.post(
        "/api/v1/knowledge-bases",
        json={"name": "Product docs", "mode": "lexical"},
    ).json()
    client.post(
        f"/api/v1/knowledge-bases/{base['id']}/documents",
        json={"name": "plans.md", "text": "The Pro plan includes priority support."},
    )

    with patch(
        "app.providers.langchain.LangChainProvider.check_connectivity",
        return_value=_lc_ok(),
    ):
        connection = client.post(
            "/api/v1/provider-connections",
            json={
                "provider": "langchain",
                "name": "Local model",
                "base_url": "http://localhost:11434/v1",
                "api_key": "ollama",
                "model": "test-model",
            },
        )
    assert connection.status_code == 200, connection.text
    workspace = client.get("/api/v1/workspaces").json()["items"][0]

    created = client.post(
        "/api/v1/agents/from-template",
        json={
            "workspace_id": workspace["id"],
            "name": "Docs assistant",
            "template": "rag_assistant",
            "provider_connection_id": connection.json()["id"],
            "knowledge_base_id": base["id"],
        },
    )
    assert created.status_code == 200, created.text
    agent = created.json()
    assert agent["lifecycle_status"] == "configured"

    graph = client.get(f"/api/v1/agents/{agent['id']}/graph").json()["graph"]
    nodes = graph["nodes"]
    retrieval = next(node for node in nodes.values() if node["type"] == "retrieval")
    assert retrieval["config"]["knowledge_base_id"] == base["id"]
    assert retrieval["config"]["output_key"] == "knowledge"
