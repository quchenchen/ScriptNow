from fastapi.testclient import TestClient

from scriptflow_v7.app import create_app


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
