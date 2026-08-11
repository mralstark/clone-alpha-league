# Спринт 0 — аудит и фиксация контрактов

Дата аудита: 9 августа 2026 года.

## Исходное состояние

`ExpertDaniil/alfa-champ` был создан, но не содержал веток, commit’ов, README или исходного кода. Поэтому backend реализован как greenfield FastAPI-монолит; пользовательские изменения не удалялись и не переписывались.

Локальные исследовательские файлы Stage 0/1/2 не находились в GitHub-репозитории. Из них переиспользованы только проверенные факты для `/api/model/info` и архитектурные решения:

- base model — `Qwen/Qwen1.5-0.5B`;
- production baseline — LoRA-only;
- Stage 1 — `MIXED_ON_PRIMARY_METRIC` на пяти seed;
- staged LoRA→ReFT не включён в MVP;
- Stage 2 остаётся simulator-driven протоколом, а не заявлением о готовой RL-policy.

Весов LoRA в репозитории нет. `LocalQwenLoRAPolicy` реализован как optional provider; демонстрационный runtime использует `TemplatePolicy` или автоматически откатывается к нему.

## Разрешённые неоднозначности ТЗ

| Неоднозначность | Зафиксированный контракт |
|---|---|
| Stage 2 имеет 3 класса, backend также требует `NO_ACTION` | Stage 2 evaluator остаётся трёхклассовым; runtime backend поддерживает четвёртый безопасный исход `NO_ACTION`. |
| Policy предлагает пять спринтов, ответ содержит три карточки | Policy создаёт пять кандидатов; hard rules отделяют заблокированные; ranking возвращает до трёх лучших прошедших кандидатов. |
| «Интеграция с продуктами Альфы» без доказанного API | Только каталог, `ProductConnector` и mock-план. В каждом API-ответе статус `MOCK` и `requires_confirmation=true`. |
| LLM world model должен участвовать, но не считать числа | LLM/шаблон возвращает только причинные priors; арифметика, hard rules и Monte Carlo выполняются Python-кодом. |
| Resimulate должен быть мгновенным | Resimulate повторно запускает deterministic world prior + NumPy Monte Carlo, не вызывает Idea Policy/LLM. |

## Граница реальности

Реально работают: API, SQLite/PostgreSQL persistence, fixture, агрегирование состояния, action space, hard rules, YAML-priors, Monte Carlo, ranking, bank-effect assumptions, mock execution plan, experiments, outcomes и replay export.

Mock: доступ к системам Альфа-Банка, запуск рекламы, кассовых правил и материалов.

Optional/not bundled: локальные веса LoRA и транспорт remote LLM.

