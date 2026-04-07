# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run all tests
pytest

# Run a single test file
pytest tests/test_webhook.py

# Run with verbose output
pytest -v --tb=short

# Run the app locally
python main.py  # starts on 0.0.0.0:5000

# Run the RQ worker (required for background WhatsApp message processing)
python worker.py

# Docker (full stack: app + Redis + SQL Server + worker + Nginx)
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
                   gestor_dashboard and gestor_empleado are thin assemblers — logic lives in domain mixins
                   under managers/dashboard/ (10 mixins) and managers/empleado/ (4 mixins) respectively
services/       → External API adapters (WhatsApp, Maps, tokens) — no business logic
schemas/        → Pydantic input validation
utils/          → Stateless helpers
maps_module/    → Address validation package (polygon, street catalog, geocoding) — designed as extractable microservice
models.py       → SQLAlchemy ORM (~21 tables)
states.py       → Order/registration state enums and transition rules
config.py       → All environment variable loading
container.py    → Dependency injection: exports manager singletons
database.py     → SQLAlchemy session management (SQL Server via pyodbc)
message_queue.py → RQ queue setup for background WhatsApp processing
worker.py       → RQ worker entry point
main.py         → Flask app factory, 15 blueprint registrations
```

### Registered Blueprints

| Blueprint            | Main routes                                         | Purpose                                         |
|----------------------|-----------------------------------------------------|-------------------------------------------------|
| `auth`               | `/auth/login`, `/auth/logout`                       | Staff authentication                            |
| `webhook`            | `/webhook`, `/webhook/monei`, `/webhook/meta`       | WhatsApp messages and payments                  |
| `menu`               | `/menu/<token>`, `/confirmacion_pago`               | Customer web menu                               |
| `api`                | `/api/confirmacion`, `/api/agregar_pedido`          | Cart and payment API (package: cart, payments, tracking) |
| `dashboard`          | `/dashboard/*`                                      | Operations panel (package: pages, pedidos, picking, reparto, turnos) |
| `picker`             | `/picker/*`                                         | Preparation queue (warehouse mode)              |
| `cocina`             | `/cocina/*`                                         | Kitchen PWA (restaurant mode)                   |
| `repartidor`         | `/repartidor/*`                                     | Delivery queue and tracking                     |
| `empleado`           | `/empleado/*`                                       | Employee check-in and metrics                   |
| `productos`          | `/productos-admin/*`                                | Stock and price management                      |
| `metricas_operacion` | `/metricas/operacion/*`                             | Real-time metrics                               |
| `metricas_analitica` | `/metricas/analitica/*`                             | Historical analytics                            |
| `demo`               | `/demo`, `/demo/autologin`, `/demo/exit`, `/demo/reset` | Demo mode with Redis-backed session state   |
| `landing`            | `/`, `/about`, `/por-que-funciona`                  | Public landing pages                            |
| `maps`               | `/api/v1/maps/*`                                    | Address validation REST API                     |
| *(global)*           | `/health`                                           | Health check: Redis + DB                        |

### APP_MODE: Warehouse vs Restaurant

`APP_MODE` env var (`"warehouse"` default or `"restaurant"`) switches operational mode at startup:

- **Warehouse**: uses `/picker/*` with item-level picking records in the `picking` table.
- **Restaurant**: uses `/cocina/*` PWA with simplified queue via `managers/dashboard/picking_basico.py` (no item-level detail).

`blueprints/dashboard/pages.py` selects templates based on `APP_MODE`. A context processor injects `app_mode` into all templates. Invalid values cause startup failure.

### Two Independent Flows

- **Bot flow**: WhatsApp → `/webhook` → `message_queue.py` (RQ) → `worker.py` → controllers → managers → WhatsApp response
- **Dashboard flow**: Browser → `/dashboard*`, `/picker*`, `/repartidor*` → managers → render HTML

Both share managers and DB but have separate routing and authentication.

### Key Flows

**New user registration** (Redis state machine in `controllers/registro.py`):
`SALUDO_INICIAL → ESPERANDO_CONFIRMACION → ESPERANDO_NOMBRE → ESPERANDO_DIRECCION → CONFIRMANDO_DIRECCION → save to DB`

Rollback is possible: if the user corrects their address, the state returns to `ESPERANDO_DIRECCION`.

**WhatsApp → Order (online payment):**
1. `POST /webhook` → enqueue in RQ → `worker.py` → user in DB → `controllers/mensajes_registrados.py`
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

| Use                 | Key pattern              | Responsible                   |
|---------------------|--------------------------|-------------------------------|
| Registration state  | `<phone>`                | `gestor_redis`                |
| Anti-spam lock      | `bloqueo:<phone>`        | `gestor_redis`                |
| Menu token          | `<uuid-token>`           | `token_service`               |
| Cart (session)      | `pedido:<uuid>`          | `controllers/pago`            |
| Demo session        | `demo:<session_id>`      | `services/demo_state.py`      |

### State Machines

`states.py` defines valid state transitions. When changing order states, always go through `gestor_pedidos.py` which enforces transitions and logs history to `historial_estados_pedido`.

### maps_module

Standalone address validation package (`maps_module/`). Public API:
```python
validar_direccion(address, territory) → (bool, str|None, str|None)
geocodificar_direccion(address, territory) → tuple[float, float] | None
validar_coordenadas(coords, territory) → bool
```

Rejection reasons: `"no_encontrada"`, `"fuera_de_zona"`, `"demasiado_generica"`, `"sin_numero"`, `"error_api"`. Territory config is in `maps_module/territories.json`; street catalog (311 streets) in `maps_module/calles_tarancon.json`. Designed to be extracted as an independent microservice without contract changes.

### Dependency Injection

`container.py` exports manager singletons: `gestor_pedidos`, `gestor_usuarios`, `gestor_productos`, `gestor_dashboard`, `gestor_empleado`, `gestor_metricas`, `redismanager`, `cache`, and `get_monei()`. Import from here rather than instantiating managers directly.

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
| `APP_MODE`               | Always (`warehouse`/`restaurant`) |
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
- **RQ worker** must be running alongside the app for WhatsApp message processing. In Docker, the `worker` service handles this.

## Known Issues (don't introduce more of these)

- `/webhoo/monei` (typo route) exists alongside `/webhook/monei` pending Monei dashboard update — don't replicate this pattern.
- `blueprints/api/` submodules contain business logic that belongs in controllers — don't add more.
