from __future__ import annotations

from typing import Any

ALFA_PRODUCT_CATALOG: dict[str, dict[str, Any]] = {
    "financial_analytics": {
        "name": "Финансовая аналитика",
        "description": "Агрегированные доходы, расходы и остатки для состояния бизнеса.",
        "actions": ["read_aggregated_financials"],
    },
    "market_pulse": {
        "name": "Пульс рынка",
        "description": "Сравнение агрегированных метрик с peer-когортой.",
        "actions": ["read_peer_benchmark"],
    },
    "neuro_office": {
        "name": "Нейроофис",
        "description": "Подготовка черновиков текстов, рекламы и документов.",
        "actions": ["prepare_campaign_materials", "prepare_offer_copy"],
    },
    "alfa_target": {
        "name": "Альфа-Таргет",
        "description": "Демонстрационный контур продвижения и проверки спроса.",
        "actions": ["prepare_micro_campaign"],
    },
    "risk_indicator": {
        "name": "Индикатор риска",
        "description": "Контроль рисков 115-ФЗ в доступном банковском контуре.",
        "actions": ["request_risk_check"],
    },
    "alfa_accounting": {
        "name": "Альфа-Бухгалтерия",
        "description": "Учёт налогов и бухгалтерских обязательств.",
        "actions": ["prepare_tax_effect_check"],
    },
    "alfa_kassa": {
        "name": "Альфа-Касса",
        "description": "Чеки и платёжная инфраструктура.",
        "actions": ["prepare_discount_rule", "prepare_bundle_rule"],
    },
    "acquiring": {
        "name": "Эквайринг",
        "description": "Агрегированные платёжные события и результат эксперимента.",
        "actions": ["read_payment_metrics", "measure_experiment_outcome"],
    },
    "one_business": {
        "name": "Один Бизнес",
        "description": "Сайт и интернет-магазин для малого бизнеса.",
        "actions": ["prepare_landing_update"],
    },
    "counterparty_check": {
        "name": "Проверка контрагентов",
        "description": "Проверка поставщиков перед изменением закупок.",
        "actions": ["request_supplier_check"],
    },
}


DEFAULT_ACTION_BY_PRODUCT = {
    "financial_analytics": "read_aggregated_financials",
    "market_pulse": "read_peer_benchmark",
    "neuro_office": "prepare_campaign_materials",
    "alfa_target": "prepare_micro_campaign",
    "risk_indicator": "request_risk_check",
    "alfa_accounting": "prepare_tax_effect_check",
    "alfa_kassa": "prepare_discount_rule",
    "acquiring": "measure_experiment_outcome",
    "one_business": "prepare_landing_update",
    "counterparty_check": "request_supplier_check",
}
