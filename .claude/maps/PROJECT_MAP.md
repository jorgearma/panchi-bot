# PROJECT_MAP.md

> Referencia técnica completa de **panchi-bot** — válida tanto para onboarding como para consulta diaria.

---

## 1. Visión General

**Panchi-bot** es un sistema de gestión de pedidos para un restaurante en Tarancón, España. Los clientes hacen pedidos a través de WhatsApp, navegan por el menú en una página web y pagan online vía Monei. El personal gestiona los pedidos desde un dashboard interno con roles diferenciados.

| Componente        | Tecnología                                      |
|-------------------|-------------------------------------------------|
| Backend           | Python 3.12 + Flask 3.1                         |
| Base de datos     | SQL Server (SQLAlchemy 2.0 + pyodbc)            |
| Caché / Sesiones  | Redis 5.2 (FakeRedis en tests)                  |
| WhatsApp          | Twilio o Meta Cloud API (configurable)          |
| Pagos             | Monei 2.5                                       |
| Geolocalización   | Google Maps API + Shapely 2.1                   |
| NLP               | spaCy 3.8 (`es_core_news_sm`)                   |
| Frontend          | Jinja2 + HTML/CSS/JS                            |
| Monitoreo         | Sentry SDK 2.54                                 |
| Servidor          | gunicorn + Nginx (Docker Compose)               |

---

## 2. Cómo Ejecutar el Proyecto

### Requisitos previos

```bash
# Python 3.12+
python --version

# Driver ODBC 18 para SQL Server (instalación de sistema, NO pip)
# Ubuntu/Debian:
curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add -
# (seguir documentación oficial de Microsoft para ODBC Driver 18)

# Modelo de spaCy en español
python -m spacy download es_core_news_sm
```

### Setup local

```bash
git clone <repo>
cd panchi-bot

python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Editar .env con tus credenciales (ver Sección 7)

python main.py  # Arranca en 0.0.0.0:5000
```

### Con Docker Compose (app + Redis + Nginx)

```bash
docker-compose up           # Levanta los 3 servicios
docker-compose up --build   # Reconstruye la imagen de la app
```

### Tests

```bash
pytest                       # Todos los tests (~3 segundos, 110 tests)
pytest tests/test_webhook.py # Un archivo específico
pytest -v --tb=short         # Verbose con tracebacks cortos
```

### ngrok para webhooks en local

```bash
ngrok http 5000
# Copiar la URL pública a PUBLIC_URL en .env
# Configurar esa URL en el dashboard de Twilio o Meta
```

---

## 3. Estructura de Carpetas

```
panchi-bot/
├── blueprints/          # Rutas HTTP (Flask Blueprints) — solo routing y serialización
├── controllers/         # Lógica de negocio — state machines, validaciones, orquestación
├── managers/            # Acceso a datos — operaciones DB y Redis; `estado_usuario.py` implementa la máquina de estados de registro sobre Redis
├── services/            # Adaptadores de servicios externos (WhatsApp, Maps, tokens)
├── schemas/             # Validación de entrada con Pydantic
├── utils/               # Helpers pequeños y sin estado
├── templates/           # Plantillas Jinja2 organizadas por feature
│   ├── auth/
│   ├── dashboard/
│   ├── empleado/
│   ├── picker/
│   ├── repartidor/
│   ├── productos/
│   └── macros/
├── static/              # CSS, JS, imágenes
├── tests/               # 31 archivos de test, 395 funciones de test (pytest)
├── migrations/          # Scripts SQL de migración (ejecutar manualmente)
├── docs/                # Documentación adicional
├── main.py              # App factory + registro de blueprints
├── config.py            # Carga de variables de entorno
├── models.py            # 21 modelos ORM (SQLAlchemy)
├── states.py            # Enums y reglas de transición de estado
├── database.py          # Gestión de sesión SQLAlchemy
├── docker-compose.yml   # Orquestación: app + Redis + Nginx
├── Procfile             # Despliegue Heroku (gunicorn, 2 workers)
├── nginx.conf           # Proxy inverso
└── .env.example         # Plantilla de configuración
```

---

## 4. Arquitectura del Sistema

El sistema está organizado en **5 capas horizontales** con dependencias unidireccionales (de arriba a abajo):

```
┌─────────────────────────────────────────────────────────────┐
│  BLUEPRINTS  (HTTP in/out, validación de firma, routing)    │
│  webhook · menu · api · auth · dashboard · picker           │
│  repartidor · empleado · productos · metricas_*             │
└────────────────────────┬────────────────────────────────────┘
                         │ llama a
┌────────────────────────▼────────────────────────────────────┐
│  CONTROLLERS  (Lógica de negocio, máquinas de estado)       │
│  registro · pedido · pago · mensajes_registrados            │
└────────────────────────┬────────────────────────────────────┘
                         │ llama a
┌────────────────────────▼────────────────────────────────────┐
│  MANAGERS  (Acceso a datos: DB y Redis)                     │
│  gestor_pedidos · gestor_usuarios · gestor_productos        │
│  gestor_redis · gestor_dashboard · gestor_empleado          │
│  gestor_metricas · estado_usuario                           │
└────────────────────────┬────────────────────────────────────┘
                         │ llama a
┌────────────────────────▼────────────────────────────────────┐
│  SERVICES  (Adaptadores externos, sin lógica de negocio)    │
│  whatsapp_service · maps_service · token_service            │
└────────────────────────┬────────────────────────────────────┘
                         │ comunica con
┌────────────────────────▼────────────────────────────────────┐
│  EXTERNOS                                                   │
│  SQL Server · Redis · Twilio/Meta · Monei · Google Maps     │
└─────────────────────────────────────────────────────────────┘
```

### Rol de Redis

Redis actúa como **tres sistemas distintos** dentro de la misma instancia:

| Uso                    | Clave (patrón)         | Gestor responsable  |
|------------------------|------------------------|---------------------|
| Estado de registro     | `<telefono>`           | `gestor_redis`      |
| Bloqueo anti-spam      | `bloqueo:<telefono>`   | `gestor_redis`      |
| Token de menú          | `<uuid-token>`         | `token_service`     |
| Carrito (sesión)       | `pedido:<uuid>`        | `controllers/pago`  |

### Dos flujos independientes

- **Flujo bot**: WhatsApp → `/webhook` → controllers → managers → respuesta WhatsApp
- **Flujo dashboard**: Navegador → `/dashboard*`, `/picker*`, `/repartidor*` → managers → render HTML

Ambos flujos comparten los managers y la base de datos, pero son completamente independientes en routing y autenticación.

---

## 5. Entry Points

| Archivo       | Función        | Qué hace                                                                 |
|---------------|----------------|--------------------------------------------------------------------------|
| `main.py`     | `create_app()` | App factory: valida env vars, configura logging y Sentry, registra los 11 blueprints |
| `main.py`     | `if __name__`  | Inicia Flask dev server + conecta la BD                                  |
| `Procfile`    | `web:`         | Producción: `gunicorn "main:create_app()" --bind 0.0.0.0:5000 --workers 2 --timeout 30 --access-logfile -` |
| `docker-compose.yml` | `app`   | Contenedor principal (apunta a Procfile)                                 |

### Blueprints registrados

| Blueprint              | Rutas principales                            | Propósito                                  |
|------------------------|----------------------------------------------|--------------------------------------------|
| `auth`                 | `/auth/login`, `/auth/logout`                | Autenticación del personal                 |
| `webhook`              | `/webhook`, `/webhook/monei`, `/webhook/meta`| Entrada de mensajes WhatsApp y pagos       |
| `menu`                 | `/menu/<token>`, `/confirmacion_pago`        | Menú web del cliente                       |
| `api`                  | `/api/confirmacion`, `/api/agregar_pedido`   | API del carrito y pagos                    |
| `dashboard`            | `/dashboard/*`                               | Panel de operaciones (admin)               |
| `picker`               | `/picker/*`                                  | Cola de preparación (almacén)              |
| `repartidor`           | `/repartidor/*`                              | Cola y tracking de entregas                |
| `empleado`             | `/empleado/*`                                | Fichaje y métricas del empleado            |
| `productos`            | `/productos-admin/*`                         | Gestión de stock y precios                 |
| `metricas_operacion`   | `/metricas/operacion/*`                      | Métricas en tiempo real                    |
| `metricas_analitica`   | `/metricas/analitica/*`                      | Métricas históricas y analíticas           |
| *(global)*             | `/health`                                    | Health check: verifica Redis + DB          |

---

## 6. Flujo Completo de la Aplicación

### 6.1 Registro de usuario nuevo

```
Cliente envía mensaje por WhatsApp
        │
        ▼
POST /webhook  ──► usuario NO en DB
        │
        ▼
controllers/registro.py  (máquina de estados en Redis)
        │
        ├─ SALUDO_INICIAL ──────► enviar mensaje de bienvenida
        ├─ ESPERANDO_CONFIRMACION ► confirmar intención
        ├─ ESPERANDO_NOMBRE ──────► pedir nombre (validado con spaCy)
        ├─ ESPERANDO_DIRECCION ───► pedir dirección (validada con Google Maps + Shapely)
        └─ CONFIRMANDO_DIRECCION ► confirmar dirección
                │
                ▼
        Guardar usuario en SQL Server
        Borrar estado de Redis
```

El rollback es posible: si el usuario corrige la dirección, el estado vuelve a `ESPERANDO_DIRECCION`.

### 6.2 Pedido completo (happy path — pago online)

```
Cliente envía mensaje por WhatsApp
        │
        ▼
POST /webhook ──► usuario EN DB
        │
        ▼
controllers/mensajes_registrados.py
        │
        ├─ Estado PENDIENTE ──► generar token (Redis, TTL), enviar link de menú
        │
        ▼
GET /menu/<token>  ──► validar token ──► render menú desde DB
        │  (cliente navega, agrega productos al carrito en JS)
        ▼
POST /api/confirmacion  ──► validar token ──► guardar carrito en Redis ──► estado ENLACE2
        │
        ▼
POST /api/agregar_pedido
        ├─ Validar precios contra DB (previene manipulación del carrito)
        ├─ Crear registro en tabla `pedidos` + `pedido_detalles`
        ├─ Crear pago en Monei ──► obtener URL de pago
        └─ Estado CONFIRMANDO_PAGO
        │
        ▼
POST /webhook/monei  ──► verificar HMAC ──► estado PAGADO
        ├─ Notificar al cliente por WhatsApp
        └─ Crear registro en tabla `picking_pedido`
```

### 6.3 Pago en efectivo (contra reembolso)

```
POST /api/agregar_pedido_efectivo
        ├─ Crear pedido en DB
        └─ Estado CONTRA_REEMBOLSO (salta el flujo de Monei)
        │
        ▼
Flujo operativo (igual que pago online desde aquí)
```

### 6.4 Flujo operativo (picking → reparto)

```
Estado PAGADO / CONTRA_REEMBOLSO
        │
        ▼
Dashboard: asignar picker ──► Estado EN_PREPARACION
        │
        ▼
GET /picker/cola ──► picker coge el pedido ──► actualiza items uno a uno
        │
        ▼
POST /picker/picking/<id>/finalizar ──► Estado PREPARADO
        │
        ▼
Dashboard: asignar repartidor ──► Estado EN_REPARTO (registro en `reparto`)
        │
        ▼
GET /repartidor/cola ──► repartidor marca salida / entrega / cobro
        │
        ▼
POST /repartidor/reparto/<id>/entregar ──► Estado ENTREGADO (terminal)
```

### 6.5 Diagrama de estados del pedido

```
                    ┌──────────┐
                    │ PENDIENTE│◄──────────────────────────┐
                    └────┬─────┘                           │
                         │                                 │
                    ┌────▼─────┐                           │
              ┌────►│  ENLACE  │◄─── rollback por error ───┤
              │     └────┬─────┘                           │
              │          │                                 │
              │     ┌────▼─────┐                           │
              └─────│  ENLACE2 │ (botón "atrás" → ENLACE)  │
                    └──┬───┬───┘                           │
                       │   │                               │
          ┌────────────┘   └──────────────┐                │
          ▼                               ▼                │
┌─────────────────┐             ┌──────────────────┐       │
│ CONFIRMANDO_PAGO│             │ CONTRA_REEMBOLSO │       │
└────────┬────────┘             └────────┬─────────┘       │
         │                               │                 │
         ▼                               │                 │
     ┌───────┐                           │         ┌───────────┐
     │ PAGADO│◄──────────────────────────┘         │ CANCELADO │
     └──┬┬───┘                                     └─────┬─────┘
        ││                                               │
        │└──────────────────────────────────────┐        ▼
        ▼                                       ▼  ┌──────────────┐
┌────────────────┐                       ┌──────────┤  REEMBOLSADO │
│ EN_PREPARACION │                       │ (desde   │   (terminal) │
└───────┬────────┘                       │ PAGADO o └──────────────┘
        │                                │ CANCELADO)
        ▼
  ┌──────────┐
  │ PREPARADO│
  └─────┬────┘
        │
        ▼
  ┌──────────┐
  │EN_REPARTO│
  └─────┬────┘
        │
        ▼
  ┌──────────┐
  │ENTREGADO │ (terminal)
  └──────────┘
```

> Las transiciones se definen y validan en `states.py`. Cualquier cambio de estado debe pasar por `gestor_pedidos.py`, que aplica la validación y registra el historial en `historial_estados_pedido`.

---

## 7. Variables de Entorno

Copiar `.env.example` a `.env`. Variables mínimas para arrancar:

| Variable                  | Descripción                                                  | Requerida             |
|---------------------------|--------------------------------------------------------------|-----------------------|
| `SECRET_KEY`              | Clave para sesiones Flask                                    | Siempre               |
| `WHATSAPP_PROVIDER`       | `twilio` o `meta`                                            | Siempre               |
| `SQL_SERVER`              | Host del servidor SQL Server                                 | Siempre               |
| `SQL_DATABASE`            | Nombre de la base de datos                                   | Siempre               |
| `SQL_UID` / `SQL_PWD`     | Credenciales de SQL Server                                   | Siempre               |
| `REDIS_HOST`              | Host de Redis (default: `localhost`)                         | Siempre               |
| `PUBLIC_URL`              | URL pública del servidor (ngrok en dev)                      | Siempre               |
| `MONEI_API_KEY`           | API Key de Monei                                             | Siempre               |
| `MONEI_WEBHOOK_SECRET`    | Secret HMAC para validar webhooks de Monei                   | Siempre               |
| `GOOGLE_MAPS_API_KEY`     | API Key de Google Maps (geocoding + validación de zona)      | Siempre               |
| `INTERNAL_API_TOKEN`      | Token para proteger `/api/cambiar_estado_a_enlace`           | Siempre               |
| `TWILIO_ACCOUNT_SID`      | SID de cuenta Twilio                                         | Si `PROVIDER=twilio`  |
| `TWILIO_AUTH_TOKEN`       | Token de auth Twilio                                         | Si `PROVIDER=twilio`  |
| `TWILIO_WHATSAPP_NUMBER`  | Número WhatsApp de Twilio (`whatsapp:+34...`)                | Si `PROVIDER=twilio`  |
| `META_ACCESS_TOKEN`       | Token de acceso Meta                                         | Si `PROVIDER=meta`    |
| `META_PHONE_NUMBER_ID`    | ID del número en Meta                                        | Si `PROVIDER=meta`    |
| `META_APP_SECRET`         | Secret para verificación HMAC de Meta                        | Si `PROVIDER=meta`    |
| `META_VERIFY_TOKEN`       | Token para verificación del webhook de Meta                  | Si `PROVIDER=meta`    |
| `ALLOWED_ORIGIN`          | Origen permitido en CORS para `/api/*`                       | Recomendada           |
| `SENTRY_DSN`              | DSN de Sentry para error tracking                            | Recomendada           |
| `CUSTOMER_SUPPORT_PHONE`  | Teléfono de soporte enviado al cliente en errores            | Recomendada           |

---

## 8. Dependencias Importantes

| Paquete          | Versión  | Propósito                                               | Riesgo si falla            |
|------------------|----------|---------------------------------------------------------|----------------------------|
| `SQLAlchemy`     | 2.0.38   | ORM y gestión de sesión DB                              | Sistema completo caído     |
| `pyodbc`         | 5.2.0    | Driver de conexión a SQL Server                         | Sin acceso a BD            |
| `tenacity`       | 9.1.4    | Reintentos automáticos en DB y APIs externas            | Fragilidad ante timeouts   |
| `redis`          | 5.2.1    | Estado de sesión, bloqueos, tokens                      | Sin estado entre mensajes  |
| `fakeredis`      | 2.27.0   | Mock de Redis en tests (no requiere Redis real)         | Tests no corren            |
| `twilio`         | 9.4.6    | SDK WhatsApp provider 1                                 | Sin mensajería (si Twilio) |
| `Monei`          | 2.5.2    | Pagos online                                            | Sin cobros online          |
| `spacy`          | 3.8.11   | Validación de nombres en registro (`es_core_news_sm`)   | Registro fallido           |
| `shapely`        | 2.1.2    | Validación de zona de reparto (geometría)               | Cualquier dir. aceptada    |
| `pydantic`       | 2.10.6   | Validación de schemas de entrada (webhooks)             | Sin validación de input    |
| `sentry-sdk`     | 2.54.0   | Error tracking en producción                            | Sin alertas de errores     |

> **Nota crítica:** `pyodbc` requiere que el **ODBC Driver 18 for SQL Server** esté instalado en el sistema operativo. No es un paquete de pip — si el SO no lo tiene, la app no arranca. En Docker, la imagen base debe incluirlo.

> **Nota sobre spaCy:** El modelo `es_core_news_sm` debe descargarse por separado con `python -m spacy download es_core_news_sm`. No se instala con `pip install`.

---

## 9. Posibles Problemas y Code Smells

### 9.1 `gestor_dashboard.py` — God Object (121 KB)

**Problema:** Un único archivo concentra toda la lógica de agregación de datos para el dashboard: pedidos activos, picking, reparto, empleados, turnos, alertas y más. Con 121 KB, es el archivo más grande del proyecto por un amplio margen.

**Riesgo:** Cambios en cualquier parte del dashboard requieren modificar este archivo, aumentando la probabilidad de regresiones no relacionadas. Es imposible hacer tests unitarios granulares. El tiempo de carga del módulo y la dificultad de revisión de código escalan con el tamaño.

**Sugerencia:** Extraer submódulos por dominio: `gestor_pedidos_dashboard.py`, `gestor_turnos.py`, `gestor_reparto_dashboard.py`. Cada uno con responsabilidad única y testeable de forma aislada.

---

### 9.2 `gestor_metricas.py` — Archivo sobredimensionado (48 KB)

**Problema:** Similar al anterior, concentra todos los cálculos de métricas (operacionales e históricas) en un solo archivo.

**Riesgo:** Las métricas operacionales (tiempo real) y analíticas (históricas) tienen ciclos de vida y frecuencias de cambio muy distintos. Mezclarlos en un archivo hace que cambios en uno puedan introducir errores en el otro.

**Sugerencia:** Separar en `gestor_metricas_operacion.py` y `gestor_metricas_analitica.py`, alineado con la separación que ya existe en los blueprints (`metricas_operacion.py` vs `metricas_analitica.py`).

---

### 9.3 Threading manual para notificaciones WhatsApp — sin pool ni manejo de errores

**Problema:** En `blueprints/picker.py`, `blueprints/repartidor.py` y `blueprints/dashboard.py`, las notificaciones WhatsApp se lanzan con `threading.Thread(target=_notificar, ...).start()` directamente, sin pool de threads ni captura de excepciones en el hilo hijo.

```python
# Patrón repetido en 3 blueprints:
def _notificar(telefono: str, mensaje: str) -> None:
    enviar_mensaje_whatsapp(telefono, mensaje)

threading.Thread(target=_notificar, args=(tel, msg)).start()
```

**Riesgo:** Bajo carga alta se crean threads ilimitados. Si `enviar_mensaje_whatsapp` lanza una excepción, esta se pierde silenciosamente (el hilo muere sin log ni Sentry). En producción, notificaciones fallidas son invisibles.

**Sugerencia:** Usar `concurrent.futures.ThreadPoolExecutor` con un pool acotado, y envolver la llamada en try/except con logging explícito dentro del thread.

---

### 9.4 Ruta typo activa en producción — `/webhoo/monei`

**Problema:** En `blueprints/webhook.py` existe esta doble ruta con un TODO pendiente:

```python
@blueprint_webhook.route('/webhoo/monei', methods=['POST'])  # TODO: remove once Monei dashboard points to /webhook/monei
@blueprint_webhook.route('/webhook/monei', methods=['POST'])
def webhook_monei():
```

**Riesgo:** La ruta errónea (`/webhoo/monei`) está expuesta públicamente y procesa pagos reales. Si alguien la descubre puede enviar payloads (aunque estén protegidos por HMAC). Es superficie de ataque innecesaria.

**Sugerencia:** Verificar en el dashboard de Monei que la URL apunte a `/webhook/monei` y eliminar la ruta typo.

---

### 9.5 Ausencia de CI/CD — los tests nunca se ejecutan automáticamente

**Problema:** No existe ningún pipeline de CI (GitHub Actions, GitLab CI, etc.). Los 110 tests solo se ejecutan si el desarrollador los corre manualmente.

**Riesgo:** Regresiones pueden llegar a `master` sin detección. El proyecto tiene 395 funciones de test en 31 archivos, pero ese valor es nulo si no se ejecutan en cada push.

**Sugerencia:** Añadir un workflow de GitHub Actions mínimo que ejecute `pytest` en cada push y PR. Con FakeRedis y mocks existentes, los tests no requieren ningún servicio externo.

---

### 9.6 `openai` en `requirements.txt` — dependencia no usada

**Problema:** `openai==1.64.0` está en `requirements.txt` pero no aparece en ningún `import` del código fuente.

**Riesgo:** Añade ~50 MB al entorno, amplía la superficie de vulnerabilidades (cada dependencia es un vector potencial), y confunde a quien lee las dependencias intentando entender el sistema.

**Sugerencia:** Si es una dependencia futura planificada, documentarlo. Si no, eliminarla de `requirements.txt`.

---

### 9.7 Sin rate limiting en `/webhook` — vulnerable a flood de mensajes

**Problema:** El endpoint `POST /webhook` no tiene ningún mecanismo de rate limiting por número de teléfono. Existe un mecanismo de bloqueo en Redis, pero solo se activa después de que el mensaje ya fue procesado.

**Riesgo:** Un número puede enviar cientos de mensajes en segundos, disparando múltiples llamadas a Google Maps, spaCy y SQL Server antes de que el bloqueo actúe.

**Sugerencia:** Implementar rate limiting con `flask-limiter` (soporta Redis como backend), limitando por `From` del form de Twilio antes de entrar al procesamiento de negocio.

---

### 9.8 Lógica de negocio mezclada en `blueprints/api.py`

**Problema:** `api.py` no solo hace routing — contiene validaciones de negocio como la comparación de precios del carrito contra la base de datos, generación de UUIDs y coordinación directa con múltiples managers.

**Riesgo:** Dificulta testear la lógica de validación de precios de forma aislada. Los blueprints deberían ser una capa delgada que delega en controllers.

**Sugerencia:** Extraer la validación de precios a `controllers/pago.py` o un nuevo `controllers/carrito.py`, dejando `api.py` como puro routing.

---

### 9.9 SQL Server como única opción — acoplamiento al SO

**Problema:** La conexión depende de `pyodbc` con `ODBC Driver 18 for SQL Server`, que debe instalarse en el sistema operativo. No hay posibilidad de usar otro motor (PostgreSQL, SQLite) ni siquiera para tests.

**Riesgo:** El onboarding local es complejo para nuevos desarrolladores en macOS o Linux. Los tests no pueden correr en un runner de CI estándar sin configuración adicional del SO. (Los tests actuales evitan esto mockeando la DB.)

**Sugerencia:** A largo plazo, considerar una capa de abstracción que permita SQLite en tests de integración. A corto plazo, documentar la instalación del driver ODBC en el README.
