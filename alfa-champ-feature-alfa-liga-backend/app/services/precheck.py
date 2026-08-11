from __future__ import annotations

from dataclasses import dataclass, field

from app.config import Settings
from app.schemas import (
    BusinessState,
    CandidateSpec,
    DecisionOverrides,
    FinalDecision,
    SimulationResult,
    SprintId,
)


@dataclass(frozen=True)
class DecisionLimits:
    max_budget: float
    max_loss: float
    min_cash_reserve: float


@dataclass
class PrecheckOutcome:
    decision: FinalDecision
    reasons: list[str] = field(default_factory=list)
    rules_fired: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)


class HardPrecheck:
    """Deterministic safety rules. No model can override this service."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def resolve_limits(
        self,
        state: BusinessState,
        overrides: DecisionOverrides,
    ) -> DecisionLimits:
        constraints = state.constraints
        return DecisionLimits(
            max_budget=float(
                overrides.max_budget
                if overrides.max_budget is not None
                else constraints.get("max_budget", self.settings.default_max_budget)
            ),
            max_loss=float(
                overrides.max_loss
                if overrides.max_loss is not None
                else constraints.get("max_loss", self.settings.default_max_loss)
            ),
            min_cash_reserve=float(
                overrides.min_cash_reserve
                if overrides.min_cash_reserve is not None
                else constraints.get("min_cash_reserve", self.settings.default_min_cash_reserve)
            ),
        )

    def check_before_simulation(
        self,
        state: BusinessState,
        candidate: CandidateSpec,
        limits: DecisionLimits,
    ) -> PrecheckOutcome:
        if candidate.sprint_id == SprintId.REQUEST_DATA:
            return PrecheckOutcome(
                decision=FinalDecision.NEED_DATA,
                reasons=["Не удалось однозначно извлечь тип и параметры действия."],
                rules_fired=["REQUEST_DATA_ACTION"],
                risk_flags=["PARAMETERS_MISSING"],
            )
        if candidate.sprint_id == SprintId.NO_ACTION:
            return PrecheckOutcome(
                decision=FinalDecision.NO_ACTION,
                reasons=["Пользователь выбрал безопасную базовую линию без изменения."],
                rules_fired=["NO_ACTION_SELECTED"],
            )

        missing_reasons: list[str] = []
        missing_rules: list[str] = []
        missing_flags: list[str] = []

        if "unit_cost" in state.missing_fields or state.contribution_margin.is_missing:
            missing_reasons.append("Отсутствует себестоимость для расчёта unit-экономики.")
            missing_rules.append("MISSING_UNIT_COST")
            missing_flags.append("MISSING_UNIT_COST")
        if state.cash_balance.is_missing:
            missing_reasons.append("Отсутствует остаток денег для проверки резерва.")
            missing_rules.append("MISSING_CASH_BALANCE")
            missing_flags.append("MISSING_CASH_BALANCE")
        if float(state.data_coverage.value or 0.0) < self.settings.data_coverage_threshold:
            missing_reasons.append("Покрытие данных ниже безопасного порога.")
            missing_rules.append("LOW_DATA_COVERAGE")
            missing_flags.append("LOW_DATA_COVERAGE")
        if self._target_is_missing(state, candidate.target_metric):
            missing_reasons.append(f"Неизвестно базовое значение KPI {candidate.target_metric}.")
            missing_rules.append("MISSING_BASELINE_KPI")
            missing_flags.append("MISSING_BASELINE_KPI")
        if missing_reasons:
            return PrecheckOutcome(
                decision=FinalDecision.NEED_DATA,
                reasons=missing_reasons,
                rules_fired=missing_rules,
                risk_flags=missing_flags,
            )

        block_reasons: list[str] = []
        block_rules: list[str] = []
        risk_flags: list[str] = []
        cash = float(state.cash_balance.value or 0.0)

        if candidate.budget > limits.max_budget:
            block_reasons.append(
                f"Бюджет {candidate.budget:.0f} ₽ превышает лимит {limits.max_budget:.0f} ₽."
            )
            block_rules.append("MAX_BUDGET_EXCEEDED")
            risk_flags.append("OVER_BUDGET")
        if cash - candidate.budget < limits.min_cash_reserve:
            block_reasons.append("После бюджета нарушается минимальный денежный резерв.")
            block_rules.append("MIN_CASH_RESERVE_BREACH")
            risk_flags.append("CASH_RESERVE_RISK")

        projected_margin = self._projected_contribution_margin(state, candidate)
        if projected_margin is not None and projected_margin < 0:
            block_reasons.append(
                "Contribution margin тестовой продажи станет отрицательной "
                f"({projected_margin:.1%})."
            )
            block_rules.append("NEGATIVE_CONTRIBUTION_MARGIN")
            risk_flags.append("NEGATIVE_MARGIN")

        utilization = float(state.utilization.value or 0.0)
        if utilization + max(0.0, candidate.target_delta) > 1.0:
            block_reasons.append("Целевой спрос превышает физическую мощность бизнеса.")
            block_rules.append("CAPACITY_LIMIT_EXCEEDED")
            risk_flags.append("CAPACITY_RISK")
        if not candidate.stop_conditions:
            block_reasons.append("У действия отсутствует stop-loss/условие остановки.")
            block_rules.append("STOP_LOSS_REQUIRED")
            risk_flags.append("NO_STOP_LOSS")
        if not candidate.reversible:
            block_reasons.append("Необратимое действие запрещено в демонстрационном контуре.")
            block_rules.append("IRREVERSIBLE_ACTION")
            risk_flags.append("IRREVERSIBLE_ACTION")

        if block_reasons:
            return PrecheckOutcome(
                decision=FinalDecision.BLOCK,
                reasons=block_reasons,
                rules_fired=block_rules,
                risk_flags=risk_flags,
            )
        return PrecheckOutcome(
            decision=FinalDecision.APPROVE,
            reasons=["Кандидат прошёл детерминированные проверки до симуляции."],
            rules_fired=["PRECHECK_PASSED"],
        )

    def check_after_simulation(
        self,
        simulation: SimulationResult,
        limits: DecisionLimits,
    ) -> PrecheckOutcome:
        reasons: list[str] = []
        rules: list[str] = []
        flags: list[str] = []
        if simulation.cash_gap_probability > self.settings.max_cash_gap_probability:
            reasons.append(
                "Вероятность кассового разрыва превышает безопасный порог "
                f"({simulation.cash_gap_probability:.1%})."
            )
            rules.append("CASH_GAP_PROBABILITY_EXCEEDED")
            flags.append("CASH_GAP_RISK")
        if (
            simulation.capacity_overflow_probability
            > self.settings.max_capacity_overflow_probability
        ):
            reasons.append(
                "Вероятность превышения мощности превышает безопасный порог "
                f"({simulation.capacity_overflow_probability:.1%})."
            )
            rules.append("CAPACITY_OVERFLOW_PROBABILITY_EXCEEDED")
            flags.append("CAPACITY_RISK")
        if simulation.worst_case_loss > limits.max_loss:
            reasons.append(
                f"Worst-case loss {simulation.worst_case_loss:.0f} ₽ выше лимита "
                f"{limits.max_loss:.0f} ₽."
            )
            rules.append("MAX_LOSS_EXCEEDED")
            flags.append("MAX_LOSS_RISK")
        if reasons:
            return PrecheckOutcome(FinalDecision.BLOCK, reasons, rules, flags)
        return PrecheckOutcome(
            FinalDecision.APPROVE,
            ["Сценарные риски находятся в заданных пределах."],
            ["POSTCHECK_PASSED"],
            [],
        )

    @staticmethod
    def _target_is_missing(state: BusinessState, target_metric: str) -> bool:
        aliases = {"new_transactions": "transaction_count"}
        field_name = aliases.get(target_metric, target_metric)
        value = getattr(state, field_name, None)
        return bool(value is not None and getattr(value, "is_missing", False))

    @staticmethod
    def _projected_contribution_margin(
        state: BusinessState,
        candidate: CandidateSpec,
    ) -> float | None:
        if state.contribution_margin.value is None:
            return None
        margin = float(state.contribution_margin.value)
        params = candidate.parameters
        if params.discount_pct is not None:
            margin -= params.discount_pct / 100
        if params.bonus_pct is not None:
            margin -= params.bonus_pct / 100
        if params.bundle_discount_pct is not None:
            margin -= params.bundle_discount_pct / 100
        return margin
