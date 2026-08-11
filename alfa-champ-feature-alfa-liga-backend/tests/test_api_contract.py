from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.schemas import DecisionResponse


def test_health_returns_200(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_openapi_contains_all_mandatory_endpoints(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = set(response.json()["paths"])
    assert {
        "/api/health",
        "/api/model/info",
        "/api/products",
        "/api/businesses/{business_id}/state",
        "/api/decisions",
        "/api/decisions/{decision_id}",
        "/api/decisions/{decision_id}/trace",
        "/api/candidates/{candidate_id}/resimulate",
        "/api/experiments",
        "/api/experiments/{experiment_id}/outcome",
        "/api/experiments/{experiment_id}",
        "/api/training/export-replay",
    }.issubset(paths)


def test_cors_is_configured_from_settings(client: TestClient) -> None:
    response = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_model_info_is_honest_about_lora_and_reft(client: TestClient) -> None:
    payload = client.get("/api/model/info").json()
    assert payload["production_baseline"] == "LoRA-only"
    assert payload["stage1"]["status"] == "MIXED_ON_PRIMARY_METRIC"
    assert "research" in payload["reft_decision"].lower()
    assert any("does not contain trained adapter" in item for item in payload["honest_limitations"])


def test_products_are_explicit_mock_catalog(client: TestClient) -> None:
    products = client.get("/api/products").json()
    ids = {item["product_id"] for item in products}
    assert len(products) == 10
    assert {"acquiring", "alfa_kassa", "alfa_target", "neuro_office"}.issubset(ids)
    assert {item["integration_status"] for item in products} == {"MOCK"}
    assert all(item["requires_confirmation"] for item in products)


def test_frontend_mock_matches_live_response_contract() -> None:
    path = Path(__file__).parents[1] / "docs" / "frontend_mock.json"
    DecisionResponse.model_validate(json.loads(path.read_text(encoding="utf-8")))


def test_frontend_is_served_from_backend_origin(client: TestClient) -> None:
    home = client.get("/", follow_redirects=False)
    assert home.status_code == 307
    assert home.headers["location"] == "/web/alfa-league.html"

    for page in ("alfa-league.html", "alfa-accounting.html", "alfa-assistant.html"):
        response = client.get(f"/web/{page}")
        assert response.status_code == 200
        assert "Альфа" in response.text


def test_frontend_uses_live_api_instead_of_timer_mock(client: TestClient) -> None:
    assistant = client.get("/web/alfa-assistant.html").text
    assert 'id="scenarioType"' in assistant
    assert 'src="alfa-api.js"' in assistant
    assert 'src="alfa-assistant.js"' in assistant
    assert "Сырые данные (JSON) для бэкенда" not in assistant

    api_client = client.get("/web/alfa-api.js")
    assistant_client = client.get("/web/alfa-assistant.js")
    assert api_client.status_code == 200
    assert assistant_client.status_code == 200
    for endpoint in (
        "/api/businesses/",
        "/api/decisions",
        "/api/candidates/",
        "/api/experiments",
    ):
        assert endpoint in f"{api_client.text}\n{assistant_client.text}"
