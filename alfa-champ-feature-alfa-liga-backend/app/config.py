from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Alfa Liga Backend"
    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./alfa_liga.db"
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"]
    )

    monte_carlo_runs: int = Field(default=5_000, ge=100, le=100_000)
    data_coverage_threshold: float = Field(default=0.75, ge=0, le=1)
    default_max_budget: float = Field(default=10_000, ge=0)
    default_max_loss: float = Field(default=5_000, ge=0)
    default_min_cash_reserve: float = Field(default=50_000, ge=0)
    max_cash_gap_probability: float = Field(default=0.15, ge=0, le=1)
    max_capacity_overflow_probability: float = Field(default=0.20, ge=0, le=1)

    policy_provider: Literal["template", "local_lora", "remote"] = "template"
    world_model_provider: Literal["template", "llm"] = "template"
    base_model: str = "Qwen/Qwen1.5-0.5B"
    lora_adapter_path: str = "artifacts/stage2/lora_adapter"
    simulator_version: str = "coffee-mc-v1"
    policy_version: str = "template-policy-v1"
    world_model_version: str = "template-world-model-v1"
    stage2_model_version: str = "simulator-driven-v1-preregistered"

    bank_acquiring_fee_rate: float = Field(default=0.018, ge=0, le=1)
    bank_service_cost_per_sprint: float = Field(default=25, ge=0)

    rank_success_weight: float = 0.35
    rank_profit_weight: float = 0.25
    rank_cash_risk_weight: float = 0.20
    rank_worst_case_weight: float = 0.08
    rank_cost_weight: float = 0.05
    rank_uncertainty_weight: float = 0.04
    rank_bank_effect_weight: float = 0.03

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
