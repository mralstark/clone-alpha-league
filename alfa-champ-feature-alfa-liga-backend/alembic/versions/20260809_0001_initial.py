"""Initial Alfa-Liga schema.

Revision ID: 20260809_0001
Revises:
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260809_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_VALUE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "businesses",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("profile", JSON_VALUE, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "knowledge_items",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("key", sa.String(128), nullable=False, unique=True),
        sa.Column("payload", JSON_VALUE, nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_knowledge_items_kind", "knowledge_items", ["kind"])
    op.create_table(
        "alfa_products",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("integration_status", sa.String(32), nullable=False),
        sa.Column("actions", JSON_VALUE, nullable=False),
        sa.Column("requires_confirmation", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "model_versions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("model_type", sa.String(64), nullable=False),
        sa.Column("version", sa.String(128), nullable=False),
        sa.Column("metadata_json", JSON_VALUE, nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_model_versions_model_type", "model_versions", ["model_type"])
    op.create_table(
        "business_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "business_id",
            sa.String(64),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("is_missing", sa.Boolean(), nullable=False),
        sa.Column("payload", JSON_VALUE, nullable=False),
    )
    op.create_index("ix_business_events_business_id", "business_events", ["business_id"])
    op.create_index("ix_business_events_occurred_at", "business_events", ["occurred_at"])
    op.create_table(
        "metric_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "business_id",
            sa.String(64),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("metric_name", sa.String(128), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("is_missing", sa.Boolean(), nullable=False),
        sa.Column("value", JSON_VALUE, nullable=False),
    )
    op.create_index("ix_metric_snapshots_business_id", "metric_snapshots", ["business_id"])
    op.create_index("ix_metric_snapshots_metric_name", "metric_snapshots", ["metric_name"])
    op.create_table(
        "decision_requests",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "business_id",
            sa.String(64),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("request_text", sa.Text(), nullable=False),
        sa.Column("overrides", JSON_VALUE, nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("business_state", JSON_VALUE, nullable=False),
        sa.Column("problem_summary", sa.Text(), nullable=False),
        sa.Column("decision_trace", JSON_VALUE, nullable=False),
        sa.Column("bank_effect", JSON_VALUE, nullable=False),
        sa.Column("model_versions", JSON_VALUE, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_decision_requests_business_id", "decision_requests", ["business_id"])
    op.create_table(
        "sprint_candidates",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "decision_id",
            sa.String(64),
            sa.ForeignKey("decision_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sprint_id", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("spec", JSON_VALUE, nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("reasons", JSON_VALUE, nullable=False),
        sa.Column("rank_score", sa.Float(), nullable=True),
        sa.Column("card", JSON_VALUE, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sprint_candidates_decision_id", "sprint_candidates", ["decision_id"])
    op.create_table(
        "simulation_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "candidate_id",
            sa.String(64),
            sa.ForeignKey("sprint_candidates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("simulator_version", sa.String(128), nullable=False),
        sa.Column("input_data", JSON_VALUE, nullable=False),
        sa.Column("output_data", JSON_VALUE, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_simulation_runs_candidate_id", "simulation_runs", ["candidate_id"])
    op.create_table(
        "experiments",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "candidate_id",
            sa.String(64),
            sa.ForeignKey("sprint_candidates.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "business_id",
            sa.String(64),
            sa.ForeignKey("businesses.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("state_before", JSON_VALUE, nullable=False),
        sa.Column("action", JSON_VALUE, nullable=False),
        sa.Column("forecast", JSON_VALUE, nullable=False),
        sa.Column("execution_plan", JSON_VALUE, nullable=False),
        sa.Column("model_versions", JSON_VALUE, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_experiments_candidate_id", "experiments", ["candidate_id"])
    op.create_index("ix_experiments_business_id", "experiments", ["business_id"])
    op.create_table(
        "experiment_outcomes",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "experiment_id",
            sa.String(64),
            sa.ForeignKey("experiments.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("actual_outcome", JSON_VALUE, nullable=False),
        sa.Column("state_after", JSON_VALUE, nullable=True),
        sa.Column("reward", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_experiment_outcomes_experiment_id", "experiment_outcomes", ["experiment_id"]
    )


def downgrade() -> None:
    op.drop_table("experiment_outcomes")
    op.drop_table("experiments")
    op.drop_table("simulation_runs")
    op.drop_table("sprint_candidates")
    op.drop_table("decision_requests")
    op.drop_table("metric_snapshots")
    op.drop_table("business_events")
    op.drop_table("model_versions")
    op.drop_table("alfa_products")
    op.drop_table("knowledge_items")
    op.drop_table("businesses")
