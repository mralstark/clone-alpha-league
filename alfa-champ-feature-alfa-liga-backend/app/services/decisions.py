from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import DecisionRequest, SimulationRun, SprintCandidate
from app.schemas import (
    BankEffect,
    BlockedCandidate,
    BusinessState,
    CandidateSpec,
    DecisionCard,
    DecisionCreate,
    DecisionResponse,
    DecisionTrace,
    FinalDecision,
    ResimulateRequest,
    ResimulateResponse,
)
from app.services.business_state import BusinessStateAdapter
from app.services.policy import ResilientPolicy
from app.services.precheck import HardPrecheck, PrecheckOutcome
from app.services.products import ProductGateway
from app.services.ranking import CandidateRanker
from app.services.simulator import MonteCarloSimulator
from app.services.world_model import ResilientWorldModel


class DecisionNotFoundError(LookupError):
    pass


class CandidateNotFoundError(LookupError):
    pass


@dataclass
class EvaluatedCandidate:
    row: SprintCandidate
    simulation_row: SimulationRun | None
    card: DecisionCard | None
    blocked: BlockedCandidate | None
    rules: list[str]
    assumptions: list[str]
    risk_flags: list[str]
    reasons: list[str]


class DecisionService:
    def __init__(
        self,
        settings: Settings,
        state_adapter: BusinessStateAdapter,
        policy: ResilientPolicy,
        precheck: HardPrecheck,
        world_model: ResilientWorldModel,
        simulator: MonteCarloSimulator,
        product_gateway: ProductGateway,
        ranker: CandidateRanker,
    ):
        self.settings = settings
        self.state_adapter = state_adapter
        self.policy = policy
        self.precheck = precheck
        self.world_model = world_model
        self.simulator = simulator
        self.product_gateway = product_gateway
        self.ranker = ranker

    def create(self, session: Session, request: DecisionCreate) -> DecisionResponse:
        state = self.state_adapter.build(session, request.business_id)
        limits = self.precheck.resolve_limits(state, request.overrides)
        specs = self.policy.propose(state, request.request, request.mode)
        decision_id = f"dec_{uuid4().hex}"
        model_versions = self._model_versions()

        evaluated = [
            self._evaluate_candidate(
                session=session,
                decision_id=decision_id,
                state=state,
                spec=spec,
                limits=limits,
                seed=request.seed,
                ordinal=index,
                model_versions=model_versions,
            )
            for index, spec in enumerate(specs)
        ]
        cards = sorted(
            [item.card for item in evaluated if item.card is not None],
            key=lambda item: item.rank_score,
            reverse=True,
        )[:3]
        blocked = [item.blocked for item in evaluated if item.blocked is not None]
        trace = self._build_trace(state, evaluated, cards, model_versions)
        problem_summary = self._problem_summary(state, request.request)
        top_bank_effect = cards[0].bank_effect if cards else None

        session.add(
            DecisionRequest(
                id=decision_id,
                business_id=request.business_id,
                mode=request.mode.value,
                request_text=request.request,
                overrides=request.overrides.model_dump(mode="json", exclude_none=True),
                seed=request.seed,
                business_state=state.model_dump(mode="json"),
                problem_summary=problem_summary,
                decision_trace=trace.model_dump(mode="json"),
                bank_effect=(top_bank_effect.model_dump(mode="json") if top_bank_effect else {}),
                model_versions=model_versions,
            )
        )
        for item in evaluated:
            session.add(item.row)
            if item.simulation_row is not None:
                session.add(item.simulation_row)
        session.commit()

        return DecisionResponse(
            decision_id=decision_id,
            business_state=state,
            problem_summary=problem_summary,
            best_candidates=cards,
            blocked_candidates=blocked,
            decision_trace=trace,
            bank_effect=top_bank_effect,
            model_versions=model_versions,
        )

    def get(self, session: Session, decision_id: str) -> DecisionResponse:
        row = session.get(DecisionRequest, decision_id)
        if row is None:
            raise DecisionNotFoundError(decision_id)
        candidates = list(
            session.scalars(
                select(SprintCandidate)
                .where(SprintCandidate.decision_id == decision_id)
                .order_by(SprintCandidate.rank_score.desc().nullslast(), SprintCandidate.created_at)
            )
        )
        cards = [DecisionCard.model_validate(item.card) for item in candidates if item.card]
        cards = sorted(cards, key=lambda item: item.rank_score, reverse=True)[:3]
        blocked = [
            BlockedCandidate(
                candidate_id=item.id,
                sprint_id=item.sprint_id,
                name=item.title,
                decision=item.decision,
                reasons=list(item.reasons),
            )
            for item in candidates
            if not item.card
        ]
        bank_effect = BankEffect.model_validate(row.bank_effect) if row.bank_effect else None
        return DecisionResponse(
            decision_id=row.id,
            business_state=BusinessState.model_validate(row.business_state),
            problem_summary=row.problem_summary,
            best_candidates=cards,
            blocked_candidates=blocked,
            decision_trace=DecisionTrace.model_validate(row.decision_trace),
            bank_effect=bank_effect,
            model_versions=dict(row.model_versions),
        )

    def get_trace(self, session: Session, decision_id: str) -> DecisionTrace:
        row = session.get(DecisionRequest, decision_id)
        if row is None:
            raise DecisionNotFoundError(decision_id)
        return DecisionTrace.model_validate(row.decision_trace)

    def resimulate(
        self,
        session: Session,
        candidate_id: str,
        request: ResimulateRequest,
    ) -> ResimulateResponse:
        candidate_row = session.get(SprintCandidate, candidate_id)
        if candidate_row is None:
            raise CandidateNotFoundError(candidate_id)
        decision_row = session.get(DecisionRequest, candidate_row.decision_id)
        if decision_row is None:
            raise DecisionNotFoundError(candidate_row.decision_id)

        state = BusinessState.model_validate(decision_row.business_state)
        spec = CandidateSpec.model_validate(candidate_row.spec)
        updates: dict[str, Any] = {}
        if request.parameters is not None:
            parameter_updates = request.parameters.model_dump(exclude_unset=True)
            updates["parameters"] = spec.parameters.model_copy(update=parameter_updates)
        if request.budget is not None:
            updates["budget"] = request.budget
        if request.duration_days is not None:
            updates["duration_days"] = request.duration_days
        spec = spec.model_copy(update=updates)
        overrides = DecisionCreate.model_validate(
            {
                "business_id": decision_row.business_id,
                "mode": decision_row.mode,
                "request": decision_row.request_text,
                "overrides": decision_row.overrides,
                "seed": decision_row.seed,
            }
        ).overrides
        limits = self.precheck.resolve_limits(state, overrides)
        pre = self.precheck.check_before_simulation(state, spec, limits)
        candidate_row.spec = spec.model_dump(mode="json")

        if pre.decision != FinalDecision.APPROVE:
            candidate_row.decision = pre.decision.value
            candidate_row.reasons = pre.reasons
            candidate_row.rank_score = None
            candidate_row.card = None
            session.commit()
            return ResimulateResponse(
                candidate_id=candidate_id,
                decision=pre.decision,
                reasons=pre.reasons,
                card=None,
                simulation=None,
            )

        world = self.world_model.infer(state, spec)
        seed = request.seed
        if seed is None:
            seed = self.simulator.candidate_seed(decision_row.seed, spec.sprint_id)
        simulation = self.simulator.simulate(state, spec, world, seed)
        post = self.precheck.check_after_simulation(simulation, limits)
        simulation_row = SimulationRun(
            id=f"sim_{uuid4().hex}",
            candidate_id=candidate_id,
            seed=seed,
            simulator_version=simulation.simulator_version,
            input_data={
                "business_state": state.model_dump(mode="json"),
                "candidate": spec.model_dump(mode="json"),
                "world_model": world.model_dump(mode="json"),
                "resimulation": True,
            },
            output_data=simulation.model_dump(mode="json"),
        )
        session.add(simulation_row)

        if post.decision == FinalDecision.BLOCK:
            candidate_row.decision = FinalDecision.BLOCK.value
            candidate_row.reasons = post.reasons
            candidate_row.rank_score = None
            candidate_row.card = None
            session.commit()
            return ResimulateResponse(
                candidate_id=candidate_id,
                decision=FinalDecision.BLOCK,
                reasons=post.reasons,
                card=None,
                simulation=simulation,
            )

        products = self.product_gateway.execution_plan(session, spec)
        bank_effect = self.product_gateway.bank_effect(state, spec, simulation, products)
        score = self.ranker.score(spec, simulation, bank_effect)
        card = self._card(
            candidate_id,
            state,
            spec,
            simulation,
            bank_effect,
            products,
            world.assumptions,
            post.risk_flags,
            score,
        )
        candidate_row.decision = FinalDecision.APPROVE.value
        candidate_row.reasons = post.reasons
        candidate_row.rank_score = score
        candidate_row.card = card.model_dump(mode="json")
        session.commit()
        return ResimulateResponse(
            candidate_id=candidate_id,
            decision=FinalDecision.APPROVE,
            reasons=post.reasons,
            card=card,
            simulation=simulation,
        )

    def _evaluate_candidate(
        self,
        *,
        session: Session,
        decision_id: str,
        state: BusinessState,
        spec: CandidateSpec,
        limits: Any,
        seed: int,
        ordinal: int,
        model_versions: dict[str, str],
    ) -> EvaluatedCandidate:
        del model_versions
        candidate_id = f"cand_{uuid4().hex}"
        pre = self.precheck.check_before_simulation(state, spec, limits)
        if pre.decision != FinalDecision.APPROVE:
            row = self._candidate_row(candidate_id, decision_id, spec, pre)
            return EvaluatedCandidate(
                row=row,
                simulation_row=None,
                card=None,
                blocked=BlockedCandidate(
                    candidate_id=candidate_id,
                    sprint_id=spec.sprint_id,
                    name=spec.title,
                    decision=pre.decision,
                    reasons=pre.reasons,
                ),
                rules=pre.rules_fired,
                assumptions=[],
                risk_flags=pre.risk_flags,
                reasons=pre.reasons,
            )

        world = self.world_model.infer(state, spec)
        simulation_seed = self.simulator.candidate_seed(seed, spec.sprint_id, ordinal)
        simulation = self.simulator.simulate(state, spec, world, simulation_seed)
        post = self.precheck.check_after_simulation(simulation, limits)
        simulation_row = SimulationRun(
            id=f"sim_{uuid4().hex}",
            candidate_id=candidate_id,
            seed=simulation_seed,
            simulator_version=simulation.simulator_version,
            input_data={
                "business_state": state.model_dump(mode="json"),
                "candidate": spec.model_dump(mode="json"),
                "world_model": world.model_dump(mode="json"),
                "resimulation": False,
            },
            output_data=simulation.model_dump(mode="json"),
        )

        combined_rules = [*pre.rules_fired, *post.rules_fired]
        combined_reasons = [*pre.reasons, *post.reasons]
        combined_risks = [*pre.risk_flags, *post.risk_flags]
        if world.fallback_used:
            combined_rules.append("WORLD_MODEL_FALLBACK")
        if post.decision == FinalDecision.BLOCK:
            outcome = PrecheckOutcome(
                FinalDecision.BLOCK,
                post.reasons,
                combined_rules,
                combined_risks,
            )
            row = self._candidate_row(candidate_id, decision_id, spec, outcome)
            return EvaluatedCandidate(
                row=row,
                simulation_row=simulation_row,
                card=None,
                blocked=BlockedCandidate(
                    candidate_id=candidate_id,
                    sprint_id=spec.sprint_id,
                    name=spec.title,
                    decision=FinalDecision.BLOCK,
                    reasons=post.reasons,
                ),
                rules=combined_rules,
                assumptions=world.assumptions,
                risk_flags=combined_risks,
                reasons=combined_reasons,
            )

        products = self.product_gateway.execution_plan(session, spec)
        bank_effect = self.product_gateway.bank_effect(state, spec, simulation, products)
        score = self.ranker.score(spec, simulation, bank_effect)
        risks = list(combined_risks)
        if simulation.expected_profit_delta < 0:
            risks.append("EXPECTED_PROFIT_NEGATIVE")
        risks.extend(world.low_confidence_reasons)
        risks = self._unique(risks)
        card = self._card(
            candidate_id,
            state,
            spec,
            simulation,
            bank_effect,
            products,
            world.assumptions,
            risks,
            score,
        )
        row = SprintCandidate(
            id=candidate_id,
            decision_id=decision_id,
            sprint_id=spec.sprint_id.value,
            title=spec.title,
            spec=spec.model_dump(mode="json"),
            decision=FinalDecision.APPROVE.value,
            reasons=combined_reasons,
            rank_score=score,
            card=card.model_dump(mode="json"),
        )
        return EvaluatedCandidate(
            row=row,
            simulation_row=simulation_row,
            card=card,
            blocked=None,
            rules=combined_rules,
            assumptions=world.assumptions,
            risk_flags=risks,
            reasons=combined_reasons,
        )

    @staticmethod
    def _candidate_row(
        candidate_id: str,
        decision_id: str,
        spec: CandidateSpec,
        outcome: PrecheckOutcome,
    ) -> SprintCandidate:
        return SprintCandidate(
            id=candidate_id,
            decision_id=decision_id,
            sprint_id=spec.sprint_id.value,
            title=spec.title,
            spec=spec.model_dump(mode="json"),
            decision=outcome.decision.value,
            reasons=outcome.reasons,
            rank_score=None,
            card=None,
        )

    def _card(
        self,
        candidate_id: str,
        state: BusinessState,
        spec: CandidateSpec,
        simulation: Any,
        bank_effect: BankEffect,
        products: list[Any],
        assumptions: list[str],
        risks: list[str],
        rank_score: float,
    ) -> DecisionCard:
        facts = [
            f"repeat_rate={float(state.repeat_rate.value or 0):.1%}",
            f"peer_gap={float(state.peer_gap.value or 0):.1%}",
            f"contribution_margin={float(state.contribution_margin.value or 0):.1%}",
            f"morning_utilization={float(state.morning_utilization.value or 0):.1%}",
            f"cash_balance={float(state.cash_balance.value or 0):.0f} ₽",
        ]
        return DecisionCard(
            candidate_id=candidate_id,
            sprint_id=spec.sprint_id,
            name=spec.title,
            decision=FinalDecision.APPROVE,
            budget=spec.budget,
            duration_days=spec.duration_days,
            kpi_success_probability=simulation.success_probability,
            p10=simulation.p10,
            p50=simulation.p50,
            p90=simulation.p90,
            expected_financial_effect=simulation.expected_profit_delta,
            worst_case_loss=simulation.worst_case_loss,
            risks=self._unique(risks),
            facts=facts,
            assumptions=self._unique(assumptions),
            stop_conditions=spec.stop_conditions,
            recommended_products=products,
            requires_confirmation=any(item.requires_confirmation for item in products),
            bank_effect=bank_effect,
            rank_score=rank_score,
            simulation=simulation,
        )

    def _build_trace(
        self,
        state: BusinessState,
        evaluated: list[EvaluatedCandidate],
        cards: list[DecisionCard],
        model_versions: dict[str, str],
    ) -> DecisionTrace:
        facts = [
            (
                "Агрегаты рассчитаны из 60-дневного synthetic fixture; "
                "raw transactions не передавались policy."
            ),
            f"repeat_rate={float(state.repeat_rate.value or 0):.1%}",
            f"peer_gap={float(state.peer_gap.value or 0):.1%}",
            f"contribution_margin={float(state.contribution_margin.value or 0):.1%}",
            f"cash_balance={float(state.cash_balance.value or 0):.0f} ₽",
            f"data_coverage={float(state.data_coverage.value or 0):.1%}",
        ]
        rules = self._unique(item for result in evaluated for item in result.rules)
        if self.policy.last_fallback_used:
            rules.append("POLICY_FALLBACK_TO_TEMPLATE")
        assumptions = self._unique(item for result in evaluated for item in result.assumptions)
        if self.policy.last_fallback_used and self.policy.last_error:
            assumptions.append(f"Primary policy unavailable: {self.policy.last_error}")
        forecasts = [
            (
                f"{card.sprint_id.value}: success={card.kpi_success_probability:.1%}, "
                f"profit p10/p50/p90={card.p10:.0f}/{card.p50:.0f}/{card.p90:.0f} ₽"
            )
            for card in cards
        ]
        risk_flags = self._unique(item for result in evaluated for item in result.risk_flags)
        reasons = self._unique(item for result in evaluated for item in result.reasons)
        return DecisionTrace(
            facts_used=facts,
            missing_data=list(state.missing_fields),
            rules_fired=rules,
            assumptions=assumptions,
            numeric_forecasts=forecasts,
            risk_flags=risk_flags,
            decision_reasons=reasons,
            model_versions=model_versions,
        )

    @staticmethod
    def _problem_summary(state: BusinessState, user_request: str) -> str:
        repeat = float(state.repeat_rate.value or 0.0)
        peer_gap = float(state.peer_gap.value or 0.0)
        morning = float(state.morning_utilization.value or 0.0)
        return (
            f"Запрос: {user_request} Повторные покупки {repeat:.1%}, ниже peer на "
            f"{peer_gap:.1%}; утренняя загрузка {morning:.1%}. Нужен ограниченный "
            "обратимый тест с сохранением contribution margin и денежного резерва."
        )

    def _model_versions(self) -> dict[str, str]:
        policy = self.policy.version
        if self.policy.last_fallback_used:
            policy = f"{policy} -> template-policy-v1 fallback"
        return {
            "policy": policy,
            "world_model": self.settings.world_model_version,
            "simulator": self.settings.simulator_version,
            "production_baseline": "LoRA-only; template fallback active",
        }

    @staticmethod
    def _unique(values: Iterable[str]) -> list[str]:
        return list(dict.fromkeys(value for value in values if value))
