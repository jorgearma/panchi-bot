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
pytest                          # all tests
pytest tests/test_pedido.py     # single test file
pytest tests/test_pedido.py::test_name  # single test
```

## Architecture

### App Structure

`main.py` creates the Flask app and registers three blueprints. All singleton service instances (DB managers, Monei client, Redis client) live in `services.py` and are imported from there — never instantiated elsewhere.

```
blueprints/webhook.py   POST /webhook (Twilio), POST /webhook/monei (Monei)
blueprints/menu.py      GET /menu/<token>, /confirmacion_pago, /pago_confirmado
blueprints/api.py       POST /api/confirmacion, /api/agregar_pedido, /api/productos, etc.
```

### Message Flow

1. WhatsApp message arrives at `POST /webhook`
2. Pydantic model `modelos/validator_twilio.py::WebhookRequest` validates `From` + `Body`
3. Redis rate-limit check (20-second cooldown per user)
4. **Unregistered users** → `controllers/no_resgistrados.py` — multi-step registration state machine
5. **Registered users** → `controllers/mensajes_registrados.py` → `ManejadorMensajesRegistrados`

### Registration State Machine (Redis)

States stored in Redis (not DB) during registration:
`saludo_inicial` → `esperando_confirmacion` → `esperando_nombre` → `esperando_direccion` → `confirmando_direccion` → registered in DB

Name validation uses spaCy (`es_core_news_sm`). Address validation uses `calles_tarancon.json`.

### Order Flow

1. User sends "1" (Tienda) → token generated, pending order created in DB, link `/menu/<token>` sent
2. Token payload (user id, name, address, phone) stored in Redis; validated by `modelos/validator_usuario.py::UsuarioDatos` on retrieval
3. User selects products on `quiniela.html` → `POST /api/confirmacion` stores cart in Redis, transitions order to `enlace2`
4. `POST /api/agregar_pedido` re-validates prices against DB, creates Monei payment, transitions to `confirmando-pago`
5. Monei calls `POST /webhook/monei` → order set to `pagado`, WhatsApp confirmation sent
   - Legacy route `/webhoo/monei` (typo) still active — remove once Monei panel is updated

Order states: `Pendiente` → `enlace` → `enlace2` → `confirmando-pago` → `pagado`

### Key Modules

| Path | Role |
|------|------|
| `main.py` | Flask app creation, blueprint registration, Sentry init |
| `services.py` | Singleton instances: `gestor_pedidos`, `gestor_usuarios`, `gestor_productos`, `monei`, `cache` |
| `database.py` | SQLAlchemy engine + session factory, table creation |
| `models.py` | ORM models: `Usuario`, `Producto`, `Pedido`, `PedidoDetalle`, `Empleado`, `Usuario_web` |
| `modelos/validator_twilio.py` | Pydantic validators for incoming Twilio webhook data |
| `modelos/validator_usuario.py` | Pydantic validator for user data stored in Redis tokens |
| `managers/gestor_redis.py` | All Redis state reads/writes (singleton `redismanager`) |
| `managers/gestor_usuarios.py` | User DB queries |
| `managers/gestor_productos.py` | Product DB queries |
| `data/order.py` | `GestorPedidos` — order creation, state transitions, detail insertion |
| `utils/mensajes.py` | Twilio send functions |
| `utils/crear_token.py` | Token generation + Redis storage |
| `utils/maps.py` | Google Maps address validation |
| `cocina/comandas.py` | Kitchen-side comanda logic |

### External Services

- **SQL Server** — persistent storage (pyodbc driver, connection string in `database.py`)
- **Redis** — ephemeral user state, tokens, cart data, rate limiting
- **Twilio** — WhatsApp send/receive
- **Monei** — payment processing
- **Sentry** — error monitoring (DSN hardcoded in `main.py`)
- **Google Maps API** — address validation

## Environment Variables

The app reads from `.env`. Key variables:

```
SECRET_KEY
TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_NUMBER
MONEI_API_KEY, MONEI_WEBHOOK_SECRET
GOOGLE_MAPS_API_KEY
PUBLIC_URL          # ngrok or production URL used for menu/payment links
SQL_SERVER, SQL_DATABASE, SQL_UID, SQL_PWD
REDIS_HOST, REDIS_PORT, REDIS_DB
OPENAI_API_KEY      # loaded via config.py, not yet actively used
```
