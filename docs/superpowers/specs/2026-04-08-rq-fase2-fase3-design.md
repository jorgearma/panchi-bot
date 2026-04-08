# Spec: RQ Fase 2 y Fase 3

**Fecha:** 2026-04-08  
**Estado:** Aprobado  
**Rama:** `redimiento-colaworker-webhook-meta-tilwgo`  
**Contexto:** Continuación de Fase 1 (colas con prioridades + load balancing, commit `9716bc5`)

---

## Objetivo

Completar el sistema RQ de Panchi-bot con protección de datos (Fase 2) y visibilidad operacional (Fase 3), siguiendo el principio de despliegue incremental: la protección llega antes que la visibilidad.

---

## Decisiones de diseño

| Tema | Decisión | Razón |
|------|----------|-------|
| Alertas | Sentry | Ya tiene `SENTRY_DSN` en `.env.example`. Sin infraestructura extra. |
| Transacciones saga | Reintentar + DLQ + alerta (sin compensación) | Sobreingeniería para este tamaño. Reintentos + idempotencia es suficiente. |
| Métricas SLA | Sentry Performance | Sin tabla nueva, sin dashboard propio. Sentry lo gestiona. |
| Organización | 3 capas independientes (datos → visibilidad → jobs) | Deploy incremental. Capa 1 puede ir a producción sola. |

---

## Arquitectura: 3 capas

```
Capa 1 (protección de datos)
├── Idempotencia en todos los jobs
├── Dead Letter Queue → tabla failed_jobs
└── Sentry alertas en on_failure callback

Capa 2 (visibilidad)
├── RQ Dashboard → /rq-dashboard (protegido con login)
└── Sentry Performance → @sentry_job decorator

Capa 3 (jobs operacionales)
├── managers/pedidos/jobs.py (asignar_picker, asignar_repartidor, cambiar_estado)
└── managers/dashboard/jobs.py (actualizar_estado_operativo — mover de _base.py)
```

---

## Capa 1 — Protección de datos

### 1.1 Idempotencia

**Principio:** Cada job verifica si ya completó antes de actuar. Si ya está hecho, exit limpio sin error ni log de warning.

**Reglas por job:**

| Job | Check de idempotencia |
|-----|----------------------|
| `asignar_picker_job(pedido_id, picker_id)` | `PickingPedido.filter_by(pedido_id=pedido_id).first()` → skip si existe |
| `asignar_repartidor_job(pedido_id, repartidor_id)` | `Reparto.filter_by(pedido_id=pedido_id).first()` → skip si existe |
| `cambiar_estado_pedido_job(pedido_id, nuevo_estado)` | `pedido.Estado == nuevo_estado` → skip |
| `actualizar_estado_operativo_job(empleado_id, nuevo_estado)` | `empleado.estado_operativo == nuevo_estado` → skip |

**Patrón:**
```python
@staticmethod
def asignar_picker_job(pedido_id: int, picker_id: int):
    s = SessionLocal()
    try:
        # IDEMPOTENCIA
        if s.query(PickingPedido).filter_by(pedido_id=pedido_id).first():
            logger.info(f"Picking {pedido_id} ya existe — skip (reintento idempotente)")
            return

        # LÓGICA
        ...
        s.commit()
    except Exception as e:
        s.rollback()
        raise  # RQ reintenta
    finally:
        s.close()
```

---

### 1.2 Dead Letter Queue (DLQ)

**Tabla nueva:** `failed_jobs`

```python
class FailedJob(Base):
    __tablename__ = 'failed_jobs'

    id          = Column(Integer, primary_key=True, autoincrement=True)
    job_id      = Column(String(100), nullable=False)       # ID RQ
    job_type    = Column(String(100), nullable=False)       # nombre función
    queue_name  = Column(String(50),  nullable=False)       # "pedidos", "dashboard"
    payload     = Column(Text,        nullable=True)        # JSON con args
    error       = Column(Text,        nullable=False)       # traceback completo
    retries     = Column(Integer,     nullable=False, default=0)
    created_at  = Column(DateTime,    default=datetime.utcnow, nullable=False)
    resolved_at = Column(DateTime,    nullable=True)        # NULL = sin resolver
    resolved_by = Column(Integer, ForeignKey('empleados.EmpleadoID'), nullable=True)
```

**Archivo:** `models.py` — añadir clase `FailedJob`  
**Migración:** `migrations/add_failed_jobs.sql`

---

### 1.3 Callback `on_failure`

**Archivo:** `utils/rq_callbacks.py` (nuevo)

```python
import json
import sentry_sdk

def on_job_failure(job, connection, type, value, traceback_obj):
    """RQ callback: persiste en failed_jobs + alerta Sentry al agotar reintentos."""
    from database import SessionLocal
    from models import FailedJob

    s = SessionLocal()
    try:
        s.add(FailedJob(
            job_id=job.id,
            job_type=job.func_name,
            queue_name=job.origin,
            payload=json.dumps(list(job.args)),
            error=str(value),
            retries=getattr(job, 'retries_left', 0),
        ))
        s.commit()
    except Exception as db_err:
        logger.error(f"No se pudo guardar failed_job: {db_err}")
        s.rollback()
    finally:
        s.close()

    # Capturar en Sentry con contexto completo
    with sentry_sdk.push_scope() as scope:
        scope.set_tag("job_type", job.func_name)
        scope.set_tag("queue", job.origin)
        scope.set_extra("job_id", job.id)
        scope.set_extra("payload", job.args)
        sentry_sdk.capture_exception(value)
```

**Uso en cada `enqueue`:**
```python
from utils.rq_callbacks import on_job_failure

queue_pedidos.enqueue(
    asignar_picker_job,
    pedido_id,
    picker_id,
    on_failure=on_job_failure,
    retry=5,
    failure_ttl=86400
)
```

---

## Capa 2 — Visibilidad

### 2.1 RQ Dashboard

**Instalación:** `pip install rq-dashboard` → añadir a `requirements.txt`

**Integración Flask:**
```python
# blueprints/rq_dashboard_bp.py (nuevo)
import rq_dashboard
import config

def register_rq_dashboard(app):
    app.config['RQ_DASHBOARD_REDIS_URL'] = (
        f"redis://{config.REDIS_HOST}:{config.REDIS_PORT}/{config.REDIS_DB}"
    )
    app.register_blueprint(
        rq_dashboard.blueprint,
        url_prefix='/rq-dashboard',
    )
```

**Protección:** middleware `before_request` que verifica sesión activa (usa el sistema de auth existente de Flask — `session['empleado_id']`).

**Registro en `main.py`:**
```python
from blueprints.rq_dashboard_bp import register_rq_dashboard
register_rq_dashboard(app)
```

**URL en producción:** `https://tu-dominio/rq-dashboard` — solo accesible con login de empleado.

---

### 2.2 Sentry Performance

**Decorator reutilizable** en `utils/rq_callbacks.py`:

```python
import functools
import sentry_sdk

def sentry_job(op_name: str = "rq.job"):
    """Decorator para wrappear jobs con Sentry Performance transaction."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with sentry_sdk.start_transaction(op=op_name, name=func.__name__):
                return func(*args, **kwargs)
        return wrapper
    return decorator
```

**Uso:**
```python
@sentry_job(op="rq.job")
def asignar_picker_job(pedido_id: int, picker_id: int):
    ...
```

**Métricas disponibles en Sentry → Performance:**
- P50 / P95 / P99 de duración por tipo de job
- Error rate por job
- Trazas completas de cada ejecución

---

## Capa 3 — Jobs operacionales

### Archivos nuevos

```
managers/pedidos/jobs.py      ← 3 jobs operacionales
managers/dashboard/jobs.py    ← 1 job (actualizar_estado_operativo, movido de _base.py)
```

### managers/pedidos/jobs.py

**`asignar_picker_job(pedido_id: int, picker_id: int)`**
1. Idempotencia: `PickingPedido.filter_by(pedido_id=pedido_id)` → skip si existe
2. Validar que `pedido.Estado == EstadoPedido.PAGADO` o `CONTRA_REEMBOLSO`
3. Crear `PickingPedido(pedido_id, empleado_id=picker_id, estado=PENDIENTE)`
4. Actualizar `pedido.Estado = EN_PREPARACION`
5. Guardar `HistorialEstadoPedido`
6. Encolar notificación WhatsApp al picker en `queue_whatsapp` (best effort — no falla el job si esto falla)
7. Encolar actualización `estado_operativo` picker a "con_trabajo" en `queue_dashboard`

**`asignar_repartidor_job(pedido_id: int, repartidor_id: int)`**
1. Idempotencia: `Reparto.filter_by(pedido_id=pedido_id)` → skip si existe
2. Validar que `pedido.Estado == EstadoPedido.PREPARADO`
3. Crear `Reparto(pedido_id, repartidor_id, estado=ASIGNADO)`
4. Actualizar `pedido.Estado = EN_REPARTO`
5. Guardar `HistorialEstadoPedido`
6. Encolar notificación WhatsApp al repartidor en `queue_whatsapp` (best effort)
7. Encolar actualización `estado_operativo` repartidor a "en_reparto" en `queue_dashboard`

**`cambiar_estado_pedido_job(pedido_id: int, nuevo_estado: str)`**
1. Idempotencia: `pedido.Estado == nuevo_estado` → skip
2. Validar transición con `transicion_valida_pedido()` de `states.py`
3. Actualizar `pedido.Estado = nuevo_estado`
4. Guardar `HistorialEstadoPedido`

### managers/dashboard/jobs.py

**`actualizar_estado_operativo_job(empleado_id: int, nuevo_estado: str)`**  
Mover la lógica de `_base.py._ejecutar_actualizar_estado()` aquí.  
`_base.py` sigue encolando en `queue_dashboard` pero apunta a esta función.

---

## Flujo completo (con todas las capas)

```
1. Operador: "Asignar picker 5 al pedido 123"
   POST /dashboard/picking/assign

2. Blueprint valida inputs
   queue_pedidos.enqueue(
       asignar_picker_job, 123, 5,
       on_failure=on_job_failure,
       retry=5
   )
   → 202 Accepted (inmediato)

3. Worker procesa asignar_picker_job(123, 5)
   ├─ Idempotencia: PickingPedido existe? No → continuar
   ├─ Crear PickingPedido
   ├─ Cambiar estado pedido → EN_PREPARACION
   ├─ queue_whatsapp.enqueue(notificar_picker, tel_picker, 123)
   └─ queue_dashboard.enqueue(actualizar_estado_operativo_job, 5, "con_trabajo")

4. Si falla (BD caída):
   └─ RQ reintenta (hasta 5 veces)
   └─ Si agota reintentos → on_job_failure:
       ├─ INSERT en failed_jobs
       └─ sentry_sdk.capture_exception → Alerta supervisor

5. Sentry Performance registra:
   asignar_picker_job  duración: 145ms  resultado: OK
```

---

## Archivos afectados

| Archivo | Cambio |
|---------|--------|
| `models.py` | Añadir clase `FailedJob` |
| `utils/rq_callbacks.py` | NUEVO: `on_job_failure` + `@sentry_job` |
| `managers/pedidos/jobs.py` | NUEVO: 3 jobs operacionales |
| `managers/dashboard/jobs.py` | NUEVO: `actualizar_estado_operativo_job` |
| `managers/dashboard/_base.py` | Actualizar `enqueue` para apuntar a nuevo job |
| `blueprints/rq_dashboard_bp.py` | NUEVO: montar rq-dashboard |
| `main.py` | Registrar `rq_dashboard_bp` |
| `requirements.txt` | Añadir `rq-dashboard` |
| `migrations/add_failed_jobs.sql` | NUEVO: CREATE TABLE failed_jobs |
| `database.py` | `create_all` para tabla `FailedJob` |

---

## Orden de implementación (deploy incremental)

### PR 1 — Capa 1 (protección)
1. `models.py` → `FailedJob`
2. `migrations/add_failed_jobs.sql`
3. `utils/rq_callbacks.py` → `on_job_failure` + `@sentry_job`
4. `managers/dashboard/_base.py` → idempotencia en `_ejecutar_actualizar_estado`

### PR 2 — Capa 2 (visibilidad)
1. `requirements.txt` → `rq-dashboard`
2. `blueprints/rq_dashboard_bp.py`
3. `main.py` → registrar blueprint

### PR 3 — Capa 3 (jobs operacionales)
1. `managers/pedidos/jobs.py`
2. `managers/dashboard/jobs.py`
3. Actualizar blueprints para encolar en lugar de llamar managers directamente

---

## Tests que deben existir

| Test | Qué verifica |
|------|-------------|
| `test_asignar_picker_job_idempotente` | Segunda llamada con mismo pedido_id → skip sin error |
| `test_asignar_picker_job_exito` | Crea PickingPedido + cambia estado pedido |
| `test_asignar_repartidor_job_idempotente` | Segunda llamada → skip |
| `test_cambiar_estado_pedido_transicion_invalida` | Levanta ValueError si transición no válida |
| `test_on_job_failure_persiste_en_bd` | Crea FailedJob en BD cuando callback se llama |
| `test_on_job_failure_captura_sentry` | sentry_sdk.capture_exception se llama con contexto |
| `test_sentry_job_decorator` | Wrappea correctamente, propaga excepciones |
| `test_rq_dashboard_requiere_login` | GET /rq-dashboard sin sesión → redirect a login |

---

## Notas de seguridad

- `/rq-dashboard` protegido con el sistema auth existente (`session['empleado_id']`). Sin login → redirect.
- `payload` en `failed_jobs` almacena args del job como JSON. Si los args contienen datos sensibles (teléfonos, direcciones), considerar no persistirlos o cifrarlos en Fase 4.
- `on_job_failure` no falla si BD está caída (try/except independiente) — Sentry siempre recibe la alerta aunque BD no pueda guardar el `FailedJob`.
