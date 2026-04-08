# Spec: RQ Fase 2 y Fase 3

**Fecha:** 2026-04-08 (revisado post-exploración de código)
**Estado:** Aprobado
**Rama:** `redimiento-colaworker-webhook-meta-tilwgo`
**Contexto:** Continuación de Fase 1 (colas con prioridades + load balancing, commit `9716bc5`)

---

## Corrección arquitectónica clave

El spec original proponía `asignar_picker_job`, `asignar_repartidor_job` y `cambiar_estado_pedido_job` como jobs RQ. **Esto estaba mal.**

La exploración del código revela que esos métodos **ya existen y son síncronos**:
- `picking_flujo.py:asignar_picker()` — síncrono, ya valida + crea PickingPedido + cambia estado
- `reparto_asignacion.py:asignar_repartidor()` — síncrono, ya valida + crea Reparto + cambia estado

RQ es para operaciones externas lentas o background. El operador necesita confirmación inmediata al asignar un picker. 202-encolado no sirve aquí.

**Regla definitiva:**

```
Síncrono + tenacity → operaciones de dashboard que el operador espera confirmar
RQ async            → side effects (notificaciones WhatsApp, estado_operativo, métricas)
```

---

## Objetivo

Completar el sistema con protección de datos (Fase 2) y visibilidad operacional (Fase 3):

1. **Capa 1:** Idempotencia + tenacity en managers síncronos + DLQ + Sentry alertas para jobs RQ
2. **Capa 2:** RQ Dashboard + Sentry Performance en jobs RQ
3. **Capa 3:** Jobs RQ de side effects (notificaciones al picker/repartidor por WhatsApp)

---

## Decisiones de diseño

| Tema | Decisión | Razón |
|------|----------|-------|
| Operaciones de dashboard | Síncrono + tenacity | Operador espera confirmación inmediata. RQ añadiría latencia y polling sin beneficio. |
| Side effects | RQ async | Notificaciones WhatsApp son externas, lentas, pueden fallar — merecen reintentos y aislamiento. |
| Alertas | Sentry | Ya tiene `SENTRY_DSN` en `.env.example`. Sin infraestructura extra. |
| Sagas | Reintentar + DLQ (sin compensación) | Side effects fallidos no invalidan la operación principal. El operador ya tiene confirmación. |
| Métricas SLA | Sentry Performance | Sin tabla nueva. Sentry gestiona P50/P95 por job. |

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────┐
│ SÍNCRONO + TENACITY (operaciones que el operador ve)    │
│                                                         │
│  picking_flujo.py:asignar_picker()                      │
│  reparto_asignacion.py:asignar_repartidor()             │
│  gestor_pedidos_mixin.py:cambiar_estado_pedido()        │
│                                                         │
│  Patrón:                                                │
│  1. Validar                                             │
│  2. Idempotencia check                                  │
│  3. Operar en BD                                        │
│  4. Commit                                              │
│  5. Disparar side effects → queue_whatsapp / queue_dash │
│  6. Devolver (True, "ok") o (False, "error")            │
└─────────────────────────────────────────────────────────┘
              ↓ disparan side effects async

┌─────────────────────────────────────────────────────────┐
│ RQ ASYNC (side effects y background)                    │
│                                                         │
│  queue_whatsapp → notificar_picker_job                  │
│                   notificar_repartidor_job               │
│                   notificar_cliente_*                   │
│                                                         │
│  queue_dashboard → actualizar_estado_operativo_job      │
│                    (ya implementado en Fase 1)          │
└─────────────────────────────────────────────────────────┘
```

---

## Capa 1 — Protección de datos

### 1.1 Tenacity en managers síncronos

Los managers actuales capturan `SQLAlchemyError` pero no tienen reintentos automáticos ante caídas transitorias de BD (conexión drop, timeout).

**Añadir `@retry` de tenacity en métodos críticos:**

```python
# picking_flujo.py
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from sqlalchemy.exc import OperationalError

_retry_db = retry(
    retry=retry_if_exception_type(OperationalError),  # Solo errores de conexión, no de lógica
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    reraise=True,
)

class GestorPickingFlujoMixin:

    @_retry_db
    def asignar_picker(self, pedido_id: int, empleado_id: int) -> tuple:
        # ... código existente sin cambios ...
```

**Métodos que deben recibir `@_retry_db`:**

| Archivo | Método |
|---------|--------|
| `picking_flujo.py` | `asignar_picker()`, `reasignar_picker()`, `completar_picking()` |
| `reparto_asignacion.py` | `asignar_repartidor()` |
| `gestor_pedidos_mixin.py` | `cambiar_estado_pedido()` |

**Importante:** `retry_if_exception_type(OperationalError)` — solo reintenta errores de conexión, NO errores de validación de negocio (`ValueError`, `IntegrityError`). Un picking duplicado no debe reintentarse; una conexión caída sí.

---

### 1.2 Idempotencia en managers síncronos

`asignar_picker()` ya tiene idempotencia parcial (verifica si existe PickingPedido antes de crear). Pero si la BD cae después del `INSERT` y antes del `commit`, el reintento de tenacity volvería a intentar crear y fallaría con IntegrityError.

**Patrón correcto:** manejar `IntegrityError` como idempotencia explícita:

```python
from sqlalchemy.exc import IntegrityError

def asignar_picker(self, pedido_id: int, empleado_id: int) -> tuple:
    s = self.session
    try:
        # Check explícito antes de actuar
        existente = s.query(PickingPedido).filter_by(pedido_id=pedido_id).first()
        if existente:
            logger.info(f"Picking {pedido_id} ya existe — idempotente")
            return True, "Picking ya asignado"

        # ... crear picking ...
        s.commit()
        return True, "Picker asignado correctamente"

    except IntegrityError:
        # Carrera entre dos requests: el otro ganó, no es error
        s.rollback()
        logger.info(f"IntegrityError en picking {pedido_id} — idempotente (race condition)")
        return True, "Picking ya asignado"

    except SQLAlchemyError as e:
        s.rollback()
        logger.error("Error asignando picker %s: %s", pedido_id, e)
        return False, "Error de base de datos"
```

---

### 1.3 Dead Letter Queue (DLQ) — solo para jobs RQ

Cuando un job RQ agota sus reintentos (notificación que nunca llega), nadie se entera.

**Tabla nueva:** `failed_jobs`

```python
# models.py — añadir
class FailedJob(Base):
    __tablename__ = 'failed_jobs'

    id          = Column(Integer, primary_key=True, autoincrement=True)
    job_id      = Column(String(100), nullable=False)       # ID RQ
    job_type    = Column(String(100), nullable=False)       # "notificar_picker_job"
    queue_name  = Column(String(50),  nullable=False)       # "whatsapp", "dashboard"
    payload     = Column(Text,        nullable=True)        # JSON con args (sin datos sensibles)
    error       = Column(Text,        nullable=False)       # traceback completo
    retries     = Column(Integer,     nullable=False, default=0)
    created_at  = Column(DateTime,    default=datetime.utcnow, nullable=False)
    resolved_at = Column(DateTime,    nullable=True)        # NULL = sin resolver
    resolved_by = Column(Integer, ForeignKey('empleados.EmpleadoID'), nullable=True)
```

**Archivo:** `models.py`
**Migración:** `migrations/add_failed_jobs.sql`

---

### 1.4 Callback `on_failure` para jobs RQ

**Archivo nuevo:** `utils/rq_callbacks.py`

```python
import json
import logging
import sentry_sdk

logger = logging.getLogger(__name__)

def on_job_failure(job, connection, type, value, traceback_obj):
    """RQ callback: persiste en failed_jobs + alerta Sentry al agotar reintentos.

    Tiene try/except propio: si BD está caída, Sentry recibe la alerta de todos modos.
    """
    from database import SessionLocal
    from models import FailedJob

    # 1. Persistir en BD (best effort)
    s = SessionLocal()
    try:
        s.add(FailedJob(
            job_id=job.id,
            job_type=job.func_name,
            queue_name=job.origin,
            payload=json.dumps(list(job.args)),  # args solo, sin kwargs sensibles
            error=str(value),
            retries=getattr(job, 'retries_left', 0),
        ))
        s.commit()
        logger.error(f"Job fallido persistido en DLQ: {job.func_name} (job_id={job.id})")
    except Exception as db_err:
        logger.error(f"No se pudo guardar failed_job en BD: {db_err}")
        s.rollback()
    finally:
        s.close()

    # 2. Alerta Sentry (siempre, independiente de BD)
    with sentry_sdk.push_scope() as scope:
        scope.set_tag("job_type", job.func_name)
        scope.set_tag("queue", job.origin)
        scope.set_extra("job_id", job.id)
        scope.set_extra("args", job.args)
        sentry_sdk.capture_exception(value)
```

**Uso en cada `enqueue`:**
```python
from utils.rq_callbacks import on_job_failure

queue_whatsapp.enqueue(
    notificar_picker_job,
    picker_telefono,
    pedido_id,
    on_failure=on_job_failure,
    retry=3,
    failure_ttl=86400,
)
```

---

## Capa 2 — Visibilidad

### 2.1 RQ Dashboard

**Instalación:** `pip install rq-dashboard` → añadir a `requirements.txt`

**Archivo nuevo:** `blueprints/rq_dashboard_bp.py`

```python
import rq_dashboard
from flask import session, redirect, url_for
import config

def register_rq_dashboard(app):
    app.config['RQ_DASHBOARD_REDIS_URL'] = (
        f"redis://{config.REDIS_HOST}:{config.REDIS_PORT}/{config.REDIS_DB}"
    )

    @rq_dashboard.blueprint.before_request
    def _require_login():
        if 'empleado_id' not in session:
            return redirect(url_for('auth.login'))

    app.register_blueprint(
        rq_dashboard.blueprint,
        url_prefix='/rq-dashboard',
    )
```

**Registro en `main.py`:**
```python
from blueprints.rq_dashboard_bp import register_rq_dashboard
register_rq_dashboard(app)
```

**Acceso:** `/rq-dashboard` — solo con sesión activa.

---

### 2.2 Sentry Performance en jobs RQ

**Decorator en `utils/rq_callbacks.py`:**

```python
import functools
import sentry_sdk

def sentry_job(op_name: str = "rq.job"):
    """Wrappea un job RQ con una transacción Sentry Performance."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with sentry_sdk.start_transaction(op=op_name, name=func.__name__):
                return func(*args, **kwargs)
        return wrapper
    return decorator
```

Se aplica **solo a jobs RQ**, no a métodos síncronos de managers (Sentry SDK instrumenta SQLAlchemy automáticamente para transacciones síncronas si `traces_sample_rate` está configurado).

---

## Capa 3 — Jobs RQ de side effects

Los jobs en RQ son **solo notificaciones y background**. La operación principal ya ocurrió de forma síncrona.

### managers/dashboard/jobs.py

**`notificar_picker_job(picker_telefono: str, pedido_id: int)`**
```
1. Construir mensaje WhatsApp al picker
2. Llamar a services/whatsapp_service.py:enviar_mensaje()
3. Si falla → RQ reintenta (retry=3) → on_failure → DLQ + Sentry
```

**`notificar_repartidor_job(repartidor_telefono: str, pedido_id: int)`**
```
1. Construir mensaje WhatsApp al repartidor
2. Llamar a services/whatsapp_service.py:enviar_mensaje()
3. Si falla → RQ reintenta → on_failure → DLQ + Sentry
```

**`actualizar_estado_operativo_job`** — ya implementado en Fase 1 (`_base.py`). Mover a este archivo para centralizar todos los jobs de dashboard.

### Dónde se disparan

Dentro de los métodos síncronos, **después del commit exitoso**:

```python
# picking_flujo.py:asignar_picker()
s.commit()  # ← operación principal confirmada

# Ahora disparar side effects (best effort — no revertir si falla el enqueue)
try:
    queue_whatsapp.enqueue(
        notificar_picker_job,
        empleado.Telefono,
        pedido_id,
        on_failure=on_job_failure,
        retry=3,
        failure_ttl=86400,
    )
except Exception as e:
    logger.warning(f"No se pudo encolar notificación picker: {e}")
    # No fallar — picking ya está creado correctamente

self._actualizar_estado_operativo(empleado_id, 'ocupado')  # ya usa RQ en Fase 1
return True, "Picker asignado correctamente"
```

---

## Flujo completo corregido

```
1. Operador: "Asignar picker 5 al pedido 123"
   POST /dashboard/picking/assign

2. Blueprint valida inputs y llama manager síncrono:
   gestor_dashboard.asignar_picker(123, 5)

3. Manager ejecuta síncronamente (tenacity protege contra BD caída):
   ├─ Idempotencia: PickingPedido existe? No → continuar
   ├─ Crear PickingPedido + PickingItems
   ├─ Cambiar estado pedido → EN_PREPARACION
   ├─ Guardar HistorialEstadoPedido
   └─ COMMIT ← operación confirmada en BD

4. Manager dispara side effects (async, best effort):
   ├─ queue_whatsapp.enqueue(notificar_picker_job, tel, 123)
   └─ queue_dashboard.enqueue(actualizar_estado_operativo_job, 5, "ocupado")

5. Blueprint responde 200 OK inmediato:
   {"status": "asignado", "picking_id": 45}  ← el operador ve confirmación

6. Workers procesan side effects en background:
   ├─ Picker recibe WhatsApp "tienes un nuevo pedido"
   └─ Estado operativo actualizado en BD

7. Si side effect falla N veces → on_failure:
   ├─ INSERT en failed_jobs
   └─ Sentry alerta al equipo técnico
   (el picking ya está creado — no hay rollback)
```

---

## Archivos afectados

| Archivo | Cambio |
|---------|--------|
| `models.py` | Añadir clase `FailedJob` |
| `migrations/add_failed_jobs.sql` | NUEVO: CREATE TABLE failed_jobs |
| `database.py` | Añadir `FailedJob` a `create_all` |
| `utils/rq_callbacks.py` | NUEVO: `on_job_failure` + `@sentry_job` |
| `managers/dashboard/jobs.py` | NUEVO: `notificar_picker_job`, `notificar_repartidor_job`, mover `actualizar_estado_operativo_job` |
| `managers/dashboard/picking_flujo.py` | Añadir `@_retry_db` + idempotencia IntegrityError + encolar notificación post-commit |
| `managers/dashboard/reparto_asignacion.py` | Añadir `@_retry_db` + encolar notificación post-commit |
| `managers/dashboard/_base.py` | Apuntar `_ejecutar_actualizar_estado` al job centralizado en `jobs.py` |
| `blueprints/rq_dashboard_bp.py` | NUEVO: montar rq-dashboard con login_required |
| `main.py` | Registrar `rq_dashboard_bp` |
| `requirements.txt` | Añadir `rq-dashboard` |

---

## Orden de implementación (3 PRs)

### PR 1 — Capa 1 (protección)
1. `models.py` → clase `FailedJob`
2. `migrations/add_failed_jobs.sql`
3. `database.py` → `create_all` para `FailedJob`
4. `utils/rq_callbacks.py` → `on_job_failure` + `@sentry_job`
5. `picking_flujo.py` → tenacity + idempotencia IntegrityError
6. `reparto_asignacion.py` → tenacity

### PR 2 — Capa 2 (visibilidad)
1. `requirements.txt` → `rq-dashboard`
2. `blueprints/rq_dashboard_bp.py`
3. `main.py` → registrar blueprint

### PR 3 — Capa 3 (side effects jobs + notificaciones)
1. `managers/dashboard/jobs.py` → jobs de notificación
2. `picking_flujo.py` → encolar notificaciones post-commit
3. `reparto_asignacion.py` → encolar notificaciones post-commit
4. `managers/dashboard/_base.py` → apuntar a jobs centralizado

---

## Tests que deben existir

| Test | Qué verifica |
|------|-------------|
| `test_asignar_picker_idempotente` | Segunda llamada con mismo pedido_id → `(True, "Picking ya asignado")` |
| `test_asignar_picker_race_condition` | IntegrityError → tratado como idempotencia, no como error |
| `test_asignar_picker_tenacity_reintenta` | OperationalError → tenacity reintenta 3 veces |
| `test_asignar_picker_encola_notificacion` | Post-commit → `queue_whatsapp.enqueue()` llamado |
| `test_asignar_picker_continua_si_enqueue_falla` | Si encolar falla → picking creado de todos modos |
| `test_on_job_failure_persiste_en_bd` | Crea `FailedJob` en BD cuando callback se llama |
| `test_on_job_failure_persiste_sentry_si_bd_cae` | Si BD falla en callback → Sentry recibe alerta igualmente |
| `test_sentry_job_decorator` | Wrappea correctamente, propaga excepciones |
| `test_rq_dashboard_requiere_login` | GET /rq-dashboard sin sesión → redirect a login |
| `test_notificar_picker_job_llama_whatsapp` | Job llama a `whatsapp_service.enviar_mensaje()` con args correctos |

---

## Notas de seguridad

- `/rq-dashboard` protegido: sin `session['empleado_id']` → redirect a login.
- `payload` en `failed_jobs` almacena args del job como JSON. Los jobs de notificación tienen teléfonos — considerar loguear solo `pedido_id` y `empleado_id`, no el teléfono completo.
- `on_job_failure` no falla si BD está caída: tiene `try/except` independiente. Sentry siempre recibe.
- Tenacity usa `retry_if_exception_type(OperationalError)`: no reintenta errores de negocio (`ValueError`, `IntegrityError`), evitando loops infinitos en datos inválidos.
