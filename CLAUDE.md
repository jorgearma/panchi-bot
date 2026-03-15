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
pytest                                        # all tests
pytest tests/test_api_pedido.py               # single file
pytest tests/test_states.py::TestEstadoPedidoEnum::test_valores_string  # single test
```

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

`main.py` calls `load_dotenv()` first, then creates the Flask app and registers three blueprints. All singleton instances live in `services.py` — never instantiated elsewhere.

```
blueprints/webhook.py   POST /webhook (Twilio), POST /webhook/monei (Monei)
blueprints/menu.py      GET /menu/<token>, /confirmacion_pago, /pago_confirmado
blueprints/api.py       POST /api/confirmacion, /api/agregar_pedido, /api/productos, etc.
```

### Message Flow

1. WhatsApp message → `POST /webhook`
2. `schemas/twilio.py::WebhookRequest` validates `From` + `Body`
3. Redis rate-limit check (20-second TTL cooldown per user)
4. **Unregistered users** → `controllers/registro.py` — multi-step registration state machine
5. **Registered users** → `controllers/mensajes_registrados.py::ManejadorMensajesRegistrados`

### Registration State Machine (Redis)

States stored in Redis during registration:
`saludo_inicial` → `esperando_confirmacion` → `esperando_nombre` → `esperando_direccion` → `confirmando_direccion` → registered in DB

Name validation uses spaCy (`es_core_news_sm`). Address validation uses `calles_tarancon.json`.

### Order Flow

1. User sends "1" → `controllers/pedido.py::procesar_pedido` → token generated, pending order created in DB, link sent
2. Token payload (user id, name, address, phone) stored in Redis; validated by `schemas/usuario.py::UsuarioDatos` on retrieval
3. User selects products on `quiniela.html` → `POST /api/confirmacion` → `controllers/pedido.py::confirmar_carrito` stores cart in Redis, transitions order to `enlace2`
4. `POST /api/agregar_pedido` → `controllers/pago.py::iniciar_pago` re-validates prices against DB, creates Monei payment, transitions to `confirmando-pago`
5. Monei calls `POST /webhook/monei` → order set to `pagado`, WhatsApp confirmation sent
   - Legacy route `/webhoo/monei` (typo) still active — remove once Monei panel is updated

Order states: `Pendiente` → `enlace` → `enlace2` → `confirmando-pago` → `pagado`

### Key Modules

| Path | Role |
|------|------|
| `main.py` | Flask app creation, blueprint registration, Sentry init. Calls `load_dotenv()` first. |
| `services.py` | Singleton instances: `gestor_pedidos`, `gestor_usuarios`, `gestor_productos`, `monei`, `cache` |
| `states.py` | `EstadoPedido` + `EstadoRegistro` str-enums, transition maps, `transicion_valida_*` pure functions |
| `config.py` | All env var constants — reads `os.environ` (populated by `main.py` before any import) |
| `database.py` | SQLAlchemy engine + session factory |
| `models.py` | ORM models: `Usuario`, `Producto`, `Pedido`, `PedidoDetalle`, `Empleado` |
| `schemas/twilio.py` | Pydantic validators for Twilio webhook data (`WebhookRequest`, `PedidoInput`) |
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
| `services/twilio_service.py` | `enviar_mensaje_whatsapp` — Twilio send functions |
| `services/token_service.py` | Token generation + Redis storage |
| `services/maps_service.py` | Google Maps address validation |
| `utils/menu_opciones.py` | `menu` dict, `mostrar_menu()`, `limpiar_texto()` — pure, no I/O |
| `cocina/comandas.py` | Kitchen-side comanda logic (stub) |

### State Machine Conventions

All valid transitions are declared in `states.py` — never hardcode them elsewhere. `GestorPedidos.actualizar_estado` and `EstadoUsuario.actualizar_estado` call the pure validators and block invalid moves with `log.error`. Both enums inherit from `str` so they serialize to JSON and compare equal to raw strings from Redis/DB without conversion.

### Known Technical Debt

- `utils/confirmar_direccion.py` imports from `services/` — violates the utils purity rule. Should be promoted to `controllers/`.
- Legacy route `/webhoo/monei` (typo) in `blueprints/webhook.py` — remove once Monei panel is updated.

### External Services

- **SQL Server** — persistent storage (pyodbc driver, connection string in `database.py`)
- **Redis** — ephemeral user state, tokens, cart data, rate limiting
- **Twilio** — WhatsApp send/receive
- **Monei** — payment processing
- **Sentry** — error monitoring (DSN in `main.py`)
- **Google Maps API** — address validation

## Environment Variables

The app reads from `.env` (loaded once by `main.py`). All constants are also available via `config.py`:

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
