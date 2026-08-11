from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any, Protocol

import yaml

from app.config import Settings
from app.schemas import BusinessState, CandidateSpec, DistributionSpec, WorldModelOutput


class WorldModelProvider(Protocol):
    name: str
    version: str

    def infer(self, state: BusinessState, candidate: CandidateSpec) -> WorldModelOutput: ...


class TemplateWorldModel:
    name = "TemplateWorldModel"

    def __init__(self, settings: Settings, priors_path: Path | None = None):
        self.version = settings.world_model_version
        self.priors_path = (
            priors_path or Path(__file__).parents[1] / "data" / "world_model_priors.yaml"
        )
        with self.priors_path.open("r", encoding="utf-8") as handle:
            self.priors: dict[str, dict[str, Any]] = yaml.safe_load(handle)

    def infer(self, state: BusinessState, candidate: CandidateSpec) -> WorldModelOutput:
        del state  # Priors consume only the validated action in the deterministic fallback.
        raw = deepcopy(self.priors[candidate.sprint_id.value])
        effects = [DistributionSpec.model_validate(item) for item in raw.get("effects", [])]
        return WorldModelOutput(
            effects=effects,
            assumptions=list(raw.get("assumptions", [])),
            confidence=float(raw.get("confidence", 0.5)),
            low_confidence_reasons=list(raw.get("low_confidence_reasons", [])),
            provider=self.name,
            version=self.version,
            fallback_used=False,
        )


class LLMWorldModel:
    """Optional structured provider; the injected callable owns transport/auth."""

    name = "LLMWorldModel"

    def __init__(
        self,
        generator: Callable[[dict[str, Any]], dict[str, Any]] | None,
        version: str = "llm-world-model-unconfigured",
    ):
        self.generator = generator
        self.version = version

    def infer(self, state: BusinessState, candidate: CandidateSpec) -> WorldModelOutput:
        if self.generator is None:
            raise RuntimeError("LLM world-model transport is not configured")
        safe_input = {
            "business_state": state.model_dump(mode="json"),
            "candidate": candidate.model_dump(mode="json"),
        }
        raw = self.generator(safe_input)
        raw["provider"] = self.name
        raw["version"] = self.version
        raw["fallback_used"] = False
        output = WorldModelOutput.model_validate(raw)
        return self._clamp(output)

    @staticmethod
    def _clamp(output: WorldModelOutput) -> WorldModelOutput:
        clamped: list[DistributionSpec] = []
        for effect in output.effects:
            minimum = max(-2.0, min(3.0, effect.minimum))
            maximum = max(minimum, min(3.0, effect.maximum))
            mode = effect.mode
            if mode is not None:
                mode = max(minimum, min(maximum, mode))
            clamped.append(
                effect.model_copy(update={"minimum": minimum, "maximum": maximum, "mode": mode})
            )
        return output.model_copy(update={"effects": clamped})


class ResilientWorldModel:
    def __init__(self, primary: WorldModelProvider, fallback: TemplateWorldModel):
        self.primary = primary
        self.fallback = fallback
        self.last_error: str | None = None

    def infer(self, state: BusinessState, candidate: CandidateSpec) -> WorldModelOutput:
        self.last_error = None
        try:
            return self.primary.infer(state, candidate)
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            fallback = self.fallback.infer(state, candidate)
            return fallback.model_copy(update={"fallback_used": True})
