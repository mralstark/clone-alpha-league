from __future__ import annotations

import math

from app.config import Settings
from app.schemas import BankEffect, CandidateSpec, SimulationResult


class CandidateRanker:
    def __init__(self, settings: Settings):
        self.settings = settings

    def score(
        self,
        candidate: CandidateSpec,
        simulation: SimulationResult,
        bank_effect: BankEffect,
    ) -> float:
        scale = max(1_000.0, candidate.budget)
        profit_score = (math.tanh(simulation.expected_profit_delta / scale) + 1) / 2
        worst_case_penalty = min(1.0, simulation.worst_case_loss / max(scale, 1.0))
        cost_penalty = min(1.0, candidate.budget / max(self.settings.default_max_budget, 1.0))
        bank_score = (math.tanh(bank_effect.net_bank_effect / 1_000.0) + 1) / 2

        score = (
            self.settings.rank_success_weight * simulation.success_probability
            + self.settings.rank_profit_weight * profit_score
            - self.settings.rank_cash_risk_weight * simulation.cash_gap_probability
            - self.settings.rank_worst_case_weight * worst_case_penalty
            - self.settings.rank_cost_weight * cost_penalty
            - self.settings.rank_uncertainty_weight * simulation.uncertainty_score
            + self.settings.rank_bank_effect_weight * bank_score
        )
        return round(float(score), 6)
