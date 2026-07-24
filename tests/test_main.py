import os
import tempfile
import pytest

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")

from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db, get_connection

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_db():
    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM deployments")
        conn.commit()
    yield


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_deployment():
    response = client.post(
        "/deployments",
        json={"service": "test-api", "version": "1.0.0", "status": "success"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["service"] == "test-api"
    assert body["status"] == "success"
    assert "timestamp" in body


def test_reject_invalid_status():
    response = client.post(
        "/deployments",
        json={"service": "test-api", "version": "1.0.0", "status": "maybe"},
    )
    assert response.status_code == 422


def test_list_deployments():
    client.post("/deployments", json={"service": "a", "version": "1", "status": "success"})
    client.post("/deployments", json={"service": "b", "version": "1", "status": "failed"})

    response = client.get("/deployments")
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_filter_by_service():
    client.post("/deployments", json={"service": "alpha", "version": "1", "status": "success"})
    client.post("/deployments", json={"service": "beta", "version": "1", "status": "success"})

    response = client.get("/deployments?service=alpha")
    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["service"] == "alpha"


def test_metrics_empty():
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.json()["total_deployments"] == 0


def test_metrics_calculation():
    client.post("/deployments", json={"service": "x", "version": "1", "status": "success"})
    client.post("/deployments", json={"service": "x", "version": "2", "status": "success"})
    client.post("/deployments", json={"service": "x", "version": "3", "status": "failed"})
    client.post("/deployments", json={"service": "y", "version": "1", "status": "success"})

    response = client.get("/metrics")
    body = response.json()
    assert body["total_deployments"] == 4
    assert body["successful"] == 3
    assert body["failed"] == 1
    assert body["success_rate"] == 75.0
    assert len(body["services"]) == 2
