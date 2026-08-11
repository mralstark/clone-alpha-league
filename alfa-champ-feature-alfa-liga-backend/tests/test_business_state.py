from __future__ import annotations

from fastapi.testclient import TestClient

from app.schemas import BusinessState


def test_demo_coffee_builds_strict_realistic_state(client: TestClient) -> None:
    response = client.get("/api/businesses/coffee_demo/state")
    assert response.status_code == 200
    state = BusinessState.model_validate(response.json())
    assert state.transaction_count.value > 1_000
    assert 300 < state.average_ticket.value < 450
    assert 0 < state.repeat_rate.value < 0.25
    assert state.peer_gap.value > 0.10
    assert state.morning_utilization.value < 0.15
    assert 0.09 < state.contribution_margin.value < 0.19
    assert state.data_coverage.value >= 0.75
    assert "marketing_attribution" in state.missing_fields


def test_each_business_metric_carries_provenance(client: TestClient) -> None:
    state = client.get("/api/businesses/coffee_demo/state").json()
    metric_names = {
        "payment_volume",
        "revenue",
        "transaction_count",
        "average_ticket",
        "repeat_rate",
        "refund_rate",
        "gross_margin",
        "contribution_margin",
        "utilization",
        "cash_balance",
        "runway_days",
        "morning_utilization",
        "peer_gap",
        "data_coverage",
    }
    for name in metric_names:
        assert {"value", "source", "observed_at", "confidence", "is_missing"} == set(state[name])
