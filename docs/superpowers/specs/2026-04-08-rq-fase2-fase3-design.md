# Spec: RQ Fase 2 y Fase 3

**Fecha:** 2026-04-08 (revisado post-exploración de código)
**Estado:** Aprobado
**Rama:** `redimiento-colaworker-webhook-meta-tilwgo`
**Contexto:** Continuación de Fase 1 (colas con prioridades + load balancing, commit `9716bc5`)

---

## Correcciones arquitectónicas (tras lectura completa del código)

### Corrección 1 — Jobs RQ para operaciones síncronas
El spec original proponía `asignar_picker_job`, `asignar_repartidor_job` como jobs RQ. **Estaba mal.**

`picking_flujo.py:asignar_picker()` y `reparto_asignacion.py:asignar_repartidor()` ya existen y son síncronos. El operador necesita confirmación inmediata — 202-encolado no sirve aquí.

### Corrección 2 — Threads daemon ocultos en `completar_picking`
`picking_flujo.py:completar_picking()` tiene **2 threads daemon adicionales** que el spec no cubría:

```python
# línea 226 — descuenta stock tras completar picking
Thread(target=_descontar, daemon=True).start()

# línea 250 — actualiza disponibilidad del picker
Thread(target=_actualizar_disponibilidad_picker, daemon=True).start()
```

Ambos deben migrarse a RQ. El de stock es especialmente crítico: si falla silenciosamente, el producto sigue disponible para venta aunque esté agotado.

### Corrección 3 — Idempotencia: guard, no skip
`asignar_picker()` ya hace **upsert** (si existe, actualiza; si no, crea). Es semánticamente correcto para el caso de uso. No cambiamos ese comportamiento. Solo añadimos `IntegrityError` como guard ante race conditions.

**Regla definitiva:**

```
Síncrono + tenacity → operaciones de dashboard que el operador espera confirmar
RQ async            → side effects (notificaciones, stock, estado_operativo, métricas)
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
│  queue_whatsapp  → notificar_picker_job                 │
│                    notificar_repartidor_job              │
│                    notificar_cliente_*                  │
│                                                         │
│  queue_dashboard → actualizar_estado_operativo_job      │
│                    descontar_stock_picking_job  ← NUEVO │
└─────────────────────────────────────────────────────────┘
```

---

## Capa 1 — Protección de datos

### 1.1 Tenacity en managers síncronos

Los managers actuales capturan `SQLAlchemyError` pero no tienen reintentos automáticos ante caídas transitorias de BD (conexión drop, timeout).

**⚠️ Bug crítico a evitar:** Los métodos retornan `(False, "Error de base de datos")` ante cualquier excepción. Si se pone `@_retry_db` sin re-raise de `OperationalError`, tenacity ve `(False, "...")` como retorno exitoso y **nunca reintenta**. El decorator sería silenciosamente inútil.

**Patrón correcto:** re-raise `OperationalError` antes del catch genérico para que tenacity lo vea:

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

_retry_db = retry(
    retry=retry_if_exception_type(OperationalError),  # Solo errores de conexión
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    reraise=True,
)

@_retry_db
def asignar_picker(self, pedido_id: int, empleado_id: int) -> tuple:
    s = self.session
    try:
        # ... lógica sin cambios ...
        s.commit()
        self._actualizar_estado_operativo(empleado_id, 'ocupado')
        return True, "Picker asignado correctamente"

    except OperationalError:
        s.rollback()
        raise  # ← tenacity necesita que se propague para reintentar

    except IntegrityError:
        s.rollback()
        logger.info("IntegrityError picking %s — race condition resuelta", pedido_id)
        return True, "Picker asignado correctamente"

    except SQLAlchemyError as e:
        s.rollback()
        logger.error("Error asignando picker %s: %s", pedido_id, e)
        return False, "Error de base de datos"
```

**Métodos que deben recibir `@_retry_db`:**

| Archivo | Método | Observación |
|---------|--------|-------------|
| `picking_flujo.py` | `asignar_picker()` | ✅ Seguro — sin lógica post-commit compleja |
| `picking_flujo.py` | `reasignar_picker()` | ✅ Seguro |
| `picking_flujo.py` | `completar_picking()` | ❌ NO aplicar — tiene lógica post-commit (crear Reparto, encolar RQ). Un retry reiniciaría todo incluyendo lo ya hecho. Ver nota abajo. |
| `reparto_asignacion.py` | `asignar_repartidor()` | ✅ Seguro |
| `gestor_pedidos_mixin.py` | `cambiar_estado_pedido()` | ✅ Seguro |

**`completar_picking` — manejo manual de OperationalError:**

En lugar del decorator, manejar `OperationalError` explícitamente solo en el bloque del commit principal:

```python
def completar_picking(self, picking_id: int, picker_id: int | None = None) -> tuple:
    s = self.session
    intentos = 0
    while intentos < 3:
        try:
            # ... lógica pre-commit ...
            s.commit()
            break  # commit exitoso
        except OperationalError:
            s.rollback()
            intentos += 1
            if intentos >= 3:
                logger.error("completar_picking %s falló 3 veces por OperationalError", picking_id)
                return False, "Error de base de datos", None
            time.sleep(2 ** intentos)  # backoff manual
        except IntegrityError:
            s.rollback()
            return False, "Error de integridad", None
        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error completando picking %s: %s", picking_id, e)
            return False, "Error de base de datos", None

    # post-commit: crear Reparto, encolar RQ — ya no puede reintentar desde aquí
    ...
```

---

### 1.2 Idempotencia en managers síncronos

`asignar_picker()` ya hace **upsert**: si existe PickingPedido lo actualiza, si no existe lo crea. Es el comportamiento correcto para el caso de uso (reasignación incluida). **No lo cambiamos.**

Lo que añadimos es un **guard de race condition**: si dos requests llegan al mismo tiempo y ambos intentan el INSERT simultáneamente, el segundo recibe `IntegrityError`. Hoy ese error se propaga como un 500. Con el guard, se trata como éxito idempotente.

```python
# picking_flujo.py — solo añadir el except IntegrityError,
# el resto del código no cambia

def asignar_picker(self, pedido_id: int, empleado_id: int) -> tuple:
    s = self.session
    try:
        # ... código existente sin cambios (upsert) ...
        s.commit()
        self._actualizar_estado_operativo(empleado_id, 'ocupado')
        return True, "Picker asignado correctamente"

    except IntegrityError:
        # Race condition: dos requests simultáneos, el otro ganó el INSERT
        # Tratar como éxito — el picking quedó creado
        s.rollback()
        logger.info("IntegrityError en picking %s — race condition resuelta", pedido_id)
        return True, "Picker asignado correctamente"

    except SQLAlchemyError as e:
        s.rollback()
        logger.error("Error asignando picker %s: %s", pedido_id, e)
        return False, "Error de base de datos"
```

El mismo guard aplica a `asignar_repartidor()` — `Reparto` también tiene restricción `unique(pedido_id)`.

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

Los jobs en RQ son **solo side effects y background**. La operación principal ya ocurrió síncronamente.

### Inventario completo de threads daemon a migrar

| Archivo | Thread actual | Job RQ nuevo | Cola |
|---------|--------------|-------------|------|
| `_base.py` | `_ejecutar()` — actualizar estado_operativo | `actualizar_estado_operativo_job` ✅ ya migrado (Fase 1) | `queue_dashboard` |
| `picking_flujo.py:completar_picking` | `_descontar()` — descontar stock | `descontar_stock_picking_job` ← **NUEVO** | `queue_dashboard` |
| `picking_flujo.py:completar_picking` | `_actualizar_disponibilidad_picker()` | Eliminar thread, llamar directo `_actualizar_estado_operativo()` | `queue_dashboard` |

### managers/dashboard/jobs.py (archivo nuevo)

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

**`descontar_stock_picking_job(picking_id: int)`**

```
⚠️ Recibe picking_id (int), NO la lista de items precalculada.

Razón: si recibiera la lista como argumento y RQ reintentara,
el job descontaría stock dos veces sin saber que ya lo hizo.
Con picking_id, lee el estado actual desde BD en cada ejecución.

Idempotencia garantizada por campo PickingPedido.stock_descontado:
1. Lee picking desde BD
2. Si picking.stock_descontado == True → skip (ya ejecutado)
3. Si picking.estado != COMPLETADO → skip (no debería descontar)
4. Por cada item del picking:
   - estado "encontrado" → stock -= cantidad_encontrada (mínimo 0)
   - estado "sin_stock"  → stock = 0, disponible = False
   Usa with_for_update() para evitar race conditions de stock
5. picking.stock_descontado = True
6. s.commit()
Si falla → RQ reintenta (retry=3) → idempotencia garantiza no duplicar
Si agota reintentos → on_failure → DLQ + Sentry

CRÍTICO: si falla permanentemente, el stock queda incorrecto.
DLQ + alerta Sentry permite detectarlo y corregirlo manualmente.
```

**Cambio en modelo:** añadir campo `stock_descontado` a `PickingPedido`:
```python
stock_descontado = Column(Boolean, nullable=False, default=False)
```
Y en la migración: `ALTER TABLE picking_pedido ADD stock_descontado BIT NOT NULL DEFAULT 0`

**`actualizar_estado_operativo_job`** — ya existe en `_base.py`. Mover a este archivo para centralizar jobs de dashboard.

### Cómo se eliminan los threads de `completar_picking`

**Antes (thread daemon invisible):**
```python
# picking_flujo.py:200-226
if items_para_stock:
    def _descontar(items=items_para_stock):
        # ... lógica de stock ...
    Thread(target=_descontar, daemon=True).start()  # ← invisible si falla

# picking_flujo.py:229-250
if _picker_id:
    def _actualizar_disponibilidad_picker(emp_id=_picker_id):
        # ... comprueba pickings activos → llama _actualizar_estado_operativo ...
    Thread(target=_actualizar_disponibilidad_picker, daemon=True).start()  # ← invisible
```

**Después (RQ):**
```python
# picking_flujo.py:completar_picking() — tras s.commit()

# 1. Descontar stock → RQ (con reintentos y DLQ)
# Pasa picking_id, no la lista — el job lee items desde BD para garantizar idempotencia
try:
    queue_dashboard.enqueue(
        descontar_stock_picking_job,
        picking_id,   # ← int, no lista
        on_failure=on_job_failure,
        retry=3,
        failure_ttl=86400,
    )
except Exception as e:
    logger.warning("No se pudo encolar descontar_stock: %s", e)

# 2. Disponibilidad picker → expire_all + COUNT inline
# El thread original usaba SessionLocal() nueva para evitar caché de la sesión.
# Con expire_all() forzamos recarga desde BD antes del COUNT.
if _picker_id:
    s.expire_all()  # ← forzar recarga para evitar caché post-commit
    activos = s.query(PickingPedido).filter(
        PickingPedido.empleado_id == _picker_id,
        PickingPedido.estado.in_([
            EstadoPicking.PENDIENTE.value,
            EstadoPicking.EN_PROCESO.value,
            EstadoPicking.CON_INCIDENCIAS.value,
        ]),
    ).count()
    if activos == 0:
        self._actualizar_estado_operativo(_picker_id, 'disponible')  # RQ (Fase 1)
```

`s.expire_all()` invalida el identity map antes del COUNT para garantizar que la sesión no devuelve datos cacheados. El coste es mínimo (una query COUNT con índice).

### Side effects en `asignar_picker` y `asignar_repartidor`

```python
# picking_flujo.py:asignar_picker() — tras s.commit()
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
    logger.warning("No se pudo encolar notificación picker: %s", e)
    # No fallar — picking ya está creado

self._actualizar_estado_operativo(empleado_id, 'ocupado')
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

## Flujo completo corregido (`completar_picking`)

```
1. Picker completa el picking
   POST /picker/completar

2. Manager ejecuta síncronamente:
   ├─ picking.estado = COMPLETADO
   ├─ pedido.Estado = PREPARADO
   ├─ Crear Reparto(repartidor_id=None, estado=PENDIENTE)
   └─ COMMIT ← todo confirmado

3. Post-commit side effects:
   ├─ queue_dashboard.enqueue(descontar_stock_picking_job, items)
   ├─ COUNT pickings activos del picker (inline, sin thread)
   └─ si count == 0: _actualizar_estado_operativo(picker_id, 'disponible')

4. Blueprint responde 200 OK inmediato

5. Workers en background:
   ├─ descontar_stock_picking_job actualiza Producto.Stock
   └─ actualizar_estado_operativo_job actualiza Empleado.estado_operativo

6. Si descontar_stock falla N veces → on_failure:
   ├─ INSERT en failed_jobs
   └─ Sentry alerta → equipo corrige stock manualmente
```

---

## Archivos afectados

| Archivo | Cambio |
|---------|--------|
| `models.py` | Añadir clase `FailedJob` + campo `PickingPedido.stock_descontado` |
| `migrations/add_failed_jobs.sql` | NUEVO: CREATE TABLE failed_jobs + ALTER TABLE picking_pedido ADD stock_descontado |
| `database.py` | Añadir `FailedJob` a `create_all` |
| `utils/rq_callbacks.py` | NUEVO: `on_job_failure` + `@sentry_job` |
| `managers/dashboard/jobs.py` | NUEVO: `notificar_picker_job`, `notificar_repartidor_job`, `descontar_stock_picking_job` (recibe `picking_id`), mover `actualizar_estado_operativo_job` |
| `managers/dashboard/picking_flujo.py` | `@_retry_db` en métodos sin post-commit + re-raise `OperationalError` + IntegrityError guard + encolar notif/stock post-commit + eliminar 2 threads daemon + `s.expire_all()` antes COUNT disponibilidad |
| `managers/dashboard/reparto_asignacion.py` | `@_retry_db` + re-raise `OperationalError` + IntegrityError guard + encolar notif post-commit |
| `managers/dashboard/_base.py` | Apuntar `_ejecutar_actualizar_estado` al job en `jobs.py` + eliminar import `threading` |
| `blueprints/rq_dashboard_bp.py` | NUEVO: montar rq-dashboard con `before_request` login guard |
| `main.py` | Registrar `rq_dashboard_bp` |
| `requirements.txt` | Añadir `rq-dashboard` |

---

## Orden de implementación (3 PRs)

### PR 1 — Capa 1 (protección)
1. `models.py` → clase `FailedJob` + campo `PickingPedido.stock_descontado`
2. `migrations/add_failed_jobs.sql` → CREATE TABLE + ALTER TABLE
3. `database.py` → `create_all` para `FailedJob`
4. `utils/rq_callbacks.py` → `on_job_failure` + `@sentry_job`
5. `picking_flujo.py` → `@_retry_db` con re-raise + IntegrityError guard + **eliminar 2 threads daemon** + `expire_all()` + manejo manual OperationalError en `completar_picking`
6. `reparto_asignacion.py` → `@_retry_db` con re-raise + IntegrityError guard

### PR 2 — Capa 2 (visibilidad)
1. `requirements.txt` → `rq-dashboard`
2. `blueprints/rq_dashboard_bp.py`
3. `main.py` → registrar blueprint

### PR 3 — Capa 3 (jobs RQ de side effects)
1. `managers/dashboard/jobs.py` → 4 jobs nuevos
2. `picking_flujo.py` → encolar notif + stock post-commit
3. `reparto_asignacion.py` → encolar notif post-commit
4. `managers/dashboard/_base.py` → apuntar a jobs centralizado + eliminar import `threading`

---

## Tests que deben existir

| Test | Qué verifica |
|------|-------------|
| `test_asignar_picker_race_condition` | IntegrityError → `(True, "Picker asignado")`, no 500 |
| `test_asignar_picker_operational_error_reintenta` | OperationalError → se propaga para tenacity, reintenta hasta 3 veces |
| `test_asignar_picker_operational_error_no_reintenta_integrity` | IntegrityError no llega a tenacity, se maneja como idempotencia |
| `test_asignar_picker_encola_notificacion` | Post-commit → `queue_whatsapp.enqueue()` llamado con teléfono y pedido_id |
| `test_asignar_picker_continua_si_enqueue_falla` | Si encolar notif falla → picking creado, devuelve True |
| `test_completar_picking_encola_picking_id` | Post-commit → `queue_dashboard.enqueue(descontar_stock_picking_job, picking_id)` — pasa int, no lista |
| `test_completar_picking_sin_thread` | `threading.Thread` NO se llama en completar_picking |
| `test_completar_picking_operational_error_reintenta` | OperationalError en commit → reintenta 3 veces con backoff manual |
| `test_descontar_stock_job_idempotente` | Segunda llamada con mismo picking_id → skip si stock_descontado == True |
| `test_descontar_stock_job_encontrado` | estado "encontrado" → stock decrementado, stock_descontado = True tras commit |
| `test_descontar_stock_job_sin_stock` | estado "sin_stock" → stock=0, disponible=False, stock_descontado = True |
| `test_descontar_stock_job_skip_si_no_completado` | picking.estado != COMPLETADO → skip sin error |
| `test_on_job_failure_persiste_en_bd` | Crea `FailedJob` en BD con job_type, queue_name, error |
| `test_on_job_failure_sentry_si_bd_cae` | BD falla en callback → Sentry recibe alerta igualmente |
| `test_sentry_job_decorator` | Wrappea correctamente, propaga excepciones |
| `test_rq_dashboard_requiere_login` | GET /rq-dashboard sin sesión → redirect a login |
| `test_notificar_picker_job_llama_whatsapp` | Job llama a `whatsapp_service.enviar_mensaje()` |

---

## Notas de seguridad

- `/rq-dashboard` protegido: sin `session['empleado_id']` → redirect a login.
- `payload` en `failed_jobs` almacena args del job como JSON. Los jobs de notificación tienen teléfonos — considerar loguear solo `pedido_id` y `empleado_id`, no el teléfono completo.
- `on_job_failure` no falla si BD está caída: tiene `try/except` independiente. Sentry siempre recibe.
- Tenacity usa `retry_if_exception_type(OperationalError)`: no reintenta errores de negocio (`ValueError`, `IntegrityError`), evitando loops infinitos en datos inválidos.
