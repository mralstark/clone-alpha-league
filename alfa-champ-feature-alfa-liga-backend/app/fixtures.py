from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import ALFA_PRODUCT_CATALOG
from app.models import (
    AlfaProduct,
    Business,
    BusinessEvent,
    KnowledgeItem,
    MetricSnapshot,
    ModelVersion,
)


def _customer_hash(business_id: str, customer_number: int) -> str:
    return hashlib.sha256(f"{business_id}:{customer_number}".encode()).hexdigest()[:20]


def _seed_transactions(
    session: Session,
    business_id: str,
    *,
    seed: int,
    transactions_per_day: int,
    include_cost: bool,
) -> None:
    rng = np.random.default_rng(seed)
    today = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    known_customers: list[str] = []
    next_customer = 1

    for day_offset in range(60, 0, -1):
        day = today - timedelta(days=day_offset)
        daily_count = max(12, int(rng.normal(transactions_per_day, 4)))
        for _ in range(daily_count):
            # The morning is deliberately weak: only around 11% of transactions.
            hour = int(rng.integers(8, 11)) if rng.random() < 0.11 else int(rng.integers(11, 20))

            if known_customers and rng.random() < 0.16:
                customer = known_customers[int(rng.integers(0, len(known_customers)))]
            else:
                customer = _customer_hash(business_id, next_customer)
                next_customer += 1
                known_customers.append(customer)

            amount = round(float(np.clip(rng.normal(365, 90), 170, 780)), 2)
            payload: dict[str, object] = {
                "amount": amount,
                "hour": hour,
                "customer_hash": customer,
                "refunded": bool(rng.random() < 0.012),
                "payment_channel": "acquiring" if rng.random() < 0.91 else "cash",
            }
            if include_cost:
                payload["variable_cost"] = round(amount * float(rng.uniform(0.56, 0.62)), 2)

            session.add(
                BusinessEvent(
                    business_id=business_id,
                    event_type="TRANSACTION",
                    occurred_at=day.replace(
                        hour=hour,
                        minute=int(rng.integers(0, 60)),
                    ),
                    source="SYNTHETIC",
                    confidence=0.98,
                    is_missing=False,
                    payload=payload,
                )
            )


def _seed_business(
    session: Session,
    *,
    business_id: str,
    name: str,
    seed: int,
    include_cost: bool,
    transactions_per_day: int,
) -> None:
    session.add(
        Business(
            id=business_id,
            name=name,
            kind="coffee_shop",
            profile={
                "cash_balance": 180_000.0,
                "fixed_costs_60d": 180_000.0,
                "capacity_orders_per_hour": 18.0,
                "operating_hours_per_day": 12.0,
                "cost_data_available": include_cost,
                "manual_constraints": {
                    "max_budget": 12_000.0,
                    "max_loss": 6_000.0,
                    "min_cash_reserve": 50_000.0,
                },
                "known_missing_fields": ["marketing_attribution"],
                "fixture_note": "Synthetic demo; not customer or bank production data.",
            },
        )
    )
    _seed_transactions(
        session,
        business_id,
        seed=seed,
        transactions_per_day=transactions_per_day,
        include_cost=include_cost,
    )

    observed_at = datetime.now(UTC)
    snapshots = [
        ("cash_balance", 180_000.0, "BANK", 0.99, False),
        ("peer_repeat_rate", 0.34, "EXTERNAL", 0.82, False),
        ("peer_average_ticket", 390.0, "EXTERNAL", 0.82, False),
        ("marketing_attribution", None, "MANUAL", 0.0, True),
    ]
    for metric_name, value, source, confidence, is_missing in snapshots:
        session.add(
            MetricSnapshot(
                business_id=business_id,
                metric_name=metric_name,
                observed_at=observed_at,
                source=source,
                confidence=confidence,
                is_missing=is_missing,
                value={"value": value},
            )
        )


def seed_demo_data(session: Session) -> None:
    if session.scalar(select(Business.id).limit(1)) is not None:
        return

    _seed_business(
        session,
        business_id="coffee_demo",
        name="Кофейня на кампусе",
        seed=2026,
        include_cost=True,
        transactions_per_day=33,
    )
    _seed_business(
        session,
        business_id="coffee_missing_cost",
        name="Кофейня без данных о себестоимости",
        seed=2027,
        include_cost=False,
        transactions_per_day=25,
    )

    for product_id, item in ALFA_PRODUCT_CATALOG.items():
        session.add(
            AlfaProduct(
                id=product_id,
                name=item["name"],
                description=item["description"],
                integration_status="MOCK",
                actions=item["actions"],
                requires_confirmation=True,
                active=True,
            )
        )

    session.add(
        KnowledgeItem(
            id="coffee-peer-v1",
            kind="peer_benchmark",
            key="coffee_shop_small_city_v1",
            source="EXTERNAL",
            payload={
                "repeat_rate_median": 0.34,
                "average_ticket_median": 390.0,
                "method": "demonstration cohort assumption",
                "official_alfa_data": False,
            },
        )
    )

    model_rows = [
        (
            "base-qwen",
            "base_model",
            "Qwen/Qwen1.5-0.5B",
            {"runtime_loaded": False},
        ),
        (
            "lora-stage1",
            "policy_adapter",
            "lora-only-stage1",
            {"production_baseline": True, "adapter_present_in_repository": False},
        ),
        (
            "reft-stage1",
            "research_adapter",
            "joint-reft-stage1",
            {"production_baseline": False, "reason": "No statistically stable product gain"},
        ),
        (
            "simulator-v1",
            "simulator",
            "coffee-mc-v1",
            {"runs": 5_000, "deterministic_seed": True},
        ),
    ]
    for row_id, model_type, version, metadata in model_rows:
        session.add(
            ModelVersion(
                id=row_id,
                model_type=model_type,
                version=version,
                metadata_json=metadata,
                active=True,
            )
        )

    session.commit()
