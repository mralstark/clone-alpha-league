from __future__ import annotations

import logging
import time
import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.services.prior_updater import BayesianPriorUpdater

from app.api import router
from app.config import Settings, get_settings
from app.db import Database
from app.fixtures import seed_demo_data
from app.logging import configure_logging
from app.services.business_state import BusinessStateAdapter
from app.services.decisions import DecisionService
from app.services.experiments import ExperimentService
from app.services.policy import (
    LocalQwenLoRAPolicy,
    RemoteLLMPolicy,
    ResilientPolicy,
    TemplatePolicy,
)
from app.services.precheck import HardPrecheck
from app.services.products import ProductGateway
from app.services.ranking import CandidateRanker
from app.services.simulator import MonteCarloSimulator
from app.services.world_model import (
    LLMWorldModel,
    ResilientWorldModel,
    TemplateWorldModel,
)

logger = logging.getLogger(__name__)
FRONTEND_DIR = Path(__file__).with_name("frontend")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    db = Database(settings.database_url)

    template_policy = TemplatePolicy()
    if settings.policy_provider == "local_lora":
        primary_policy = LocalQwenLoRAPolicy(settings.base_model, settings.lora_adapter_path)
    elif settings.policy_provider == "remote":
        primary_policy = RemoteLLMPolicy()
    else:
        primary_policy = template_policy
    policy = ResilientPolicy(primary_policy, template_policy)

    template_world = TemplateWorldModel(settings)
    if settings.world_model_provider == "llm":
        primary_world = LLMWorldModel(None)
    else:
        primary_world = template_world
    world_model = ResilientWorldModel(primary_world, template_world)

    state_adapter = BusinessStateAdapter()
    product_gateway = ProductGateway(settings)
    decision_service = DecisionService(
        settings=settings,
        state_adapter=state_adapter,
        policy=policy,
        precheck=HardPrecheck(settings),
        world_model=world_model,
        simulator=MonteCarloSimulator(settings),
        product_gateway=product_gateway,
        ranker=CandidateRanker(settings),
    )
    experiment_service = ExperimentService(product_gateway)

    async def scheduled_bayesian_update_loop(app: FastAPI, interval_seconds: int = 86400):
        """Фоновая задача периодического перерасчета priors."""
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                db_local = app.state.db

                def _job():
                    with db_local.session_factory() as session:
                        updater = BayesianPriorUpdater()
                        updater.run_update_pipeline(session)

                await asyncio.to_thread(_job)
            except Exception as e:
                logger.exception("[PriorUpdater Error] %s", e)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Ensure ORM models are imported so Base.metadata includes all tables (e.g., KnowledgeBaseEntry)
        # Use importlib to avoid binding the name 'app' in this function's locals
        import importlib
        importlib.import_module('app.models')  # noqa: F401

        db.create_schema()
        with db.session_factory() as session:
            seed_demo_data(session)
        logger.info("application_started")

        # Запуск фонового планировщика (раз в час на демо)
        task = asyncio.create_task(scheduled_bayesian_update_loop(app, interval_seconds=3600))
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            db.dispose()
            logger.info("application_stopped")

    api_app = FastAPI(
        title="Альфа-Лига API",
        version="0.1.0",
        description=(
            "Transparent business-decision simulation for a coffee-shop golden path. "
            "All Alfa product connectors are explicitly marked MOCK in this demo."
        ),
        lifespan=lifespan,
    )
    api_app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api_app.state.settings = settings
    api_app.state.db = db
    api_app.state.state_adapter = state_adapter
    api_app.state.product_gateway = product_gateway
    api_app.state.decision_service = decision_service
    api_app.state.experiment_service = experiment_service
    api_app.include_router(router)
    api_app.mount("/web", StaticFiles(directory=FRONTEND_DIR, html=True), name="web")

    @api_app.get("/", include_in_schema=False)
    def frontend_home() -> RedirectResponse:
        return RedirectResponse(url="/web/alfa-league.html")

    @api_app.middleware("http")
    async def request_log(request: Request, call_next):  # type: ignore[no-untyped-def]
        started = time.perf_counter()
        response = await call_next(request)
        logger.info(
            "request_completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1_000, 2),
            },
        )
        return response

    # Ensure DB schema exists and demo data seeded even if lifespan isn't entered (tests rely on this)
    # Avoid binding 'app' name in locals when importing submodules
    import importlib
    importlib.import_module('app.models')  # noqa: F401
    db.create_schema()
    with db.session_factory() as session:
        seed_demo_data(session)

    return api_app


