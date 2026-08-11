from __future__ import annotations

import json

from fastapi.testclient import TestClient

from tests.conftest import evaluation_payload


def _single_result(payload: dict[str, object]) -> tuple[str, dict[str, object]]:
    if payload["best_candidates"]:
        item = payload["best_candidates"][0]
    else:
        item = payload["blocked_candidates"][0]
    return item["decision"], item


def test_generate_returns_three_ranked_cards_and_blocked_options(
    client: TestClient,
    generate_payload: dict[str, object],
) -> None:
    response = client.post("/api/decisions", json=generate_payload)
    assert response.status_code == 201
    payload = response.json()
    assert len(payload["best_candidates"]) == 3
    assert len(payload["blocked_candidates"]) == 2
    scores = [item["rank_score"] for item in payload["best_candidates"]]
    assert scores == sorted(scores, reverse=True)
    assert all(item["simulation"]["runs"] == 5_000 for item in payload["best_candidates"])
    assert any(
        "NEGATIVE_CONTRIBUTION_MARGIN" in payload["decision_trace"]["rules_fired"] for _ in [0]
    )


def test_discount_9_percent_is_approved(client: TestClient) -> None:
    response = client.post("/api/decisions", json=evaluation_payload("Дать скидку 9% утром"))
    assert response.status_code == 201
    decision, item = _single_result(response.json())
    assert decision == "APPROVE"
    assert item["sprint_id"] == "MORNING_DISCOUNT"


def test_discount_19_percent_is_blocked_by_negative_margin(client: TestClient) -> None:
    response = client.post("/api/decisions", json=evaluation_payload("Дать скидку 19% утром"))
    decision, item = _single_result(response.json())
    assert decision == "BLOCK"
    assert any("отрицательной" in reason for reason in item["reasons"])


def test_missing_cost_returns_need_data(client: TestClient) -> None:
    response = client.post(
        "/api/decisions",
        json=evaluation_payload("Дать скидку 9% утром", business_id="coffee_missing_cost"),
    )
    decision, item = _single_result(response.json())
    assert decision == "NEED_DATA"
    assert any("себестоимость" in reason for reason in item["reasons"])


def test_budget_above_limit_is_blocked(client: TestClient) -> None:
    response = client.post(
        "/api/decisions",
        json=evaluation_payload("Запустить рекламу с бюджетом 200000 рублей на 7 дней"),
    )
    decision, item = _single_result(response.json())
    assert decision == "BLOCK"
    assert any("превышает лимит" in reason for reason in item["reasons"])


def test_same_seed_produces_identical_numeric_result(client: TestClient) -> None:
    first = client.post(
        "/api/decisions", json=evaluation_payload("Дать скидку 9% утром", seed=77)
    ).json()["best_candidates"][0]["simulation"]
    second = client.post(
        "/api/decisions", json=evaluation_payload("Дать скидку 9% утром", seed=77)
    ).json()["best_candidates"][0]["simulation"]
    assert first == second


def test_no_action_is_an_explicit_safe_decision(client: TestClient) -> None:
    payload = client.post(
        "/api/decisions",
        json=evaluation_payload("Пока ничего не менять, оставить без изменений"),
    ).json()
    decision, item = _single_result(payload)
    assert decision == "NO_ACTION"
    assert item["sprint_id"] == "NO_ACTION"


def test_only_catalog_products_appear_in_decisions(
    client: TestClient,
    generate_payload: dict[str, object],
) -> None:
    catalog = {item["product_id"] for item in client.get("/api/products").json()}
    decision = client.post("/api/decisions", json=generate_payload).json()
    returned = {
        product["product_id"]
        for card in decision["best_candidates"]
        for product in card["recommended_products"]
    }
    assert returned
    assert returned <= catalog


def test_trace_and_prompt_surface_never_expose_raw_transactions(
    client: TestClient,
    generate_payload: dict[str, object],
) -> None:
    payload = client.post("/api/decisions", json=generate_payload).json()
    serialized = json.dumps(payload, ensure_ascii=False)
    for forbidden in ("customer_hash", "variable_cost", "payment_channel"):
        assert forbidden not in serialized


class FailingPolicy:
    name = "FailingPolicy"
    version = "failing-v1"

    def __init__(self) -> None:
        self.calls = 0

    def propose(self, state, request, mode):  # type: ignore[no-untyped-def]
        self.calls += 1
        raise RuntimeError("provider down")


def test_policy_failure_uses_template_fallback(
    client: TestClient,
    app,
    generate_payload: dict[str, object],
) -> None:
    resilient = app.state.decision_service.policy
    original = resilient.primary
    failing = FailingPolicy()
    resilient.primary = failing
    try:
        response = client.post("/api/decisions", json=generate_payload)
        assert response.status_code == 201
        payload = response.json()
        assert payload["best_candidates"]
        assert "POLICY_FALLBACK_TO_TEMPLATE" in payload["decision_trace"]["rules_fired"]
        assert failing.calls == 1
    finally:
        resilient.primary = original


def test_resimulate_changes_numbers_without_calling_policy(client: TestClient, app) -> None:
    created = client.post("/api/decisions", json=evaluation_payload("Дать скидку 9% утром")).json()
    card = created["best_candidates"][0]
    resilient = app.state.decision_service.policy
    original = resilient.primary
    failing = FailingPolicy()
    resilient.primary = failing
    try:
        response = client.post(
            f"/api/candidates/{card['candidate_id']}/resimulate",
            json={"parameters": {"discount_pct": 10}, "seed": 42},
        )
        assert response.status_code == 200
        result = response.json()
        assert result["decision"] == "APPROVE"
        assert result["simulation"] != card["simulation"]
        assert failing.calls == 0
    finally:
        resilient.primary = original


def test_resimulate_counterfactual_19_percent_blocks(client: TestClient) -> None:
    created = client.post("/api/decisions", json=evaluation_payload("Дать скидку 9% утром")).json()
    candidate_id = created["best_candidates"][0]["candidate_id"]
    result = client.post(
        f"/api/candidates/{candidate_id}/resimulate",
        json={"parameters": {"discount_pct": 19}, "seed": 42},
    ).json()
    assert result["decision"] == "BLOCK"
    assert result["simulation"] is None
