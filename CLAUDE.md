cpcp# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run all tests (~3 seconds, 110 tests)
pytest

# Run a single test file
pytest tests/test_webhook.py

# Run with verbose output
pytest -v --tb=short

# Run the app locally
python main.py  # starts on 0.0.0.0:5000

# Docker (full stack: app + Redis + Nginx)
docker-compose up
docker-compose up --build  # rebuild app image

# ngrok for local webhooks
ngrok http 5000
# Copy the public URL to PUBLIC_URL in .env

# spaCy model (required for registration NLP)
python -m spacy download es_core_news_sm
```

## Architecture

**Panchi-Bot** is a WhatsApp restaurant ordering bot for a business in Tarancón, Spain. Customers message via WhatsApp, browse a web menu, and pay via Monei. Operators manage orders through a dashboard with role-based access.

### Layer Structure (strict top-down dependencies)

```
blueprints/     → HTTP routing only — no business logic
controllers/    → Business logic & state machines
managers/       → DB and Redis data access (estado_usuario.py = registration state machine over Redis)
services/       → External API adapters (WhatsApp, Maps, tokens) — no business logic
schemas/        → Pydantic input validation
utils/          → Stateless helpers
models.py       → SQLAlchemy ORM (21 tables)
states.py       → Order/registration state enums and transition rules
config.py       → All environment variable loading
database.py     → SQLAlchemy session management (SQL Server via pyodbc)
main.py         → Flask app factory, 11 blueprint registrations
```

### Registered Blueprints

| Blueprint            | Main routes                                  | Purpose                          |
|----------------------|----------------------------------------------|----------------------------------|
| `auth`               | `/auth/login`, `/auth/logout`                | Staff authentication             |
| `webhook`            | `/webhook`, `/webhook/monei`, `/webhook/meta`| WhatsApp messages and payments   |
| `menu`               | `/menu/<token>`, `/confirmacion_pago`        | Customer web menu                |
| `api`                | `/api/confirmacion`, `/api/agregar_pedido`   | Cart and payment API             |
| `dashboard`          | `/dashboard/*`                               | Operations panel (admin)         |
| `picker`             | `/picker/*`                                  | Preparation queue (warehouse)    |
| `repartidor`         | `/repartidor/*`                              | Delivery queue and tracking      |
| `empleado`           | `/empleado/*`                                | Employee check-in and metrics    |
| `productos`          | `/productos-admin/*`                         | Stock and price management       |
| `metricas_operacion` | `/metricas/operacion/*`                      | Real-time metrics                |
| `metricas_analitica` | `/metricas/analitica/*`                      | Historical analytics             |
| *(global)*           | `/health`                                    | Health check: Redis + DB         |

### Two Independent Flows

- **Bot flow**: WhatsApp → `/webhook` → controllers → managers → WhatsApp response
- **Dashboard flow**: Browser → `/dashboard*`, `/picker*`, `/repartidor*` → managers → render HTML

Both share managers and DB but have separate routing and authentication.

### Key Flows

**New user registration** (Redis state machine in `controllers/registro.py`):
`SALUDO_INICIAL → ESPERANDO_CONFIRMACION → ESPERANDO_NOMBRE → ESPERANDO_DIRECCION → CONFIRMANDO_DIRECCION → save to DB`

Rollback is possible: if the user corrects their address, the state returns to `ESPERANDO_DIRECCION`.

**WhatsApp → Order (online payment):**
1. `POST /webhook` → user in DB → `controllers/mensajes_registrados.py`
2. State `PENDIENTE` → generate token (Redis TTL) → send menu link
3. `GET /menu/<token>` → render menu → customer adds items in JS
4. `POST /api/confirmacion` → save cart in Redis → state `ENLACE2`
5. `POST /api/agregar_pedido` → validate prices against DB → create `pedidos` + `pedido_detalles` → create Monei payment → state `CONFIRMANDO_PAGO`
6. `POST /webhook/monei` → verify HMAC → state `PAGADO` → notify customer

**Cash payment:** `POST /api/agregar_pedido_efectivo` → state `CONTRA_REEMBOLSO` (skips Monei)

**Operational flow:** `PAGADO/CONTRA_REEMBOLSO → EN_PREPARACION → PREPARADO → EN_REPARTO → ENTREGADO`

### Order State Diagram

```
PENDIENTE → ENLACE ⇄ ENLACE2 → CONFIRMANDO_PAGO → PAGADO → EN_PREPARACION → PREPARADO → EN_REPARTO → ENTREGADO
                              ↘ CONTRA_REEMBOLSO ↗                    ↘ CANCELADO → REEMBOLSADO
```

### Redis Usage

| Use                 | Key pattern          | Responsible manager |
|---------------------|----------------------|---------------------|
| Registration state  | `<phone>`            | `gestor_redis`      |
| Anti-spam lock      | `bloqueo:<phone>`    | `gestor_redis`      |
| Menu token          | `<uuid-token>`       | `token_service`     |
| Cart (session)      | `pedido:<uuid>`      | `controllers/pago`  |

### State Machines

`states.py` defines valid state transitions. When changing order states, always go through `gestor_pedidos.py` which enforces transitions and logs history to `historial_estados_pedido`.

### Retry Logic

Critical DB and external API calls use `tenacity` decorators. Don't remove these — they protect against transient SQL Server connection drops.

### WhatsApp Provider

Switchable via `WHATSAPP_PROVIDER` env var (`"twilio"` or `"meta"`). The abstraction lives in `services/whatsapp_service.py` — all message sending goes through it.

### NLP

`spaCy` (`es_core_news_sm`) is used for Spanish name validation during registration. The model must be installed separately — it is not a pip package.

### Testing

Tests use `FakeRedis` (no live Redis needed) and mock external services. Database calls are mocked — tests do not require a live SQL Server. Fixtures are in `tests/conftest.py`.

## Environment

Copy `.env.example` to `.env`. Key variables:

| Variable                 | Required               |
|--------------------------|------------------------|
| `SECRET_KEY`             | Always                 |
| `WHATSAPP_PROVIDER`      | Always (`twilio`/`meta`) |
| `SQL_SERVER`, `SQL_DATABASE`, `SQL_UID`, `SQL_PWD` | Always |
| `REDIS_HOST`             | Always                 |
| `PUBLIC_URL`             | Always (ngrok in dev)  |
| `MONEI_API_KEY`, `MONEI_WEBHOOK_SECRET` | Always  |
| `GOOGLE_MAPS_API_KEY`    | Always                 |
| `INTERNAL_API_TOKEN`     | Always                 |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_NUMBER` | If `PROVIDER=twilio` |
| `META_ACCESS_TOKEN`, `META_PHONE_NUMBER_ID`, `META_APP_SECRET`, `META_VERIFY_TOKEN` | If `PROVIDER=meta` |
| `ALLOWED_ORIGIN`         | Recommended (CORS for `/api/*`) |
| `SENTRY_DSN`             | Recommended            |
| `CUSTOMER_SUPPORT_PHONE` | Recommended            |

## Critical Notes

- **ODBC Driver 18 for SQL Server** must be installed at the OS level — it is not a pip package. Without it, the app won't start. In Docker, the base image must include it.
- **`pyodbc`** is the SQL Server driver. If the connection drops, `tenacity` retries will handle transient failures — don't remove those decorators.
- **Price validation** in `POST /api/agregar_pedido` compares cart prices against the DB to prevent client-side manipulation — don't bypass this.
- **Monei HMAC** must be verified in `POST /webhook/monei` before processing any payment state change.

## Known Issues (don't introduce more of these)

- `gestor_dashboard.py` is a 121 KB god object — don't add more logic to it, extract to submodules instead.
- WhatsApp notifications in `blueprints/picker.py`, `repartidor.py`, `dashboard.py` use bare `threading.Thread` with no error handling — failures are silent.
- `/webhoo/monei` (typo route) exists alongside `/webhook/monei` pending Monei dashboard update — don't replicate this pattern.
- `blueprints/api.py` contains business logic that belongs in controllers — don't add more.






### Agentes y sus roles

| Agente | Entrada | Salida |
|--------|---------|--------|
| `reader` (entry point) | Peticion del usuario | `reader-context.json` |
| `planner` | reader-context.json | `plan.json` |
| `writer` | plan.json | `execution-brief.json` + `execution-brief.md` |
| `frontend` / `backend` | execution-dispatch.json | `result.json` |
| `reviewer` | result.json + plan.json | `review.json` |

### Readers especializados

El `reader` principal activa solo los readers necesarios segun el dominio de la peticion:

- `project-reader` → arquitectura, modulos, flujo general (`PROJECT_MAP.md`)
- `db-reader` → tablas, modelos, migraciones (`DB_MAP.md`)
- `query-reader` → queries, acceso a datos, performance (`QUERY_MAP.md`)
- `ui-reader` → vistas, componentes, estados UI (`UI_MAP.md`)

Cada reader lee su `*_MAP.md` y devuelve un JSON con `files_to_open` y `files_to_review`. Para requests que cruzan dominios, el reader elige un `primary_reader` de todas formas.

### Gate de aprobacion

Ningun agente ejecutor (frontend/backend) puede actuar sin `operator-approval.json` con `status: "approved"`. El script `execute-plan.py` valida esto antes de generar `execution-dispatch.json`. Los agentes ejecutores verifican `selected_agents` en el dispatch para saber si deben actuar.

### Contratos JSON

Todos los artefactos del flujo tienen schema en `.claude/schemas/`. Los archivos de runtime en `.claude/runtime/` son generados y sobreescritos en cada ciclo — no editar manualmente salvo `operator-approval.json` via hooks.

## Instalacion en un proyecto nuevo

1. Copia esta carpeta al proyecto que usara Claude.
2. Verifica que exista `.claude/plugin.json`.
3. Rellena los `*_MAP.md` en `.claude/maps/` con el contexto real del proyecto.
4. Ejecuta `python3 .claude/hooks/pre-commit.py` para validar la estructura.
                                                                                   
┌──(venv)─(siemprearmando㉿elfavo)-[~/panchi-bot] ➟ prueba-agentes
└─$ 

### Contratos JSON

Todos los artefactos del flujo tienen schema en `.claude/schemas/`. Los archivos de runtime en `.claude/runtime/` son generados y sobreescritos en cada ciclo — no editar manualmente salvo `operator-approval.json` via hooks.tar manualmente salvo `operator-approval.json` via hooks.

## Instalacion en un proyecto nuevo

1. Copia esta carpeta al proyecto que usara Claude.
2. Verifica que exista `.claude/plugin.json`.
3. Rellena los `*_MAP.md` en `.claude/maps/` con el contexto real del proyecto.
4. Ejecuta `python3 .claude/hooks/pre-commit.py` para validar la estructura.