# Panchi-Bot

Bot de WhatsApp para gestión de pedidos de un restaurante en Tarancón (España). Los clientes interactúan por WhatsApp, seleccionan productos desde un menú web y pagan con Monei.

## Stack

| Capa | Tecnología |
|------|-----------|
| Mensajería | Twilio (WhatsApp) |
| Web | Flask + Jinja2 |
| Pagos | Monei |
| BD | SQL Server (pyodbc + SQLAlchemy) |
| Estado efímero | Redis |
| Validación de direcciones | Google Maps API + Shapely |
| Monitorización | Sentry |

## Requisitos previos

- Python 3.12+
- SQL Server accesible
- Redis en local o remoto
- Cuenta de Twilio con número WhatsApp habilitado
- Cuenta de Monei
- ngrok (o similar) para exponer el servidor en desarrollo

## Instalación

```bash
git clone <repo>
cd panchi-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m spacy download es_core_news_sm
cp .env.example .env  # editar con los valores reales
```

## Variables de entorno

Copia `.env.example` a `.env` y rellena todos los campos:

```env
# Flask
SECRET_KEY=

# SQL Server
SQL_SERVER=localhost,1433
SQL_DATABASE=
SQL_UID=
SQL_PWD=

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# Twilio
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886

# Monei
MONEI_API_KEY=
MONEI_WEBHOOK_SECRET=

# Google Maps
GOOGLE_MAPS_API_KEY=

# URL pública del servidor (ngrok en desarrollo)
PUBLIC_URL=https://xxxx.ngrok.io

# Sentry (opcional)
SENTRY_DSN=

# CORS: dominio del frontend en producción (vacío = permite *)
# ALLOWED_ORIGIN=https://tudominio.com

# Token para el endpoint interno de cambio de estado
# Generar con: python3 -c "import secrets; print(secrets.token_hex(32))"
INTERNAL_API_TOKEN=
```

## Arrancar en desarrollo

```bash
source venv/bin/activate
python main.py
```

El servidor arranca en `http://0.0.0.0:5000`. Los webhooks de Twilio y Monei necesitan una URL pública — usa ngrok:

```bash
ngrok http 5000
# Copia la URL HTTPS a PUBLIC_URL en .env
```

Configura la URL del webhook en el panel de Twilio: `POST https://<ngrok>/webhook`

## Tests

```bash
pytest                                      # todos
pytest tests/test_webhook.py               # un fichero
pytest -v --tb=short                       # verbose
```

Los tests requieren Redis en local. La suite completa corre en ~3 segundos con 110 tests.

## Flujo de un pedido

```
Cliente WhatsApp
    │
    ▼
POST /webhook  ──► verificación firma Twilio
    │
    ├── usuario no registrado ──► máquina de estados en Redis
    │                             (saludo → nombre → dirección → confirmación)
    │
    └── usuario registrado ──► estado del pedido activo
            │
            ├── PENDIENTE ──► procesar_pedido → genera token → POST BD → enlace enviado
            │
            ├── ENLACE / ENLACE2 ──► reenvía enlace existente
            │
            └── CONFIRMANDO_PAGO / PAGADO ──► mensaje de estado

GET /menu/<token>  ──► valida token Redis → renderiza menú web

POST /api/confirmacion  ──► confirmar_carrito → guarda carrito en Redis → ENLACE2

POST /api/agregar_pedido  ──► iniciar_pago → valida precios en BD → crea pago Monei
                                           → CONFIRMANDO_PAGO → devuelve URL de pago

POST /webhook/monei  ──► verifica HMAC → actualiza pedido a PAGADO → notifica cliente
```

## Arquitectura

Ver [`CLAUDE.md`](CLAUDE.md) para la descripción completa de capas, reglas de importación, singletons y convenciones.

Estructura de carpetas:

```
blueprints/     rutas HTTP (webhook, menu, api)
controllers/    lógica de negocio
managers/       acceso a BD y Redis
services/       adaptadores externos (Twilio, Monei, Maps, tokens)
schemas/        modelos Pydantic de entrada
models.py       ORM SQLAlchemy
states.py       enums + máquina de estados
utils/          funciones puras (texto, menú)
config.py       todas las variables de entorno
tests/          suite de tests (110 tests)
```

## Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/webhook` | Recibe mensajes WhatsApp de Twilio |
| POST | `/webhook/monei` | Recibe notificaciones de pago de Monei |
| GET | `/menu/<token>` | Menú web para el cliente |
| GET | `/confirmacion_pago` | Resumen del carrito antes de pagar |
| GET | `/pago_confirmado` | Confirmación tras el pago |
| POST | `/api/confirmacion` | Confirma carrito desde el frontend |
| POST | `/api/agregar_pedido` | Inicia pago en Monei |
| GET | `/api/productos` | Devuelve el catálogo de productos |
| POST | `/api/cambiar_estado_a_enlace` | Vuelve al menú (requiere `X-Internal-Token`) |

## Seguridad

- Webhooks de Twilio verificados con `X-Twilio-Signature` (desactivado con `TESTING=True`)
- Webhooks de Monei verificados con HMAC-SHA256
- Endpoint `/api/cambiar_estado_a_enlace` protegido con `X-Internal-Token`
- CORS configurable por `ALLOWED_ORIGIN`

## Autores

Desarrollado por Jorge Armando Escobar.
