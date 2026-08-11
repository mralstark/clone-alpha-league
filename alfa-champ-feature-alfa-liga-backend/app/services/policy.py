from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Protocol

from app.schemas import (
    BusinessState,
    CandidateParameters,
    CandidateSpec,
    DecisionMode,
    SprintId,
)


class PolicyUnavailable(RuntimeError):
    pass


class IdeaPolicy(Protocol):
    name: str
    version: str

    def propose(
        self,
        state: BusinessState,
        request: str,
        mode: DecisionMode,
    ) -> list[CandidateSpec]: ...


class TemplatePolicy:
    name = "TemplatePolicy"
    version = "template-policy-v1"

    def propose(
        self,
        state: BusinessState,
        request: str,
        mode: DecisionMode,
    ) -> list[CandidateSpec]:
        if mode == DecisionMode.EVALUATE:
            return [self._parse_user_action(request)]
        return self._generated_candidates(state)

    def _generated_candidates(self, state: BusinessState) -> list[CandidateSpec]:
        repeat_gap = float(state.peer_gap.value or 0.0)
        target_repeat_delta = max(0.03, min(0.10, repeat_gap * 0.45))
        return [
            CandidateSpec(
                sprint_id=SprintId.REPEAT_BONUS,
                title="Бонус за повторный визит",
                hypothesis="Ограниченный бонус повысит повторные покупки без общей скидки.",
                parameters=CandidateParameters(bonus_pct=7),
                budget=5_000,
                duration_days=14,
                target_metric="repeat_rate",
                target_delta=target_repeat_delta,
                required_data=["repeat_rate", "contribution_margin", "cash_balance"],
                stop_conditions=[
                    "Остановить, если накопленный убыток превысит 3500 рублей",
                    "Остановить, если contribution margin станет отрицательной",
                ],
                recommended_product_ids=["alfa_kassa", "acquiring"],
            ),
            CandidateSpec(
                sprint_id=SprintId.MORNING_DISCOUNT,
                title="Утренняя скидка 9%",
                hypothesis="Скидка только в слабые часы увеличит загрузку и сохранит маржу.",
                parameters=CandidateParameters(discount_pct=9, target_hours=[8, 9, 10]),
                budget=4_500,
                duration_days=10,
                target_metric="morning_utilization",
                target_delta=0.08,
                required_data=["morning_utilization", "contribution_margin", "cash_balance"],
                stop_conditions=[
                    "Остановить, если дневная прибыль ниже baseline три дня подряд",
                    "Остановить при убытке 3000 рублей",
                ],
                recommended_product_ids=["alfa_kassa", "neuro_office"],
            ),
            CandidateSpec(
                sprint_id=SprintId.MICRO_AD_TEST,
                title="Микротест локальной рекламы",
                hypothesis="Малый бюджет проверит спрос до масштабирования кампании.",
                parameters=CandidateParameters(ad_budget=6_000, target_hours=[8, 9, 10]),
                budget=6_000,
                duration_days=7,
                target_metric="new_transactions",
                target_delta=0.06,
                required_data=["transaction_count", "cash_balance"],
                stop_conditions=[
                    "Остановить при стоимости привлечения выше 700 рублей",
                    "Не увеличивать бюджет без подтверждения владельца",
                ],
                recommended_product_ids=["alfa_target", "neuro_office", "acquiring"],
            ),
            CandidateSpec(
                sprint_id=SprintId.PRODUCT_BUNDLE,
                title="Утренний набор кофе + выпечка",
                hypothesis="Набор повысит средний чек в часы свободной мощности.",
                parameters=CandidateParameters(bundle_discount_pct=6, target_hours=[8, 9, 10]),
                budget=3_000,
                duration_days=10,
                target_metric="average_ticket",
                target_delta=0.05,
                required_data=["average_ticket", "contribution_margin"],
                stop_conditions=[
                    "Остановить, если списания выпечки превысят baseline на 15%",
                    "Остановить при убытке 2500 рублей",
                ],
                recommended_product_ids=["alfa_kassa", "neuro_office"],
            ),
            CandidateSpec(
                sprint_id=SprintId.MORNING_DISCOUNT,
                title="Агрессивная утренняя скидка 19%",
                hypothesis="Высокая скидка может резко увеличить утренний поток.",
                parameters=CandidateParameters(discount_pct=19, target_hours=[8, 9, 10]),
                budget=9_500,
                duration_days=14,
                target_metric="morning_utilization",
                target_delta=0.18,
                required_data=["morning_utilization", "contribution_margin", "cash_balance"],
                stop_conditions=["Остановить при убытке 4000 рублей"],
                recommended_product_ids=["alfa_kassa", "alfa_target"],
            ),
        ]

    def _parse_user_action(self, request: str) -> CandidateSpec:
        lowered = request.lower().replace("ё", "е")
        percent = self._extract_percent(lowered)
        budget = self._extract_budget(lowered)
        duration = self._extract_duration(lowered)

        if any(token in lowered for token in ("ничего не", "без изменений", "no_action")):
            return CandidateSpec(
                sprint_id=SprintId.NO_ACTION,
                title="Сохранить текущую стратегию",
                hypothesis="Изменение не запускается до появления достаточного сигнала.",
                parameters=CandidateParameters(),
                budget=0,
                duration_days=7,
                target_metric="contribution_margin",
                target_delta=0,
                required_data=[],
                stop_conditions=["Повторно оценить состояние через 7 дней"],
                recommended_product_ids=[],
            )

        if any(token in lowered for token in ("скид", "снизить цену", "дешевле")):
            discount = percent if percent is not None else 10.0
            return CandidateSpec(
                sprint_id=SprintId.MORNING_DISCOUNT,
                title=f"Проверка скидки {discount:g}%",
                hypothesis="Ограниченная скидка может увеличить спрос в слабые часы.",
                parameters=CandidateParameters(
                    discount_pct=discount,
                    target_hours=self._extract_target_hours(lowered) or [8, 9, 10],
                ),
                budget=budget if budget is not None else 4_500,
                duration_days=duration,
                target_metric="morning_utilization",
                target_delta=0.08,
                required_data=["morning_utilization", "contribution_margin", "cash_balance"],
                stop_conditions=[
                    "Остановить при отрицательной дневной contribution margin",
                    "Остановить при убытке 3000 рублей",
                ],
                recommended_product_ids=["alfa_kassa", "neuro_office"],
            )

        if "бонус" in lowered or "повторн" in lowered:
            bonus = percent if percent is not None else 7.0
            return CandidateSpec(
                sprint_id=SprintId.REPEAT_BONUS,
                title=f"Проверка бонуса {bonus:g}%",
                hypothesis="Бонус после покупки может увеличить долю повторных визитов.",
                parameters=CandidateParameters(bonus_pct=bonus),
                budget=budget if budget is not None else 5_000,
                duration_days=duration,
                target_metric="repeat_rate",
                target_delta=0.05,
                required_data=["repeat_rate", "contribution_margin", "cash_balance"],
                stop_conditions=[
                    "Остановить при убытке 3500 рублей",
                    "Остановить при отрицательной contribution margin",
                ],
                recommended_product_ids=["alfa_kassa", "acquiring"],
            )

        if "реклам" in lowered or "таргет" in lowered:
            ad_budget = (
                budget if budget is not None else self._extract_largest_number(lowered) or 6_000
            )
            return CandidateSpec(
                sprint_id=SprintId.MICRO_AD_TEST,
                title="Проверка рекламного бюджета",
                hypothesis="Ограниченная кампания проверит инкрементальный спрос.",
                parameters=CandidateParameters(ad_budget=ad_budget),
                budget=ad_budget,
                duration_days=duration,
                target_metric="new_transactions",
                target_delta=0.06,
                required_data=["transaction_count", "cash_balance"],
                stop_conditions=[
                    "Остановить при стоимости привлечения выше 700 рублей",
                    "Не увеличивать бюджет автоматически",
                ],
                recommended_product_ids=["alfa_target", "neuro_office", "acquiring"],
            )

        if any(token in lowered for token in ("набор", "комбо", "кофе +", "кофе и выпеч")):
            bundle_discount = percent if percent is not None else 6.0
            return CandidateSpec(
                sprint_id=SprintId.PRODUCT_BUNDLE,
                title=f"Проверка продуктового набора со скидкой {bundle_discount:g}%",
                hypothesis="Ограниченный набор может повысить средний чек.",
                parameters=CandidateParameters(
                    bundle_discount_pct=bundle_discount,
                    target_hours=self._extract_target_hours(lowered),
                ),
                budget=budget or 3_000,
                duration_days=duration,
                target_metric="average_ticket",
                target_delta=0.05,
                required_data=["average_ticket", "contribution_margin"],
                stop_conditions=["Остановить при росте списаний более чем на 15%"],
                recommended_product_ids=["alfa_kassa", "neuro_office"],
            )

        if any(token in lowered for token in ("открывать", "закрывать", "часы работы", "график")):
            hours = [int(item) for item in re.findall(r"(?<!\d)([0-2]?\d)(?::\d{2})?", lowered)]
            opening = hours[0] if hours else 7
            closing = hours[1] if len(hours) > 1 else 20
            return CandidateSpec(
                sprint_id=SprintId.OPENING_HOURS_CHANGE,
                title="Проверка изменения часов работы",
                hypothesis="Обратимый тест графика проверит спрос вне текущих часов.",
                parameters=CandidateParameters(
                    opening_hour=min(23, opening), closing_hour=min(23, closing)
                ),
                budget=budget or 8_000,
                duration_days=duration,
                target_metric="transaction_count",
                target_delta=0.04,
                required_data=["transaction_count", "cash_balance", "utilization"],
                stop_conditions=["Остановить, если дополнительная смена убыточна 3 дня подряд"],
                recommended_product_ids=["financial_analytics", "acquiring"],
            )

        if "цен" in lowered:
            change = percent if percent is not None else 5.0
            if any(token in lowered for token in ("сниз", "уменьш")):
                change = -abs(change)
            return CandidateSpec(
                sprint_id=SprintId.PRICE_CHANGE,
                title=f"Проверка изменения цены на {change:g}%",
                hypothesis="Обратимый тест цены проверит эластичность спроса.",
                parameters=CandidateParameters(price_change_pct=change),
                budget=budget or 2_000,
                duration_days=duration,
                target_metric="contribution_margin",
                target_delta=0.03,
                required_data=["average_ticket", "contribution_margin"],
                stop_conditions=["Остановить при падении транзакций более чем на 12%"],
                recommended_product_ids=["alfa_kassa", "acquiring"],
            )

        return CandidateSpec(
            sprint_id=SprintId.REQUEST_DATA,
            title="Уточнить параметры решения",
            hypothesis="Без типа действия невозможно выполнить безопасный расчёт.",
            parameters=CandidateParameters(),
            budget=0,
            duration_days=7,
            target_metric="data_coverage",
            target_delta=0,
            required_data=["action_type", "budget", "duration_days"],
            stop_conditions=["Не запускать действие до уточнения параметров"],
            recommended_product_ids=["financial_analytics"],
        )

    @staticmethod
    def _extract_percent(text: str) -> float | None:
        match = re.search(r"(\d+(?:[.,]\d+)?)\s*%", text)
        if match:
            return float(match.group(1).replace(",", "."))
        if "десятую часть" in text:
            return 10.0
        return None

    @staticmethod
    def _extract_budget(text: str) -> float | None:
        patterns = [
            r"бюджет(?:ом|а)?\s*(?:в|до|=|:)?\s*(\d[\d\s]*)",
            r"(\d[\d\s]*)\s*(?:руб(?:лей|ля)?|₽)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return float(match.group(1).replace(" ", ""))
        return None

    @staticmethod
    def _extract_largest_number(text: str) -> float | None:
        values = [float(item.replace(" ", "")) for item in re.findall(r"\d[\d\s]*", text)]
        return max(values) if values else None

    @staticmethod
    def _extract_duration(text: str) -> int:
        match = re.search(r"(?:на|сроком)\s*(\d+)\s*(?:дн|день|дня|дней)", text)
        return int(match.group(1)) if match else 10

    @staticmethod
    def _extract_target_hours(text: str) -> list[int]:
        before = re.search(r"до\s*(\d{1,2})(?::\d{2})?", text)
        if before:
            end = min(23, int(before.group(1)))
            return list(range(8, max(9, end)))
        return []


class LocalQwenLoRAPolicy:
    """Optional provider. Loading is lazy; deterministic fallback owns availability."""

    name = "LocalQwenLoRAPolicy"
    version = "lora-only-stage1"

    def __init__(self, base_model: str, adapter_path: str):
        self.base_model = base_model
        self.adapter_path = Path(adapter_path)
        self._model: Any | None = None
        self._tokenizer: Any | None = None

    def propose(
        self,
        state: BusinessState,
        request: str,
        mode: DecisionMode,
    ) -> list[CandidateSpec]:
        if not self.adapter_path.exists():
            raise PolicyUnavailable(f"LoRA adapter not found: {self.adapter_path}")
        model, tokenizer, torch = self._load()
        prompt = self._safe_prompt(state, request, mode)
        device = next(model.parameters()).device
        tokens = tokenizer(prompt, return_tensors="pt").to(device)
        with torch.inference_mode():
            output = model.generate(**tokens, max_new_tokens=512, do_sample=False)
        generated = tokenizer.decode(
            output[0][tokens["input_ids"].shape[1] :], skip_special_tokens=True
        )
        try:
            payload = json.loads(generated)
            items = payload if isinstance(payload, list) else payload["candidates"]
            return [CandidateSpec.model_validate(item) for item in items]
        except Exception as exc:
            raise PolicyUnavailable("LoRA output failed strict CandidateSpec validation") from exc

    def _load(self) -> tuple[Any, Any, Any]:
        try:
            import torch
            from peft import PeftModel
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise PolicyUnavailable("ML optional dependencies are not installed") from exc
        if self._model is None or self._tokenizer is None:
            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            dtype = torch.float16 if device.type == "cuda" else torch.float32
            tokenizer = AutoTokenizer.from_pretrained(self.base_model, local_files_only=True)
            base = AutoModelForCausalLM.from_pretrained(
                self.base_model,
                local_files_only=True,
                torch_dtype=dtype,
            )
            model = PeftModel.from_pretrained(
                base,
                str(self.adapter_path),
                local_files_only=True,
            )
            model.to(device)
            model.eval()
            self._model = model
            self._tokenizer = tokenizer
        return self._model, self._tokenizer, torch

    @staticmethod
    def _safe_prompt(state: BusinessState, request: str, mode: DecisionMode) -> str:
        # Only aggregated state is serialized. There are no transaction rows in this object.
        payload = {
            "mode": mode.value,
            "request": request,
            "business_state": state.model_dump(mode="json"),
            "allowed_sprints": [item.value for item in SprintId],
        }
        return "Return strict JSON candidates only.\n" + json.dumps(payload, ensure_ascii=False)


class RemoteLLMPolicy:
    name = "RemoteLLMPolicy"
    version = "remote-not-configured"

    def propose(
        self,
        state: BusinessState,
        request: str,
        mode: DecisionMode,
    ) -> list[CandidateSpec]:
        raise PolicyUnavailable("Remote provider is intentionally not configured in the demo")


class ResilientPolicy:
    def __init__(self, primary: IdeaPolicy, fallback: IdeaPolicy | None = None):
        self.primary = primary
        self.fallback = fallback or TemplatePolicy()
        self.last_fallback_used = False
        self.last_error: str | None = None

    @property
    def name(self) -> str:
        return self.primary.name

    @property
    def version(self) -> str:
        return self.primary.version

    def propose(
        self,
        state: BusinessState,
        request: str,
        mode: DecisionMode,
    ) -> list[CandidateSpec]:
        self.last_fallback_used = False
        self.last_error = None
        try:
            return self.primary.propose(state, request, mode)
        except Exception as exc:
            self.last_fallback_used = True
            self.last_error = f"{type(exc).__name__}: {exc}"
            return self.fallback.propose(state, request, mode)
