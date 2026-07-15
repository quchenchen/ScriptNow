"""Smoke tests. If these fail, nothing else will pass.

Purpose:
- Verify the app starts (lifespan runs, DB gets initialized)
- Verify the health endpoint returns 200
- Verify OpenAPI schema is served
"""
from __future__ import annotations


def test_health_endpoint_returns_ok(app_client):
    """GET /api/health returns 200 with a payload identifying the service."""
    response = app_client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "ScriptFlow"


def test_openapi_schema_is_served(app_client):
    """FastAPI's auto-generated OpenAPI schema is reachable."""
    response = app_client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "ScriptFlow"
    # There should be at least the /api/health path
    assert "/api/health" in schema["paths"]
