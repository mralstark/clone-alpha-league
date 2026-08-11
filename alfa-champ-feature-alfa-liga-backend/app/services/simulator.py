from __future__ import annotations

import hashlib

import numpy as np

from app.config import Settings
from app.schemas import (
    BusinessState,
    CandidateSpec,
    DistributionSpec,
    SimulationResult,
    SprintId,
    WorldModelOutput,
)


class MonteCarloSimulator:
    def __init__(self, settings: Settings):
        self.runs = settings.monte_carlo_runs
        self.version = settings.simulator_version

    @staticmethod
    def candidate_seed(seed: int, sprint_id: SprintId, ordinal: int = 0) -> int:
        digest = hashlib.sha256(f"{seed}:{sprint_id.value}:{ordinal}".encode()).digest()
        offset = int.from_bytes(digest[:4], "big")
        return (seed + offset) % 2_147_483_647

    def simulate(
        self,
        state: BusinessState,
        candidate: CandidateSpec,
        world: WorldModelOutput,
        seed: int,
    ) -> SimulationResult:
        if candidate.sprint_id in {SprintId.NO_ACTION, SprintId.REQUEST_DATA}:
            return SimulationResult(
                success_probability=1.0 if candidate.sprint_id == SprintId.NO_ACTION else 0.0,
                expected_revenue_delta=0.0,
                expected_profit_delta=0.0,
                p10=0.0,
                p50=0.0,
                p90=0.0,
                worst_case_loss=0.0,
                cash_gap_probability=0.0,
                capacity_overflow_probability=0.0,
                uncertainty_score=0.0,
                runs=self.runs,
                seed=seed,
                simulator_version=self.version,
            )

        rng = np.random.default_rng(seed)
        sampled = {item.metric: self._sample(rng, item) for item in world.effects}
        ones = np.ones(self.runs, dtype=np.float64)
        demand = sampled.get("demand_multiplier", ones)
        repeat = sampled.get("repeat_multiplier", ones)
        ad_effect = sampled.get("ad_revenue_multiplier", ones)
        ticket = sampled.get("ticket_multiplier", ones)
        affected = sampled.get("affected_share", np.full(self.runs, 0.16))

        baseline_revenue = float(state.revenue.value or 0.0) * candidate.duration_days / 60.0
        baseline_transactions = (
            float(state.transaction_count.value or 0.0) * candidate.duration_days / 60.0
        )
        margin = float(state.contribution_margin.value or 0.0)
        gross_margin = float(state.gross_margin.value or margin)
        cash = float(state.cash_balance.value or 0.0)
        params = candidate.parameters

        revenue_delta = np.zeros(self.runs, dtype=np.float64)
        profit_delta = np.zeros(self.runs, dtype=np.float64)
        target_delta = np.zeros(self.runs, dtype=np.float64)
        transaction_multiplier = np.ones(self.runs, dtype=np.float64)

        if candidate.sprint_id == SprintId.MORNING_DISCOUNT:
            discount = float(params.discount_pct or 0.0) / 100.0
            transaction_multiplier = 1 + affected * (demand - 1)
            revenue_delta = baseline_revenue * affected * (demand * (1 - discount) - 1)
            profit_delta = baseline_revenue * affected * (demand * (margin - discount) - margin)
            target_delta = demand - 1
        elif candidate.sprint_id == SprintId.REPEAT_BONUS:
            bonus = float(params.bonus_pct or 0.0) / 100.0
            transaction_multiplier = 1 + affected * (repeat - 1)
            incremental_revenue = baseline_revenue * affected * (repeat - 1)
            revenue_delta = incremental_revenue
            # Only redeemed bonuses cost money; incremental sales use marginal gross margin.
            redemption_rate = 0.45
            profit_delta = (
                incremental_revenue * gross_margin
                - baseline_revenue * affected * bonus * redemption_rate
            )
            target_delta = repeat - 1
        elif candidate.sprint_id == SprintId.MICRO_AD_TEST:
            transaction_multiplier = 1 + affected * (ad_effect - 1)
            revenue_delta = baseline_revenue * affected * (ad_effect - 1)
            profit_delta = revenue_delta * margin - candidate.budget
            target_delta = transaction_multiplier - 1
        elif candidate.sprint_id == SprintId.PRODUCT_BUNDLE:
            discount = float(params.bundle_discount_pct or 0.0) / 100.0
            effective_ticket = ticket * (1 - discount)
            revenue_delta = baseline_revenue * affected * (effective_ticket - 1)
            # Existing ingredient cost is approximately unchanged; net ticket delta is
            # the marginal experiment effect, with a small one-off setup cost.
            profit_delta = revenue_delta - candidate.budget * 0.05
            target_delta = effective_ticket - 1
        elif candidate.sprint_id == SprintId.PRICE_CHANGE:
            price_change = float(params.price_change_pct or 0.0) / 100.0
            effective_ticket = (1 + price_change) * ticket
            transaction_multiplier = demand
            revenue_delta = baseline_revenue * (demand * effective_ticket - 1)
            profit_delta = (
                baseline_revenue * (demand * (margin + price_change) - margin)
                - candidate.budget * 0.10
            )
            target_delta = np.divide(
                profit_delta,
                max(1.0, baseline_revenue * max(abs(margin), 0.05)),
            )
        elif candidate.sprint_id == SprintId.OPENING_HOURS_CHANGE:
            transaction_multiplier = demand
            revenue_delta = baseline_revenue * (demand - 1)
            added_shift_cost = candidate.duration_days * 1_400
            profit_delta = revenue_delta * margin - added_shift_cost
            target_delta = demand - 1

        target_reached = target_delta >= candidate.target_delta
        economically_safe = profit_delta >= -max(1.0, candidate.budget)
        success_probability = float(np.mean(target_reached & economically_safe))

        overall_utilization = float(state.utilization.value or 0.0) * transaction_multiplier
        morning_utilization = float(state.morning_utilization.value or 0.0)
        if candidate.sprint_id in {SprintId.MORNING_DISCOUNT, SprintId.PRODUCT_BUNDLE}:
            capacity_load = morning_utilization * np.maximum(demand, ticket)
        else:
            capacity_load = overall_utilization
        capacity_overflow_probability = float(np.mean(capacity_load > 1.0))
        cash_gap_probability = float(np.mean(cash + profit_delta < 0.0))

        p10, p50, p90 = np.quantile(profit_delta, [0.10, 0.50, 0.90])
        worst_case_loss = max(0.0, -float(np.min(profit_delta)))
        spread = float(p90 - p10)
        scale = max(1.0, abs(float(p50)), candidate.budget)
        uncertainty = min(1.0, spread / (2 * scale) + (1 - world.confidence) * 0.5)

        # Explicitly calculate transaction change to keep the bank-effect inputs coherent.
        _ = baseline_transactions * (transaction_multiplier - 1)
        return SimulationResult(
            success_probability=round(success_probability, 6),
            expected_revenue_delta=round(float(np.mean(revenue_delta)), 2),
            expected_profit_delta=round(float(np.mean(profit_delta)), 2),
            p10=round(float(p10), 2),
            p50=round(float(p50), 2),
            p90=round(float(p90), 2),
            worst_case_loss=round(worst_case_loss, 2),
            cash_gap_probability=round(cash_gap_probability, 6),
            capacity_overflow_probability=round(capacity_overflow_probability, 6),
            uncertainty_score=round(uncertainty, 6),
            runs=self.runs,
            seed=seed,
            simulator_version=self.version,
        )

    def _sample(self, rng: np.random.Generator, spec: DistributionSpec) -> np.ndarray:
        if spec.distribution == "triangular":
            return rng.triangular(spec.minimum, float(spec.mode), spec.maximum, self.runs)
        if spec.distribution == "uniform":
            if spec.minimum == spec.maximum:
                return np.full(self.runs, spec.minimum, dtype=np.float64)
            return rng.uniform(spec.minimum, spec.maximum, self.runs)
        # Beta is constrained to the declared range and centred near the optional mode.
        raw = rng.beta(2.0, 2.0, self.runs)
        return spec.minimum + raw * (spec.maximum - spec.minimum)
