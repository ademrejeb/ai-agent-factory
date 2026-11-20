import os

from cryptography.fernet import Fernet

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["PLATFORM_SECRETS_KEY"] = Fernet.generate_key().decode()
os.environ["JWT_SECRET"] = "test-jwt-secret-which-is-long-enough-123456"
os.environ["APP_ENV"] = "test"
os.environ["WEB_ORIGIN"] = "http://localhost:3100"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.db import engine
from app.main import app
from app.models import Base


@event.listens_for(engine, "connect")
def _enforce_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    """SQLite ignores foreign keys unless enabled per connection.

    PostgreSQL enforces them, so tests must too; otherwise insert-order bugs
    (for example an audit row before its organization) only appear in production.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture(autouse=True)
def _clear_rate_limits():
    """Each test starts with empty in-process limiters."""
    from app.services import limiter

    limiter._hits.clear()
    yield


@pytest.fixture(scope="session")
def client() -> TestClient:
    """Session-scoped test client for in-memory SQLite."""
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture(scope="function")
def clean_db(client: TestClient) -> None:
    """Clean all tables from the test database before and after each function-scoped fixture."""
    # Before: Drop all tables
    Base.metadata.drop_all(bind=engine)
    # Create fresh schema
    Base.metadata.create_all(bind=engine)


@pytest.fixture(scope="function")
def user_a(client: TestClient, clean_db: None) -> dict:
    """Register a test user. Function-scoped ensures fresh registration per test."""
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "a@example.com",
            "password": "correct-horse-battery",
            "organization_name": "Org A",
        },
    )
    assert response.status_code == 200, f"user_a registration failed: {response.text}"
    return response.json()


@pytest.fixture(scope="function")
def user_b(client: TestClient, clean_db: None) -> dict:
    """Register a test user. Function-scoped ensures fresh registration per test."""
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "b@example.com",
            "password": "correct-horse-battery",
            "organization_name": "Org B",
        },
    )
    assert response.status_code == 200, f"user_b registration failed: {response.text}"
    return response.json()