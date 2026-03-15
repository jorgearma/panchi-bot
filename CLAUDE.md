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

### Message Flow

1. WhatsApp message arrives at `POST /webhook` via Twilio
2. `main.py` checks if user is registered in SQL Server
3. **Unregistered users** → `controllers/no_resgistrados.py` — multi-step registration state machine
4. **Registered users** → `controllers/mensajes_registrados.py` → `ManejadorMensajesRegistrados`

### Registration State Machine (Redis)

States stored in Redis (not DB) during registration:
`saludo_inicial` → `esperando_confirmacion` → `esperando_nombre` → `esperando_direccion` → `confirmando_direccion` → registered in DB

Name validation uses spaCy (`es_core_news_sm`). Address validation uses `calles_tarancon.json`.

### Order Flow

1. User sends "1" (Tienda) → system generates a token, creates a pending order in DB, sends link `/menu/<token>`
2. User selects products on `quiniela.html` → `POST /api/confirmacion` stores cart in Redis
3. `POST /api/agregar_pedido` validates prices against DB, creates Monei payment, redirects to payment URL
4. Monei calls `POST /webhook/monei` → order finalized, WhatsApp confirmation sent
   - Legacy route `/webhoo/monei` (typo) still active for backward compat — remove once Monei panel is updated

Order states: `Pendiente` → `enlace` → `enlace2` → `confirmando-pago` → `pagado`

### Key Modules

| Path | Role |
|------|------|
| `main.py` | Flask app, all route definitions |
| `database.py` | SQLAlchemy engine + session factory, table creation |
| `models.py` | ORM models: `Usuario`, `Producto`, `Pedido`, `PedidoDetalle`, `Empleado` |
| `managers/gestor_redis.py` | All Redis state reads/writes |
| `managers/gestor_usuarios.py` | User DB queries |
| `managers/gestor_productos.py` | Product DB queries |
| `utils/mensajes.py` | Twilio send functions |
| `utils/crear_token.py` | Token generation + Redis storage |
| `data/order.py` | `GestorPedidos` — order creation and detail insertion |
| `menu.py` | Menu/cart processing logic |

### External Services

- **SQL Server** — persistent storage (pyodbc driver, connection string in `database.py`)
- **Redis** — ephemeral user state, tokens, rate limiting (20-second cooldown per user)
- **Twilio** — WhatsApp send/receive
- **Monei** — payment processing
- **Google Maps API** — address validation (`utils/maps.py`)

## Environment Variables

The app reads from `.env`. Key variables:

```
TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_NUMBER
MONEI_API_KEY, MONEI_WEBHOOK_SECRET
GOOGLE_MAPS_API_KEY
PUBLIC_URL          # ngrok or production URL used for menu/payment links
SQL_SERVER, SQL_DATABASE, SQL_UID, SQL_PWD
REDIS_HOST, REDIS_PORT, REDIS_DB
```
