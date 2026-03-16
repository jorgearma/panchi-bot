# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

Panchi-Bot is a WhatsApp-based food ordering system for a restaurant in Tarancón, Spain. Customers interact via WhatsApp (Twilio), follow a tokenized link to select products from a web menu, and pay via Monei. The bot handles registration, order creation, and payment confirmation.

## Running the App

```bash
source venv/bin/activate
python main.py
```

The Flask dev server starts on port 5000. For WhatsApp webhooks to work, a tunnel (ngrok) is required — the public URL must be set in the environment.

## Running Tests

```bash
pytest                                                              # all tests
pytest tests/test_api_pedido.py                                    # single file
pytest tests/test_states.py::TestEstadoPedidoEnum::test_valores_string  # single test
```

`tests/conftest.py` provides shared `app` and `client` fixtures (Flask test client) for integration tests.

## Architecture

### Layer Rules

Imports must only flow downward. Violations are bugs.

```
blueprints  →  controllers, schemas, states
controllers →  managers, services, schemas, states, utils
managers    →  models, states, database
services    →  managers (rate_limit only), schemas, utils
models      →  database (Base only)
schemas     →  (pydantic only — no internal imports)
utils       →  (pure functions only — no internal imports)
states      →  (enums + pure functions — no internal imports)
```

### App Structure

`main.py` exposes `create_app(config: dict = None) -> Flask`. It calls `load_dotenv()` first, then builds the Flask app inside the factory. All singleton instances live in `services/__init__.py` — never instantiated elsewhere.

```
blueprints/webhook.py   POST /webhook (Twilio), POST /webhook/monei (Monei)
blueprints/menu.py      GET /menu/<token>, /confirmacion_pago, /pago_confirmado
blueprints/api.py       POST /api/confirmacion, /api/agregar_pedido, /api/productos, etc.
```

### Singleton Initialization

All three external-client singletons are **lazy** — they initialize on first call, not at import time. This makes the test suite importable without live credentials.

| Singleton | Location | Accessor |
|---|---|---|
| Twilio `Client` | `services/twilio_service.py` | `_get_client()` (module-private) |
| spaCy `es_core_news_sm` | `controllers/registro.py` | `_get_nlp()` (module-private) |
| `Monei.MoneiClient` | `services/__init__.py` | `get_monei()` (exported) |

DB managers and Redis are still eagerly initialized in `services/__init__.py` because they have no credentials risk in tests.

### Message Flow

1. WhatsApp message → `POST /webhook`
2. `schemas/twilio.py::WebhookRequest` validates `From` + `Body`
3. Redis rate-limit check (20-second TTL per user — unlock is automatic via TTL, no explicit call)
4. **Unregistered users** → `controllers/registro.py` — multi-step registration state machine
5. **Registered users** → `controllers/mensajes_registrados.py::ManejadorMensajesRegistrados`

### Registration State Machine (Redis)

States stored in Redis during registration:
`saludo_inicial` → `esperando_confirmacion` → `esperando_nombre` → `esperando_direccion` → `confirmando_direccion` → registered in DB

Name validation uses spaCy (`es_core_news_sm`, loaded lazily). Address validation uses `calles_tarancon.json`.

### Order Flow

1. User sends "1" → `controllers/pedido.py::procesar_pedido` → token generated, pending order created in DB, link sent
2. Token payload validated by `schemas/usuario.py::UsuarioDatos` (includes `token` field) on retrieval
3. User selects products → `POST /api/confirmacion` → `controllers/pedido.py::confirmar_carrito` stores cart in Redis, transitions to `enlace2`
4. `POST /api/agregar_pedido` → `controllers/pago.py::iniciar_pago` re-validates prices against DB, creates Monei payment, transitions to `confirmando-pago`
5. Monei calls `POST /webhook/monei` → HMAC signature verified → order set to `pagado`, WhatsApp confirmation sent

Order states: `Pendiente` → `enlace` → `enlace2` → `confirmando-pago` → `pagado`

### Key Modules

| Path | Role |
|------|------|
| `main.py` | `create_app()` factory — Flask setup, Sentry, blueprints, logging config |
| `services/__init__.py` | Singletons: `gestor_pedidos`, `gestor_usuarios`, `gestor_productos`, `cache`, `get_monei()` |
| `states.py` | `EstadoPedido` + `EstadoRegistro` str-enums, transition maps, `transicion_valida_*` pure functions |
| `config.py` | All env var constants — reads `os.environ` (populated by `main.py` before any import) |
| `database.py` | SQLAlchemy engine + session factory |
| `models.py` | ORM models: `Usuario`, `Producto`, `Pedido`, `PedidoDetalle`, `Empleado` |
| `schemas/twilio.py` | Pydantic V2 validators for Twilio webhook data (`WebhookRequest`, `PedidoInput`) |
| `schemas/usuario.py` | `UsuarioDatos` — Pydantic model for user data in Redis tokens (includes `token` field) |
| `managers/gestor_redis.py` | `RedisManager` infrastructure adapter + `redismanager` singleton |
| `managers/estado_usuario.py` | `EstadoUsuario` — registration state read/write, enforces `transicion_valida_registro` |
| `managers/gestor_usuarios.py` | `GestorUsuarios` — User DB queries |
| `managers/gestor_productos.py` | `ProductoManager` — Product DB queries |
| `managers/gestor_pedidos.py` | `GestorPedidos` — order creation, state transitions, detail insertion |
| `controllers/registro.py` | Multi-step registration flow for unregistered users |
| `controllers/mensajes_registrados.py` | `ManejadorMensajesRegistrados` — dispatches registered user messages |
| `controllers/pedido.py` | `procesar_pedido`, `confirmar_carrito` — order initiation and cart confirmation |
| `controllers/pago.py` | `iniciar_pago` — DB price re-validation, Monei payment creation |
| `services/twilio_service.py` | `enviar_mensaje_whatsapp` — Twilio send functions (lazy client) |
| `services/token_service.py` | Token generation + Redis storage |
| `services/maps_service.py` | Google Maps address validation |
| `utils/menu_opciones.py` | `menu` dict, `mostrar_menu()` — pure, no I/O |
| `utils/text_utils.py` | `limpiar_texto()` — unicode normalization + punctuation removal for text comparison |
| `utils/es_pregunta.py` | `es_pregunta()` — heuristic to detect if a user message is a question (Spanish) |

### State Machine Conventions

All valid transitions are declared in `states.py` — never hardcode them elsewhere. `GestorPedidos.actualizar_estado` and `EstadoUsuario.actualizar_estado` call the pure validators and block invalid moves with `logger.error`. Both enums inherit from `str` so they serialize to JSON and compare equal to raw strings from Redis/DB without conversion.

### Security — Monei Webhook

`blueprints/webhook.py::webhook_monei` verifies the `MONEI-SIGNATURE` header with `hmac.compare_digest` before processing any payload. Returns 401 if the signature is missing or invalid. `MONEI_WEBHOOK_SECRET` must be set in the environment.

### Known Technical Debt

See `REFACTOR_PLAN.md` for the full phase-by-phase refactor plan (security fixes → data bugs → tech debt → test coverage). The active branch is `refactorizar-estructura`.

Key items not to overlook:
- Legacy route `/webhoo/monei` (typo) in `blueprints/webhook.py` — remove once Monei dashboard points to `/webhook/monei`.
- `cocina/` directory is intentionally empty (placeholder for future kitchen-display features).
- `scripts/generar_calles.py` regenerates `calles_tarancon.json` from source data — run manually when the street list needs updating.

### External Services

- **SQL Server** — persistent storage (pyodbc driver, connection string in `database.py`)
- **Redis** — ephemeral user state, tokens, cart data, rate limiting
- **Twilio** — WhatsApp send/receive
- **Monei** — payment processing
- **Sentry** — error monitoring (skipped when `app.config["TESTING"]` is True)
- **Google Maps API** — address validation

## Environment Variables

The app reads from `.env` (loaded once by `main.py`). All constants also available via `config.py`:

```
SECRET_KEY
TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_NUMBER
MONEI_API_KEY, MONEI_WEBHOOK_SECRET
GOOGLE_MAPS_API_KEY
PUBLIC_URL          # ngrok or production URL used for menu/payment links
SQL_SERVER, SQL_DATABASE, SQL_UID, SQL_PWD
REDIS_HOST, REDIS_PORT, REDIS_DB
OPENAI_API_KEY      # not yet actively used
```
