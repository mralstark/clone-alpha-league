import logging
import math
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DecisionLog

logger = logging.getLogger("alfa_liga.prior_updater")


class BayesianPriorUpdater:
    """Сервис байесовского перерасчета априорных распределений для World Model."""

    def __init__(
        self,
        priors_path: str | Path = "app/data/world_model_priors.yaml",
        min_observations: int = 5,
        outlier_iqr_factor: float = 1.5,
        variance_floor: float = 1e-4,
    ):
        self.priors_path = Path(priors_path)
        self.min_observations = min_observations
        self.outlier_iqr_factor = outlier_iqr_factor
        self.variance_floor = variance_floor

    def filter_outliers(self, data: list[float]) -> list[float]:
        """Фильтрация аномалий (выбросов) через межквартильный размах (IQR)."""
        if len(data) < 4:
            return data

        q25, q75 = np.percentile(data, [25, 75])
        iqr = q75 - q25
        lower_bound = q25 - (self.outlier_iqr_factor * iqr)
        upper_bound = q75 + (self.outlier_iqr_factor * iqr)

        filtered = [x for x in data if lower_bound <= x <= upper_bound]
        return filtered if len(filtered) >= 2 else data

    def calculate_posterior(
        self,
        mu_0: float,
        sigma_0: float,
        observations: list[float],
    ) -> tuple[float, float, dict[str, Any]]:
        """Байесовский расчет апостериорного среднего (mu_new) и дисперсии (sigma_new)."""
        clean_obs = self.filter_outliers(observations)
        n = len(clean_obs)

        if n < self.min_observations:
            return mu_0, sigma_0, {"status": "skipped", "n_samples": n}

        x_bar = float(np.mean(clean_obs))
        sample_var = float(np.var(clean_obs, ddof=1)) if n > 1 else self.variance_floor

        # Дисперсия выборочного среднего: sigma_x^2 = s^2 / n
        sigma_x_sq = max(sample_var / n, self.variance_floor)
        sigma_0_sq = max(sigma_0**2, self.variance_floor)

        # Сопряженное нормальное обновление
        denominator = sigma_0_sq + sigma_x_sq
        mu_new = (sigma_0_sq * x_bar + sigma_x_sq * mu_0) / denominator
        sigma_new_sq = (sigma_0_sq * sigma_x_sq) / denominator
        sigma_new = math.sqrt(max(sigma_new_sq, self.variance_floor))

        stats = {
            "status": "updated",
            "n_samples": n,
            "sample_mean": round(x_bar, 4),
            "prior_mu": round(mu_0, 4),
            "posterior_mu": round(mu_new, 4),
            "posterior_sigma": round(sigma_new, 4),
        }

        return mu_new, sigma_new, stats

    def fetch_historical_facts(self, session: Session) -> dict[str, list[float]]:
        """Извлечение фактических приростов метрик из таблицы экспериментов (Experiment + ExperimentOutcome).

        Ожидаем, что Experiment.action содержит сериализованный CandidateSpec (dict) с keys 'sprint_id' и 'target_metric'.
        Из ExperimentOutcome.actual_outcome берем поле 'actual_target_delta' (если есть).
        """
        from app.models import Experiment, ExperimentOutcome
        stmt = select(Experiment, ExperimentOutcome).join(
            ExperimentOutcome, ExperimentOutcome.experiment_id == Experiment.id
        )
        result = session.execute(stmt).all()

        facts: dict[str, list[float]] = {}
        for experiment, outcome in result:
            try:
                action = experiment.action or {}
                sprint_id = action.get("sprint_id")
                target_metric = action.get("target_metric")
                if not sprint_id or not target_metric:
                    continue
                actual = outcome.actual_outcome or {}
                # prefer actual_target_delta when available
                if isinstance(actual, dict) and actual.get("actual_target_delta") is not None:
                    value = float(actual.get("actual_target_delta"))
                # fallback: try revenue/profit deltas if target not present
                elif isinstance(actual, dict) and actual.get("actual_revenue_delta") is not None:
                    value = float(actual.get("actual_revenue_delta"))
                elif isinstance(actual, dict) and actual.get("actual_profit_delta") is not None:
                    value = float(actual.get("actual_profit_delta"))
                else:
                    continue

                key = f"{sprint_id}:{target_metric}"
                facts.setdefault(key, []).append(value)
            except Exception:
                continue

        return facts

    def _atomic_yaml_write(self, data: dict[str, Any]) -> None:
        """Атомарная запись во избежание состояния гонки во время чтения симулятором."""
        dir_name = self.priors_path.parent
        dir_name.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, encoding="utf-8") as tf:
            yaml.dump(data, tf, default_flow_style=False, allow_unicode=True, sort_keys=False)
            temp_name = tf.name

        os.replace(temp_name, self.priors_path)

    def run_update_pipeline(self, session: Session) -> dict[str, Any]:
        """Запуск пайплайна перерасчета priors."""
        if not self.priors_path.exists():
            raise FileNotFoundError(f"Файл {self.priors_path} не найден.")

        with open(self.priors_path, "r", encoding="utf-8") as f:
            priors_config = yaml.safe_load(f) or {}

        historical_facts = self.fetch_historical_facts(session)
        audit_log = {}

        for category_name, category_data in priors_config.get("categories", {}).items():
            for sprint_id, sprint_priors in category_data.get("sprints", {}).items():
                target_metric = sprint_priors.get("target_metric")
                key = f"{sprint_id}:{target_metric}"

                if key in historical_facts:
                    obs = historical_facts[key]
                    mu_0 = sprint_priors.get("expected_delta_mu", 0.05)
                    sigma_0 = sprint_priors.get("expected_delta_sigma", 0.02)

                    mu_new, sigma_new, stats = self.calculate_posterior(mu_0, sigma_0, obs)

                    if stats["status"] == "updated":
                        sprint_priors["expected_delta_mu"] = mu_new
                        sprint_priors["expected_delta_sigma"] = sigma_new
                        sprint_priors["last_samples_count"] = stats["n_samples"]

                    audit_log[key] = stats

        self._atomic_yaml_write(priors_config)
        return audit_log
