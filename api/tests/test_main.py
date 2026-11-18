from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_ingest_rejects_missing_token():
    r = client.post("/api/deployments", json={
        "commit_sha": "abc123", "image_tag": "v1", "tests_passed": True,
        "vulnerabilities": 0, "status": "success"})
    assert r.status_code == 401


def test_health_unhealthy_without_db():
    r = client.get("/health")
    assert r.status_code == 503