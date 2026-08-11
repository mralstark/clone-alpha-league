from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DataSource(StrEnum):
    BANK = "BANK"
    MANUAL = "MANUAL"
    EXTERNAL = "EXTERNAL"
    SYNTHETIC = "SYNTHETIC"


class DecisionMode(StrEnum):
    GENERATE = "GENERATE"
    EVALUATE = "EVALUATE"


class FinalDecision(StrEnum):
    APPROVE = "APPROVE"
    BLOCK = "BLOCK"
    NEED_DATA = "NEED_DATA"
    NO_ACTION = "NO_ACTION"


class SprintId(StrEnum):
    MORNING_DISCOUNT = "MORNING_DISCOUNT"
    REPEAT_BONUS = "REPEAT_BONUS"
    MICRO_AD_TEST = "MICRO_AD_TEST"
    PRICE_CHANGE = "PRICE_CHANGE"
    OPENING_HOURS_CHANGE = "OPENING_HOURS_CHANGE"
    PRODUCT_BUNDLE = "PRODUCT_BUNDLE"
    NO_ACTION = "NO_ACTION"
    REQUEST_DATA = "REQUEST_DATA"


class IntegrationStatus(StrEnum):
    MOCK = "MOCK"
    AVAILABLE = "AVAILABLE"


class MetricValue(StrictModel):
    value: float | int | str | None
    source: DataSource
    observed_at: datetime
    confidence: float = Field(ge=0, le=1)
    is_missing: bool = False


class BusinessState(StrictModel):
    business_id: str
    window_start: datetime
    window_end: datetime
    payment_volume: MetricValue
    revenue: MetricValue
    transaction_count: MetricValue
    average_ticket: MetricValue
    repeat_rate: MetricValue
    refund_rate: MetricValue
    gross_margin: MetricValue
    contribution_margin: MetricValue
    utilization: MetricValue
    cash_balance: MetricValue
    runway_days: MetricValue
    morning_utilization: MetricValue
    peer_gap: MetricValue
    data_coverage: MetricValue
    missing_fields: list[str]
    constraints: dict[str, float]


class DecisionOverrides(StrictModel):
    max_budget: float | None = Field(default=None, ge=0)
    max_loss: float | None = Field(default=None, ge=0)
    min_cash_reserve: float | None = Field(default=None, ge=0)


class DecisionCreate(StrictModel):
    business_id: str
    mode: DecisionMode
    request: str = Field(min_length=3, max_length=2_000)
    overrides: DecisionOverrides = Field(default_factory=DecisionOverrides)
    seed: int = Field(default=42, ge=0, le=2_147_483_647)


class CandidateParameters(StrictModel):
    discount_pct: float | None = Field(default=None, ge=-50, le=95)
    bonus_pct: float | None = Field(default=None, ge=0, le=50)
    ad_budget: float | None = Field(default=None, ge=0)
    price_change_pct: float | None = Field(default=None, ge=-50, le=100)
    opening_hour: int | None = Field(default=None, ge=0, le=23)
    closing_hour: int | None = Field(default=None, ge=0, le=23)
    bundle_discount_pct: float | None = Field(default=None, ge=0, le=50)
    target_hours: list[int] = Field(default_factory=list)


class CandidateSpec(StrictModel):
    sprint_id: SprintId
    title: str
    hypothesis: str
    parameters: CandidateParameters
    budget: float = Field(ge=0)
    duration_days: int = Field(ge=1, le=180)
    target_metric: str
    target_delta: float
    required_data: list[str]
    stop_conditions: list[str]
    recommended_product_ids: list[str]
    reversible: bool = True


class DistributionSpec(StrictModel):
    metric: str
    distribution: Literal["triangular", "uniform", "beta"]
    minimum: float
    mode: float | None = None
    maximum: float
    direction: Literal["UP", "DOWN", "MIXED"]
    dependency: str | None = None

    @model_validator(mode="after")
    def validate_bounds(self) -> DistributionSpec:
        if self.minimum > self.maximum:
            raise ValueError("minimum cannot exceed maximum")
        if self.distribution == "triangular" and (
            self.mode is None or not self.minimum <= self.mode <= self.maximum
        ):
            raise ValueError("triangular mode must be inside bounds")
        return self


class WorldModelOutput(StrictModel):
    effects: list[DistributionSpec]
    assumptions: list[str]
    confidence: float = Field(ge=0, le=1)
    low_confidence_reasons: list[str] = Field(default_factory=list)
    provider: str
    version: str
    fallback_used: bool = False


class SimulationResult(StrictModel):
    success_probability: float = Field(ge=0, le=1)
    expected_revenue_delta: float
    expected_profit_delta: float
    p10: float
    p50: float
    p90: float
    worst_case_loss: float = Field(ge=0)
    cash_gap_probability: float = Field(ge=0, le=1)
    capacity_overflow_probability: float = Field(ge=0, le=1)
    uncertainty_score: float = Field(ge=0, le=1)
    runs: int
    seed: int
    simulator_version: str


class BankEffect(StrictModel):
    incremental_payment_volume: float
    incremental_transaction_count: float
    estimated_fee_revenue: float
    connected_product_count: int
    estimated_service_cost: float
    net_bank_effect: float
    assumptions: list[str]


class ProductAction(StrictModel):
    product_id: str
    product_name: str
    action: str
    integration_status: IntegrationStatus
    requires_confirmation: bool


class ProductInfo(StrictModel):
    product_id: str
    name: str
    description: str
    integration_status: IntegrationStatus
    actions: list[str]
    requires_confirmation: bool


class DecisionTrace(StrictModel):
    facts_used: list[str]
    missing_data: list[str]
    rules_fired: list[str]
    assumptions: list[str]
    numeric_forecasts: list[str]
    risk_flags: list[str]
    decision_reasons: list[str]
    model_versions: dict[str, str]


class DecisionCard(StrictModel):
    candidate_id: str
    sprint_id: SprintId
    name: str
    decision: FinalDecision
    budget: float
    duration_days: int
    kpi_success_probability: float
    p10: float
    p50: float
    p90: float
    expected_financial_effect: float
    worst_case_loss: float
    risks: list[str]
    facts: list[str]
    assumptions: list[str]
    stop_conditions: list[str]
    recommended_products: list[ProductAction]
    requires_confirmation: bool
    bank_effect: BankEffect
    rank_score: float
    simulation: SimulationResult


class BlockedCandidate(StrictModel):
    candidate_id: str
    sprint_id: SprintId
    name: str
    decision: FinalDecision
    reasons: list[str]


class DecisionResponse(StrictModel):
    decision_id: str
    business_state: BusinessState
    problem_summary: str
    best_candidates: list[DecisionCard]
    blocked_candidates: list[BlockedCandidate]
    decision_trace: DecisionTrace
    bank_effect: BankEffect | None
    model_versions: dict[str, str]


class ResimulateRequest(StrictModel):
    parameters: CandidateParameters | None = None
    budget: float | None = Field(default=None, ge=0)
    duration_days: int | None = Field(default=None, ge=1, le=180)
    seed: int | None = Field(default=None, ge=0, le=2_147_483_647)


class ResimulateResponse(StrictModel):
    candidate_id: str
    decision: FinalDecision
    reasons: list[str]
    card: DecisionCard | None
    simulation: SimulationResult | None


class ExperimentCreate(StrictModel):
    candidate_id: str
    confirmed: bool


class ExperimentOutcomeCreate(StrictModel):
    actual_revenue_delta: float
    actual_profit_delta: float
    actual_target_delta: float | None = None
    stopped_early: bool = False
    notes: str | None = Field(default=None, max_length=2_000)
    state_after: dict[str, Any] | None = None


class ExperimentResponse(StrictModel):
    experiment_id: str
    candidate_id: str
    business_id: str
    status: str
    state_before: dict[str, Any]
    action: dict[str, Any]
    forecast: dict[str, Any]
    execution_plan: list[ProductAction]
    model_versions: dict[str, Any]
    actual_outcome: dict[str, Any] | None = None
    reward: float | None = None
    started_at: datetime
    stopped_at: datetime | None = None


class ModelInfo(StrictModel):
    runtime_policy: str
    base_model: str
    lora_adapter: str
    production_baseline: str
    stage0: dict[str, Any]
    stage1: dict[str, Any]
    reft_decision: str
    stage2_model_version: str
    simulator_version: str
    honest_limitations: list[str]


class HealthResponse(StrictModel):
    status: Literal["ok"]
    app: str
    environment: str
    database: str
