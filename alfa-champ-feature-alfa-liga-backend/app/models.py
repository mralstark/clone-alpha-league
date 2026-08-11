from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

JSON_VALUE = JSON().with_variant(JSONB, "postgresql")


def utc_now() -> datetime:
    return datetime.now(UTC)


class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False, default="coffee_shop")
    profile: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class BusinessEvent(Base):
    __tablename__ = "business_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    is_missing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)


class MetricSnapshot(Base):
    __tablename__ = "metric_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    metric_name: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    is_missing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    value: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)


class DecisionRequest(Base):
    __tablename__ = "decision_requests"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    request_text: Mapped[str] = mapped_column(Text, nullable=False)
    overrides: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    business_state: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    problem_summary: Mapped[str] = mapped_column(Text, nullable=False)
    decision_trace: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    bank_effect: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    model_versions: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SprintCandidate(Base):
    __tablename__ = "sprint_candidates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    decision_id: Mapped[str] = mapped_column(
        ForeignKey("decision_requests.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sprint_id: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    spec: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reasons: Mapped[list[str]] = mapped_column(JSON_VALUE, nullable=False, default=list)
    rank_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    card: Mapped[dict[str, Any] | None] = mapped_column(JSON_VALUE, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SimulationRun(Base):
    __tablename__ = "simulation_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("sprint_candidates.id", ondelete="CASCADE"), index=True, nullable=False
    )
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    simulator_version: Mapped[str] = mapped_column(String(128), nullable=False)
    input_data: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    output_data: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("sprint_candidates.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    state_before: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    action: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    forecast: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    execution_plan: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON_VALUE, nullable=False, default=list
    )
    model_versions: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExperimentOutcome(Base):
    __tablename__ = "experiment_outcomes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    actual_outcome: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    state_after: Mapped[dict[str, Any] | None] = mapped_column(JSON_VALUE, nullable=True)
    reward: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class KnowledgeItem(Base):
    __tablename__ = "knowledge_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AlfaProduct(Base):
    __tablename__ = "alfa_products"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    integration_status: Mapped[str] = mapped_column(String(32), nullable=False, default="MOCK")
    actions: Mapped[list[str]] = mapped_column(JSON_VALUE, nullable=False, default=list)
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    model_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
