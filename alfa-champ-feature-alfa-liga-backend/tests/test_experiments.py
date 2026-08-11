from __future__ import annotations

import json

from fastapi.testclient import TestClient


def test_outcome_is_persisted_and_exported_to_anonymized_replay(
    client: TestClient,
    generate_payload: dict[str, object],
) -> None:
    decision = client.post("/api/decisions", json=generate_payload).json()
    candidate_id = decision["best_candidates"][0]["candidate_id"]

    unconfirmed = client.post(
        "/api/experiments",
        json={"candidate_id": candidate_id, "confirmed": False},
    )
    assert unconfirmed.status_code == 409

    created = client.post(
        "/api/experiments",
        json={"candidate_id": candidate_id, "confirmed": True},
    )
    assert created.status_code == 201
    experiment = created.json()
    assert experiment["status"] == "RUNNING"
    assert all(item["integration_status"] == "MOCK" for item in experiment["execution_plan"])

    completed = client.patch(
        f"/api/experiments/{experiment['experiment_id']}/outcome",
        json={
            "actual_revenue_delta": 4200,
            "actual_profit_delta": 900,
            "actual_target_delta": 0.09,
            "stopped_early": False,
            "notes": "Synthetic demo outcome",
        },
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "COMPLETED"
    assert completed.json()["actual_outcome"]["actual_profit_delta"] == 900

    replay = client.post("/api/training/export-replay")
    assert replay.status_code == 200
    records = [json.loads(line) for line in replay.text.splitlines() if line]
    record = next(item for item in records if item["actual_outcome"]["actual_profit_delta"] == 900)
    assert record["privacy"] == {
        "contains_raw_transactions": False,
        "contains_personal_data": False,
    }
    assert record["business_hash"] != "coffee_demo"
    assert "customer_hash" not in replay.text
