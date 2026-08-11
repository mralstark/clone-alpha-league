from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture(scope="session")
def settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    db_path = tmp_path_factory.mktemp("alfa_liga") / "test.db"
    return Settings(
        app_env="test",
        log_level="ERROR",
        database_url=f"sqlite:///{db_path}",
        cors_origins=["http://localhost:5173"],
        monte_carlo_runs=5_000,
    )


@pytest.fixture(scope="session")
def app(settings: Settings):
    return create_app(settings)


@pytest.fixture(scope="session")
def client(settings) -> Iterator[TestClient]:
    """Create a TestClient using the provided test settings directly to avoid
    any fixture name collisions with the package named 'app'."""
    app_instance = create_app(settings)
    with TestClient(app_instance) as test_client:
        yield test_client


@pytest.fixture()
def generate_payload() -> dict[str, object]:
    return {
        "business_id": "coffee_demo",
        "mode": "GENERATE",
        "request": "Как увеличить повторные покупки и не уйти в минус?",
        "overrides": {
            "max_budget": 10_000,
            "max_loss": 5_000,
            "min_cash_reserve": 50_000,
        },
        "seed": 42,
    }


def evaluation_payload(
    text: str,
    *,
    business_id: str = "coffee_demo",
    seed: int = 42,
) -> dict[str, object]:
    return {
        "business_id": business_id,
        "mode": "EVALUATE",
        "request": text,
        "overrides": {
            "max_budget": 10_000,
            "max_loss": 5_000,
            "min_cash_reserve": 50_000,
        },
        "seed": seed,
    }
