from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    DecisionRequest,
    Experiment,
    ExperimentOutcome,
    SprintCandidate,
)
from app.schemas import (
    CandidateSpec,
    ExperimentCreate,
    ExperimentOutcomeCreate,
    ExperimentResponse,
    FinalDecision,
    ProductAction,
)
from app.services.products import ProductGateway


class ExperimentNotFoundError(LookupError):
    pass


class ExperimentValidationError(ValueError):
    pass


class ExperimentService:
    def __init__(self, product_gateway: ProductGateway):
        self.product_gateway = product_gateway

    def create(self, session: Session, request: ExperimentCreate) -> ExperimentResponse:
        if not request.confirmed:
            raise ExperimentValidationError("User confirmation is required before launch")
        candidate = session.get(SprintCandidate, request.candidate_id)
        if candidate is None:
            raise ExperimentValidationError("Candidate not found")
        if candidate.decision != FinalDecision.APPROVE.value or candidate.card is None:
            raise ExperimentValidationError("Only an APPROVE candidate can be launched")
        decision = session.get(DecisionRequest, candidate.decision_id)
        if decision is None:
            raise ExperimentValidationError("Parent decision not found")

        spec = CandidateSpec.model_validate(candidate.spec)
        execution_plan = self.product_gateway.execution_plan(session, spec)
        card = dict(candidate.card)
        experiment = Experiment(
            id=f"exp_{uuid4().hex}",
            candidate_id=candidate.id,
            business_id=decision.business_id,
            status="RUNNING",
            state_before=dict(decision.business_state),
            action=spec.model_dump(mode="json"),
            forecast=dict(card["simulation"]),
            execution_plan=[item.model_dump(mode="json") for item in execution_plan],
            model_versions=dict(decision.model_versions),
        )
        session.add(experiment)
        session.commit()
        return self._response(experiment, None)

    def record_outcome(
        self,
        session: Session,
        experiment_id: str,
        payload: ExperimentOutcomeCreate,
    ) -> ExperimentResponse:
        experiment = session.get(Experiment, experiment_id)
        if experiment is None:
            raise ExperimentNotFoundError(experiment_id)
        actual = payload.model_dump(mode="json", exclude={"state_after"})
        reward = self._reward(experiment.forecast, payload)
        outcome = session.scalar(
            select(ExperimentOutcome).where(ExperimentOutcome.experiment_id == experiment_id)
        )
        if outcome is None:
            outcome = ExperimentOutcome(
                id=f"out_{uuid4().hex}",
                experiment_id=experiment_id,
                actual_outcome=actual,
                state_after=payload.state_after,
                reward=reward,
            )
            session.add(outcome)
        else:
            outcome.actual_outcome = actual
            outcome.state_after = payload.state_after
            outcome.reward = reward

        experiment.status = "STOPPED" if payload.stopped_early else "COMPLETED"
        experiment.stopped_at = datetime.now(UTC)
        session.commit()
        return self._response(experiment, outcome)

    def get(self, session: Session, experiment_id: str) -> ExperimentResponse:
        experiment = session.get(Experiment, experiment_id)
        if experiment is None:
            raise ExperimentNotFoundError(experiment_id)
        outcome = session.scalar(
            select(ExperimentOutcome).where(ExperimentOutcome.experiment_id == experiment_id)
        )
        return self._response(experiment, outcome)

    def export_replay_jsonl(self, session: Session) -> str:
        rows = session.execute(
            select(Experiment, ExperimentOutcome)
            .join(
                ExperimentOutcome,
                ExperimentOutcome.experiment_id == Experiment.id,
            )
            .order_by(Experiment.started_at)
        ).all()
        lines: list[str] = []
        for experiment, outcome in rows:
            business_hash = hashlib.sha256(
                f"alfa-liga:{experiment.business_id}".encode()
            ).hexdigest()[:16]
            record = {
                "schema_version": "replay-v1",
                "business_hash": business_hash,
                "state": experiment.state_before,
                "action": experiment.action,
                "predicted_outcome": experiment.forecast,
                "actual_outcome": outcome.actual_outcome,
                "reward": outcome.reward,
                "model_versions": experiment.model_versions,
                "privacy": {
                    "contains_raw_transactions": False,
                    "contains_personal_data": False,
                },
            }
            lines.append(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
        return "\n".join(lines) + ("\n" if lines else "")

    @staticmethod
    def _reward(forecast: dict[str, object], actual: ExperimentOutcomeCreate) -> float:
        predicted = float(forecast.get("expected_profit_delta", 0.0))
        scale = max(1_000.0, abs(predicted), abs(actual.actual_profit_delta))
        profit_component = actual.actual_profit_delta / scale
        prediction_error = abs(actual.actual_profit_delta - predicted) / scale
        safety_penalty = 0.25 if actual.stopped_early and actual.actual_profit_delta < 0 else 0.0
        return round(
            max(-1.0, min(1.0, profit_component - 0.25 * prediction_error - safety_penalty)), 6
        )

    @staticmethod
    def _response(
        experiment: Experiment,
        outcome: ExperimentOutcome | None,
    ) -> ExperimentResponse:
        return ExperimentResponse(
            experiment_id=experiment.id,
            candidate_id=experiment.candidate_id,
            business_id=experiment.business_id,
            status=experiment.status,
            state_before=dict(experiment.state_before),
            action=dict(experiment.action),
            forecast=dict(experiment.forecast),
            execution_plan=[
                ProductAction.model_validate(item) for item in experiment.execution_plan
            ],
            model_versions=dict(experiment.model_versions),
            actual_outcome=dict(outcome.actual_outcome) if outcome else None,
            reward=outcome.reward if outcome else None,
            started_at=experiment.started_at,
            stopped_at=experiment.stopped_at,
        )
