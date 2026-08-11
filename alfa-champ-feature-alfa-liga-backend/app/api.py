from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas import (
    BusinessState,
    DecisionCreate,
    DecisionResponse,
    DecisionTrace,
    ExperimentCreate,
    ExperimentOutcomeCreate,
    ExperimentResponse,
    HealthResponse,
    ModelInfo,
    ProductInfo,
    ResimulateRequest,
    ResimulateResponse,
)
from app.services.business_state import BusinessNotFoundError
from app.services.decisions import (
    CandidateNotFoundError,
    DecisionNotFoundError,
)
from app.services.experiments import (
    ExperimentNotFoundError,
    ExperimentValidationError,
)

router = APIRouter(prefix="/api")


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.db.session_factory() as session:
        yield session


@router.get("/health", response_model=HealthResponse)
def health(request: Request, session: Session = Depends(get_session)) -> HealthResponse:
    session.execute(text("SELECT 1"))
    settings = request.app.state.settings
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        environment=settings.app_env,
        database="ok",
    )


@router.get("/model/info", response_model=ModelInfo)
def model_info(request: Request) -> ModelInfo:
    settings = request.app.state.settings
    return ModelInfo(
        runtime_policy=(f"{settings.policy_provider}; deterministic TemplatePolicy fallback"),
        base_model=settings.base_model,
        lora_adapter=settings.lora_adapter_path,
        production_baseline="LoRA-only",
        stage0={
            "status": "PASS_TECHNICAL_FEASIBILITY",
            "model": "Qwen/Qwen1.5-0.5B",
            "reft_trainable_parameters": 8_196,
            "peak_vram_mib": 1_522,
            "validation_loss_initial": 2.3876,
            "validation_loss_final": 2.3552,
        },
        stage1={
            "status": "MIXED_ON_PRIMARY_METRIC",
            "seeds": 5,
            "lora_only_standard_loss": 0.05705,
            "lora_only_standard_em": 0.695,
            "joint_from_start_standard_loss": 0.05601,
            "staged_standard_loss": 0.05649,
            "conclusion": (
                "Staged benefit was not statistically stable and did not improve "
                "structured generation."
            ),
        },
        reft_decision=(
            "ReFT remains a research branch; staged LoRA→ReFT is excluded from the MVP baseline."
        ),
        stage2_model_version=settings.stage2_model_version,
        simulator_version=settings.simulator_version,
        honest_limitations=[
            (
                "The repository does not contain trained adapter weights; "
                "template fallback is the demo default."
            ),
            "Alfa product integrations are MOCK plans and do not claim undocumented public APIs.",
            "World-model priors and bank economics are demonstration assumptions.",
            "The replay loop is RL-ready; no online RL or production RL policy is claimed.",
        ],
    )


@router.get("/products", response_model=list[ProductInfo])
def products(request: Request, session: Session = Depends(get_session)) -> list[ProductInfo]:
    return request.app.state.product_gateway.list_products(session)


@router.get("/businesses/{business_id}/state", response_model=BusinessState)
def business_state(
    business_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> BusinessState:
    try:
        return request.app.state.state_adapter.build(session, business_id)
    except BusinessNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Business not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/decisions",
    response_model=DecisionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_decision(
    payload: DecisionCreate,
    request: Request,
    session: Session = Depends(get_session),
) -> DecisionResponse:
    try:
        return request.app.state.decision_service.create(session, payload)
    except BusinessNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Business not found") from exc


@router.get("/decisions/{decision_id}", response_model=DecisionResponse)
def get_decision(
    decision_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> DecisionResponse:
    try:
        return request.app.state.decision_service.get(session, decision_id)
    except DecisionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Decision not found") from exc


@router.get("/decisions/{decision_id}/trace", response_model=DecisionTrace)
def get_decision_trace(
    decision_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> DecisionTrace:
    try:
        return request.app.state.decision_service.get_trace(session, decision_id)
    except DecisionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Decision not found") from exc


@router.post(
    "/candidates/{candidate_id}/resimulate",
    response_model=ResimulateResponse,
)
def resimulate_candidate(
    candidate_id: str,
    payload: ResimulateRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> ResimulateResponse:
    try:
        return request.app.state.decision_service.resimulate(session, candidate_id, payload)
    except CandidateNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Candidate not found") from exc
    except DecisionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Decision not found") from exc


@router.post(
    "/experiments",
    response_model=ExperimentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_experiment(
    payload: ExperimentCreate,
    request: Request,
    session: Session = Depends(get_session),
) -> ExperimentResponse:
    try:
        return request.app.state.experiment_service.create(session, payload)
    except ExperimentValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.patch(
    "/experiments/{experiment_id}/outcome",
    response_model=ExperimentResponse,
)
def record_experiment_outcome(
    experiment_id: str,
    payload: ExperimentOutcomeCreate,
    request: Request,
    session: Session = Depends(get_session),
) -> ExperimentResponse:
    try:
        return request.app.state.experiment_service.record_outcome(session, experiment_id, payload)
    except ExperimentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Experiment not found") from exc


@router.get("/experiments/{experiment_id}", response_model=ExperimentResponse)
def get_experiment(
    experiment_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> ExperimentResponse:
    try:
        return request.app.state.experiment_service.get(session, experiment_id)
    except ExperimentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Experiment not found") from exc


@router.post("/training/export-replay", response_class=Response)
def export_replay(
    request: Request,
    session: Session = Depends(get_session),
) -> Response:
    content = request.app.state.experiment_service.export_replay_jsonl(session)
    return Response(
        content=content,
        media_type="application/x-ndjson",
        headers={"Content-Disposition": "attachment; filename=alfa_liga_replay.jsonl"},
    )
