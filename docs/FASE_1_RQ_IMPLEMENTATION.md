# Fase 1: Implementación RQ (Colas con Prioridades)

**Fecha:** 2026-04-08  
**Commit:** `9716bc5` (feat(rq): implementar fase 1 - colas con prioridades y load balancing)  
**Estado:** ✅ IMPLEMENTADO

---

## Resumen de cambios

Migramos de **threading daemon invisible** a **RQ (Redis Queue)** con colas separadas y load balancing.

### Archivos modificados

1. **`message_queue.py`** — Expandir de 1 cola a 3 colas con prioridades
2. **`worker.py`** — Worker escucha todas las colas en orden de prioridad
3. **`managers/dashboard/_base.py`** — Reemplazar `Thread` con `queue_dashboard.enqueue()`
4. **`docker-compose.yml`** — Agregar `worker-2` para load balancing

---

## Arquitectura: 3 colas independientes

```
┌─────────────────────────────────────────┐
│ queue_whatsapp (CRÍTICA)                │
│ - timeout: 5m                           │
│ - reintentos: 3                         │
│ - uso: mensajes al cliente (tiempo real)│
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ queue_pedidos (IMPORTANTE)              │
│ - timeout: 5m                           │
│ - reintentos: 5                         │
│ - uso: operacional (asignaciones, etc)  │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ queue_dashboard (BACKGROUND)            │
│ - timeout: 10m                          │
│ - reintentos: 3                         │
│ - uso: observabilidad (métricas, logs)  │
└─────────────────────────────────────────┘

       ↓ Los workers escuchan en este orden

    [Worker 1] ↔ [Worker 2]
    (load balancing automático)
```

---

## Cómo usar (para developers)

### Encolar un job en `queue_dashboard`

```python
# managers/dashboard/_base.py
from message_queue import queue_dashboard

def _actualizar_estado_operativo(self, empleado_id: int, nuevo_estado: str):
    # Encola el job (no bloquea)
    job = queue_dashboard.enqueue(
        self._ejecutar_actualizar_estado,  # función a ejecutar
        empleado_id,                        # arg 1
        nuevo_estado,                       # arg 2
        retry=3,                            # reintentar 3 veces si falla
        failure_ttl=86400                   # guardar error 24h
    )
    logger.debug(f"Encolado: job_id={job.id}")
```

### Crear un job nuevo (Fase 2)

```python
# managers/pedidos/asignacion_mixin.py
from message_queue import queue_pedidos

def asignar_picker(self, pedido_id: int, picker_id: int):
    """Encola una asignación de picker."""
    job = queue_pedidos.enqueue(
        self._asignar_picker_job,
        pedido_id,
        picker_id,
        retry=5,         # más reintentos (más crítico)
        failure_ttl=86400
    )
    logger.info(f"Asignación encolada: pedido {pedido_id} → picker {picker_id}")
    return {'job_id': job.id, 'status': 'encolado'}, 202

@staticmethod
def _asignar_picker_job(pedido_id: int, picker_id: int):
    """Job que corre en el worker."""
    from database import SessionLocal
    s = SessionLocal()
    try:
        # ... lógica aquí ...
        s.commit()
        logger.info(f"✅ Asignación completada")
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        s.rollback()
        raise  # RQ reintenta automáticamente
    finally:
        s.close()
```

---

## Flujo de ejecución

```
1. REQUEST LLEGA
   POST /dashboard/empleado/5/estado
         ↓
2. BLUEPRINT VALIDA
   gestor_dashboard._actualizar_estado_operativo(5, "recibiendo_pedidos")
         ↓
3. ENCOLA EN RQ (¡INMEDIATO!)
   queue_dashboard.enqueue(_ejecutar_actualizar_estado, 5, "recibiendo_pedidos")
         ↓
4. RESPONDE 202 OK
   {"status": "encolado", "job_id": "abc123"}
         ↓
5. WORKER PROCESA EN BACKGROUND
   [Worker 1 o 2]
   _ejecutar_actualizar_estado(5, "recibiendo_pedidos")
         ↓
   ¿Falla? → RQ reintentar (hasta 3 veces)
   ¿Éxito? → logger.info("✅ Estado actualizado")
         ↓
6. BD ACTUALIZADA
   empleado 5 ahora tiene estado "recibiendo_pedidos"
```

---

## Recuperación de fallos de BD

### ANTES (threading daemon):
```
Operador: cambiar estado
    ↓
Thread lanza
    ↓
[BD CADE]
    ↓
Thread falla silenciosamente → logger.warning()
    ↓
PERDIDO. Cambio nunca se hizo.
```

### AHORA (RQ):
```
Operador: cambiar estado
    ↓
Job encolado en Redis
    ↓
[BD CADE]
    ↓
Worker intenta UPDATE → Exception
    ↓
RQ reintentar automáticamente (retry=3)
    ↓
[BD VUELVE 30s después]
    ↓
Worker reintento → Success
    ↓
Cambio completado. RECUPERADO.
```

---

## Validación e input safety

Todos los jobs validan inputs en el método público:

```python
def _actualizar_estado_operativo(self, empleado_id: int, nuevo_estado: str):
    # VALIDAR antes de encolar
    if not isinstance(empleado_id, int) or empleado_id <= 0:
        logger.warning("empleado_id inválido: %s", empleado_id)
        return
    if not nuevo_estado or not isinstance(nuevo_estado, str):
        logger.warning("nuevo_estado inválido: %s", nuevo_estado)
        return
    
    # Si pasó validación, encolar (seguro)
    queue_dashboard.enqueue(...)
```

---

## Logging en cada etapa

```
# Request encolado
DEBUG: "Encolado update estado_operativo: empleado 5 → recibiendo_pedidos (job_id=abc123)"

# Worker procesa
DEBUG: "Worker: actualizando estado_operativo empleado 5 → recibiendo_pedidos"

# Éxito
INFO: "✅ Estado actualizado: empleado 5 → recibiendo_pedidos"

# Fallo
ERROR: "❌ Error al actualizar estado empleado 5: [exception]" (+ traceback)
```

**Resultado:** Completamente observable. No hay operaciones invisibles.

---

## Monitoreo (desarrollo)

Ver cola en tiempo real:

```bash
# En otra terminal
redis-cli

> LLEN rq:queue:whatsapp    # Cuántos jobs esperando
(integer) 3

> LLEN rq:queue:pedidos
(integer) 5

> LLEN rq:queue:dashboard
(integer) 0

# Ver job específico
> HGETALL rq:job:abc123
```

---

## Docker: cómo escalar workers

```bash
# Hoy (2 workers)
docker-compose up

# Mañana (más carga, agregar workers)
docker-compose up --scale worker-1=2 --scale worker-2=3
# (eso crearía 5 workers totales escuchando las 3 colas)

# O simplemente copiar worker-3, worker-4 en docker-compose.yml
```

---

## Checklist: antes de producción (Fase 1)

- [x] RQ instalado (already in requirements.txt)
- [x] 3 colas definidas en `message_queue.py`
- [x] Worker escucha 3 colas con prioridades
- [x] `_actualizar_estado_operativo()` encola en RQ
- [x] Validación de inputs antes de encolar
- [x] Logging en DEBUG, INFO, ERROR
- [x] Try/except con rollback en worker
- [x] 2 workers en docker-compose.yml
- [x] Alias `message_queue = queue_whatsapp` para compatibilidad
- [ ] Probar en staging (simular fallo de BD)
- [ ] Ajustar `retry` según necesidad (hoy: 3-5)
- [ ] Ajustar `failure_ttl` según auditoría (hoy: 86400 = 24h)

---

## Próximos pasos (Fase 2+3)

### Fase 2 (en 2-3 semanas):
- [ ] Idempotencia: verificar si picking/reparto ya existe antes de crear
- [ ] Dead Letter Queue: tabla `FailedJob` para jobs fallidos
- [ ] RQ Dashboard: instalar `rq-dashboard` para monitoreo visual

### Fase 3 (en 1-2 meses):
- [ ] Transacciones saga: compensación en fallos multi-cola
- [ ] Alertas: notificar supervisor si job falla N veces
- [ ] Métricas: medir tiempo promedio por job tipo

---

## Troubleshooting

### Problema: "Worker no procesa jobs"
```bash
# Verificar que Redis está vivo
redis-cli ping
# Output: PONG

# Verificar que worker está corriendo
docker-compose ps
# Debe ver: worker-1 y worker-2 en estado "Up"

# Ver logs del worker
docker-compose logs worker-1 -f
```

### Problema: "Job se queda en reintentos infinitos"
```python
# Revisar que método público valida inputs
# Si inputs inválidos, NO encolar (return early)

# Revisar que job @staticmethod no usa self
# @staticmethod
# def _ejecutar_job(arg1, arg2):  # ← sin self
#     # ...

# Si job es incapaz de completar nunca, configura timeout
queue_dashboard.enqueue(..., job_timeout='10m')
```

### Problema: "Un worker se cuelga procesando un job largo"
```python
# Job está tardando > timeout configurado
# Default: 5m (whatsapp, pedidos), 10m (dashboard)

# Fix: configura timeout más largo en enqueue
queue_pedidos.enqueue(
    slow_job,
    args,
    job_timeout='30m'  # 30 minutos si es operación lenta
)
```

---

## Resumen

| Aspecto | Antes (threading) | Ahora (RQ) |
|--------|--|--|
| Fallos | Invisibles | Reintentos automáticos |
| Observabilidad | Logs + hope | Logs + job_id + failure_ttl |
| Scalabilidad | 1 thread/request | N workers, colas independientes |
| Priorización | No | Sí (whatsapp > pedidos > dashboard) |
| Recuperación BD | No | Sí (reintentos cuando BD vuelve) |

---

**¿Preguntas o problemas?** Ver `CLAUDE.md` para arquitectura general.
