from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect


def test_alembic_initial_migration_creates_contract_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "migration.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        cwd=Path(__file__).parents[1],
        env=env,
        capture_output=True,
        text=True,
    )
    tables = set(inspect(create_engine(f"sqlite:///{db_path}")).get_table_names())
    assert {
        "businesses",
        "business_events",
        "metric_snapshots",
        "decision_requests",
        "sprint_candidates",
        "simulation_runs",
        "experiments",
        "experiment_outcomes",
        "knowledge_items",
        "alfa_products",
        "model_versions",
    }.issubset(tables)
