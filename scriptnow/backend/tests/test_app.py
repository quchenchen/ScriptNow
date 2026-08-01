from fastapi.testclient import TestClient

from scriptnow.app import create_app


def test_health_exposes_both_isolated_domains() -> None:
    response = TestClient(create_app()).get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "domains": {
            "script": ["action", "character", "dialogue", "slugline", "transition"],
            "novel": ["dialogue", "divider", "heading", "prose", "quote"],
        },
    }


def test_cross_cultural_recreation_uses_the_shared_api_proxy_contract() -> None:
    paths = TestClient(create_app()).app.openapi()["paths"]

    assert "/cross-cultural-recreations" in paths
    assert "/api/cross-cultural-recreations" not in paths


def test_standalone_review_api_is_not_nested_under_a_project() -> None:
    paths = TestClient(create_app()).app.openapi()["paths"]

    assert "/review-agent/cases" in paths
    assert "/review-agent/cases/{case_id}/messages" in paths
    assert not any(path.startswith("/projects/{project_id}/review-agent/cases") for path in paths)
