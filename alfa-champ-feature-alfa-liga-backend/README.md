# Альфа-Лига — демонстрационный backend

Рабочий FastAPI-монолит для глубокой истории кофейни: агрегировать состояние бизнеса → предложить ограниченные спринты → применить hard rules → выполнить 5 000 Monte Carlo-прогонов → показать три сценария → запустить подтверждённый mock-эксперимент → сохранить outcome → экспортировать обезличенный replay.

Golden path не зависит от внешней LLM. Если локальная LoRA или remote provider недоступны, pipeline автоматически продолжает работу через deterministic `TemplatePolicy` и YAML-priors.

## Быстрый запуск с SQLite

```bash
python3.12 -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1  or .\.venv\Scripts\activate.bat
# Unix: source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env

# Create DB schema and run migrations
alembic upgrade head

# Recommended: start via the repository-root ASGI entrypoint
# (avoids package import-time side effects):
uvicorn asgi:app --host 0.0.0.0 --port 8000 --log-level info
```
После старта:

- web-интерфейс: `http://localhost:8000/`;
- Swagger UI: `http://localhost:8000/docs`
- OpenAPI: `http://localhost:8000/openapi.json`
- health: `http://localhost:8000/api/health`

Приложение идемпотентно создаёт demo fixture при первом старте. Его также можно подготовить явно:

```bash
python scripts/seed_demo.py
```

## Web-интерфейс

FastAPI раздаёт присланный frontend с того же origin по `/web`, поэтому отдельный Node-сервер и ручная настройка API URL не нужны:

- `/web/alfa-league.html` — главная Альфа-Лиги с live-выручкой;
- `/web/alfa-accounting.html` — бухгалтерия с агрегатами `BusinessState`;
- `/web/alfa-assistant.html` — рабочий клиент decision pipeline.

ИИ-ассистент загружает состояние `coffee_demo`, позволяет выбрать `GENERATE` или конкретный тип проверки, передаёт лимиты в `POST /api/decisions` и отображает настоящие карточки Monte Carlo. Из карточки можно выполнить deterministic resimulate или создать подтверждённый mock-эксперимент. Временная имитация ответа через `setTimeout` удалена.

## Docker + PostgreSQL

```bash
docker compose up --build
```

Compose поднимает PostgreSQL 16, ждёт healthcheck, применяет `alembic upgrade head` и публикует API на `localhost:8000`.

## Golden path через curl

Проверка состояния:

```bash
curl -s http://localhost:8000/api/health
curl -s http://localhost:8000/api/businesses/coffee_demo/state
curl -s http://localhost:8000/api/model/info
curl -s http://localhost:8000/api/products
```

Создание решения:

```bash
curl -s -X POST http://localhost:8000/api/decisions \
  -H 'Content-Type: application/json' \
  -d '{
    "business_id": "coffee_demo",
    "mode": "GENERATE",
    "request": "Как увеличить повторные покупки и не уйти в минус?",
    "overrides": {
      "max_budget": 10000,
      "max_loss": 5000,
      "min_cash_reserve": 50000
    },
    "seed": 42
  }' | tee decision.json
```

Контрфактуальная пара без вызова LLM:

```bash
curl -s -X POST http://localhost:8000/api/decisions \
  -H 'Content-Type: application/json' \
  -d '{"business_id":"coffee_demo","mode":"EVALUATE","request":"Дать скидку 9% утром","overrides":{"max_budget":10000,"max_loss":5000,"min_cash_reserve":50000},"seed":42}'

curl -s -X POST http://localhost:8000/api/decisions \
  -H 'Content-Type: application/json' \
  -d '{"business_id":"coffee_demo","mode":"EVALUATE","request":"Дать скидку 19% утром","overrides":{"max_budget":10000,"max_loss":5000,"min_cash_reserve":50000},"seed":42}'
```

Первая команда возвращает `APPROVE`; вторая — `BLOCK` и fired rule `NEGATIVE_CONTRIBUTION_MARGIN`.

Resimulate существующей карточки:

```bash
CANDIDATE_ID=$(jq -r '.best_candidates[0].candidate_id' decision.json)

curl -s -X POST "http://localhost:8000/api/candidates/${CANDIDATE_ID}/resimulate" \
  -H 'Content-Type: application/json' \
  -d '{"parameters":{"discount_pct":10},"budget":4500,"duration_days":10,"seed":42}'
```

Запуск подтверждённого mock-эксперимента и outcome:

```bash
curl -s -X POST http://localhost:8000/api/experiments \
  -H 'Content-Type: application/json' \
  -d "{\"candidate_id\":\"${CANDIDATE_ID}\",\"confirmed\":true}" \
  | tee experiment.json

EXPERIMENT_ID=$(jq -r '.experiment_id' experiment.json)

curl -s -X PATCH "http://localhost:8000/api/experiments/${EXPERIMENT_ID}/outcome" \
  -H 'Content-Type: application/json' \
  -d '{"actual_revenue_delta":4200,"actual_profit_delta":900,"actual_target_delta":0.09,"stopped_early":false,"notes":"Demo outcome"}'

curl -s -X POST http://localhost:8000/api/training/export-replay \
  -o alfa_liga_replay.jsonl
```

CLI-экспорт того же replay:

```bash
python scripts/export_replay.py --output artifacts/replay.jsonl
```

## API

| Метод | Endpoint | Назначение |
|---|---|---|
| GET | `/api/health` | Проверка API и БД |
| GET | `/api/model/info` | Честная карточка Base/LoRA/ReFT/Stage 2 |
| GET | `/api/products` | Каталог допустимых продуктов и mock-статусы |
| GET | `/api/businesses/{business_id}/state` | Строгий агрегированный `BusinessState` |
| POST | `/api/decisions` | GENERATE или EVALUATE pipeline |
| GET | `/api/decisions/{decision_id}` | Сохранённое решение |
| GET | `/api/decisions/{decision_id}/trace` | Публичный decision trace без chain-of-thought |
| POST | `/api/candidates/{candidate_id}/resimulate` | Новый deterministic расчёт без Idea Policy |
| POST | `/api/experiments` | Подтверждённый mock-запуск |
| PATCH | `/api/experiments/{experiment_id}/outcome` | Фактический outcome/остановка |
| GET | `/api/experiments/{experiment_id}` | Состояние эксперимента |
| POST | `/api/training/export-replay` | Обезличенный RL-ready JSONL |

Готовый payload для фронтендера: [`docs/frontend_mock.json`](docs/frontend_mock.json).

## Тесты

```bash
python -m compileall -q app tests scripts
python -m pytest -q
python -m pytest --cov=app --cov-report=term-missing
```

Набор проверяет health/OpenAPI, provenance `BusinessState`, 9%/19%, `NEED_DATA`, бюджет/резерв, одинаковый seed, resimulate без policy, каталог продуктов, fallback, отсутствие raw transactions, experiment outcome, replay и Alembic schema.

## Что реально работает, а что mock

Реально работает:

- синтетический 60-дневный fixture с пропусками;
- расчёт всех бизнес-метрик в Python/SQL;
- strict action space и parameter extraction;
- hard precheck/postcheck;
- validated world-model priors;
- 5 000 NumPy Monte Carlo-прогонов;
- p10/p50/p90, risk flags, ranking и bank effect;
- SQLite/PostgreSQL persistence, experiments и replay;
- optional локальный LoRA provider + deterministic fallback.

Mock/демонстрационные допущения:

- все коннекторы продуктов Альфа-Банка;
- fee rate и стоимость сопровождения;
- peer cohort и causal priors;
- фактический outcome, пока его не введёт пользователь.

Репозиторий не содержит обученных весов LoRA. `LocalQwenLoRAPolicy` активируется только через `POLICY_PROVIDER=local_lora` и существующий `LORA_ADAPTER_PATH`; иначе golden path остаётся рабочим через fallback. ReFT не является production baseline. Replay описывается как «RL-ready feedback loop», а не как уже обученная RL-policy.

## Документация

- [`docs/audit.md`](docs/audit.md) — исходное состояние, противоречия и решения.
- [`docs/architecture.md`](docs/architecture.md) — pipeline и доверенные границы.
- [`docs/frontend_mock.json`](docs/frontend_mock.json) — стабильный mock ответа для HTML/React.
