# Auditoría de `managers/dashboard/_base.py`

> Auditoría técnica estricta. Fecha: 2026-04-08.
> Archivos analizados: `managers/dashboard/_base.py`, `database.py`, `models.py`, `states.py`.

---

## 1. Rol del archivo

**Responsabilidad principal:** Clase base `GestorDashboardBase` que provee infraestructura compartida a todos los mixins del dashboard: acceso a sesión DB, actualización de estado operativo de empleados en background, y queries batch de alta eficiencia para pickings y repartos.

**Qué debería hacer:** Proveer acceso a la sesión SQLAlchemy, helpers de query reutilizables por los mixins, y utilidades de infraestructura de datos. Sin lógica de negocio propia.

**Qué no debería hacer:** Gestionar threads directamente, contener lógica de estado de negocio, ni depender de Flask (el contexto de aplicación es de Flask `g`).

**Dependencias clave:**
- `database.get_db` / `database.SessionLocal` — sesión SQLAlchemy por request y sesión standalone
- `models.Empleado`, `HistorialEstadoPedido`, `PickingPedido`, `Reparto`, `Pedido`
- `states.EstadoPedido`, `EstadoPicking`, `EstadoReparto`
- `threading.Thread` (stdlib)

**Nivel de criticidad:** Alto — es la raíz de herencia de todos los mixins del dashboard. Un fallo aquí afecta toda la operativa del panel.

---

## 2. Lo que hace bien

- **Property `session` con lazy import** (línea 21): el import de `get_db` dentro del property evita importar Flask en el momento del módulo, facilitando el testeo con mocks sin arrancar la app completa.
- **Race condition prevenida con UPDATE atómico** (líneas 43–46): el `UPDATE ... WHERE estado_operativo NOT IN (protegidos)` evita sobreescribir estados manuales entre el read y el write; el comentario lo explica explícitamente.
- **Thread daemon** (línea 54): el flag `daemon=True` garantiza que el thread no bloquea el shutdown del proceso.
- **Manejo de errores en el thread** (líneas 48–52): `try/except/finally` con rollback y cierre de sesión garantiza que la sesión no quede abierta aunque el UPDATE falle.
- **Batch loading con una sola query** (líneas 109–123 y 153–167): `_batch_pickings` y `_batch_repartos` eliminan el N+1 clásico al cargar datos de múltiples empleados en una sola consulta con `IN`.
- **Eager loading explícito** (líneas 111, 155–156): `joinedload` previene lazy-loading silencioso posterior al cierre del contexto de sesión.
- **`_tiempo_medio` con self-join SQL** (líneas 69–87): una sola query en lugar de 1 por pedido; el comentario advierte sobre el supuesto de no-reentrada de estados.
- **Documentación de supuestos** (líneas 103–105, 144–147): los docstrings advierten que `estados_activos` debe ser lista de strings, no de enums, y documentan el supuesto de no-reentrada.
- **`frozenset` para `_ESTADOS_PROTEGIDOS`** (línea 24): inmutable y con lookup O(1).

---

## 3. Hallazgos

### Hallazgo 1

**Tipo:** diseño / acoplamiento
**Severidad:** Media

**Problema:** El método `_actualizar_estado_operativo` gestiona un `threading.Thread` directamente dentro del manager. Los managers deben ser acceso a datos; la decisión de ejecutar algo en background es infraestructura transversal que debería delegarse a una cola (RQ ya existe en el proyecto) o al menos a un helper de infraestructura separado.

**Evidencia:**
```python
# línea 54
Thread(target=_ejecutar, daemon=True).start()
```

**Impacto real:** El número de threads vivos crece si hay picos de tráfico (un thread por cada actualización de estado operativo). RQ ya está disponible y es la solución canónica del proyecto para trabajo en background. Además, mezcla responsabilidad de "transporte de ejecución" con "acceso a datos".

**Recomendación mínima concreta:** Encolar la tarea en RQ (`q.enqueue(actualizar_estado_operativo_task, empleado_id, nuevo_estado)`) en lugar de lanzar un thread. Si se mantiene el thread por simplicidad, añadir un semáforo o pool de threads con límite de concurrencia máxima.

---

### Hallazgo 2

**Tipo:** acoplamiento / testabilidad
**Severidad:** Media

**Problema:** `_actualizar_estado_operativo` usa `from database import SessionLocal` dentro de la función anidada `_ejecutar` (línea 39). Esto crea una dependencia de importación en tiempo de ejecución dentro de un closure, invisible para quien inspecciona la signatura del método. El thread crea su propia `SessionLocal()` de forma directa, sin inyección.

**Evidencia:**
```python
# línea 38-39
from database import SessionLocal
s = SessionLocal()
```

**Impacto real:** Imposible mockear `SessionLocal` en tests del thread sin parchear el módulo `database`. Si `SessionLocal` cambia de interfaz, el fallo es silencioso (el thread muere con un warning que puede perderse en logs).

**Recomendación mínima concreta:** Extraer `_ejecutar` a una función de módulo top-level que reciba `session_factory` como parámetro, o usar RQ donde el worker ya gestiona su propia sesión.

---

### Hallazgo 3

**Tipo:** observabilidad
**Severidad:** Baja

**Problema:** El warning del thread (línea 49) es el único log de todo el archivo. `_tiempo_medio`, `_batch_pickings` y `_batch_repartos` no tienen ningún logging de error. Si una query de batch falla (timeout de SQL Server, pool agotado), la excepción se propaga silenciosamente al caller sin contexto adicional.

**Evidencia:**
```python
# línea 49
logger.warning("No se pudo actualizar estado_operativo de empleado %s: %s", empleado_id, e)
# No existe ningún logger.error en _tiempo_medio, _batch_pickings ni _batch_repartos
```

**Impacto real:** Un fallo en `_batch_repartos` durante una carga del dashboard se presenta al usuario como HTTP 500 sin traza contextual en los logs más allá del stacktrace genérico de Flask.

**Recomendación mínima concreta:** Añadir `logger.error("_batch_pickings falló para ids=%s: %s", ids, e, exc_info=True)` en un `except` que luego re-raise la excepción, para conservar el stacktrace completo con contexto de negocio.

---

### Hallazgo 4

**Tipo:** rendimiento
**Severidad:** Baja

**Problema:** El property `session` (líneas 18–22) llama a `get_db()` en cada acceso. `_batch_pickings` y `_batch_repartos` acceden a `self.session` una vez cada uno (correcto), pero `_tiempo_medio` también accede a `self.session` directamente (línea 65). Si un mixin llama a `self.session` múltiples veces en el mismo método, `get_db()` se invoca repetidamente aunque devuelva la misma instancia gracias a Flask `g`. No es un bug hoy, pero es una dependencia implícita de que `get_db()` sea idempotente.

**Evidencia:**
```python
# línea 19-22
@property
def session(self):
    from database import get_db
    return get_db()
```

**Impacto real:** Bajo mientras `get_db()` mantenga su implementación actual con `flask.g`. Si `get_db()` se modifica para crear una nueva sesión en cada llamada, los mixins empezarían a usar múltiples sesiones simultáneamente.

**Recomendación mínima concreta:** Documentar en el docstring que `session` es idempotente dentro del mismo request gracias a `flask.g`, o añadir un test que verifique que dos llamadas consecutivas devuelven el mismo objeto.

---

### Hallazgo 5

**Tipo:** diseño / seguridad
**Severidad:** Baja

**Problema:** `_tiempo_medio` usa `func.datediff(text('minute'), ...)` (línea 72). `text('minute')` introduce un literal SQL crudo, aunque no es user-supplied. Si el argumento de unidad de tiempo necesitara parametrizarse en el futuro, el patrón invita a pasar valores controlados externamente a `text()`.

**Evidencia:**
```python
# línea 72
func.datediff(text('minute'), h_ini.cambiado_en, h_fin.cambiado_en)
```

**Impacto real:** En el estado actual no hay riesgo de inyección porque `'minute'` es un literal hardcoded. El riesgo es de patrón: si alguien extiende el método para aceptar la unidad como parámetro y no lo limita a un enum, abre inyección SQL.

**Recomendación mínima concreta:** Añadir un comentario `# 'minute' es literal fijo — no parametrizar con input externo` y, si se generaliza, usar un `Literal` de Python para restringir los valores válidos.

---

### Hallazgo 6

**Tipo:** consistencia de estado
**Severidad:** Baja

**Problema:** Si el proceso muere justo después de `s.commit()` en `_ejecutar` pero antes de que el caller reciba la confirmación (edge case de crash), el estado operativo del empleado ya está actualizado en DB pero el objeto de negocio que disparó la actualización podría haber fallado después. No hay ningún mecanismo de compensación.

**Evidencia:**
```python
# líneas 46-47
).update({'estado_operativo': nuevo_estado}, synchronize_session=False)
s.commit()
```

**Impacto real:** Muy bajo en la práctica: `estado_operativo` es un campo de conveniencia UI, no afecta la integridad del pedido ni del pago. El peor caso es que el panel muestre un estado operativo incorrecto hasta el próximo login del empleado.

**Recomendación mínima concreta:** Documentar explícitamente que `estado_operativo` es eventually-consistent y no fuente de verdad para decisiones de negocio.

---

## 4. Riesgos principales si no se toca

| Riesgo | Escenario concreto |
|--------|-------------------|
| Acumulación de threads sin límite | En un pico de 100 peticiones/minuto al dashboard, se lanzan 100 threads simultáneos para actualizar estados operativos, potencialmente superando la capacidad del pool de conexiones SQL Server (por defecto `pool_size=5` en SQLAlchemy) |
| Fallo silencioso de batch queries | `_batch_repartos` falla por timeout de SQL Server; el dashboard presenta un error 500 genérico sin log contextual; el equipo de ops no puede distinguir si fue DB, red o lógica |
| Acoplamiento de `SessionLocal` en closure | Un refactor de `database.py` que cambie `SessionLocal` rompe silenciosamente el thread de actualización de estado; el warning puede perderse si el volumen de logs es alto |

---

## 5. Refactor mínimo recomendado

### Qué tocar primero (en orden de impacto)

1. **Reemplazar `Thread` por tarea RQ** — elimina el riesgo de thread storm y alinea con la arquitectura del proyecto. Tiempo estimado: 30 min.
2. **Añadir `logger.error(..., exc_info=True)` en `_batch_pickings` y `_batch_repartos`** — mejora observabilidad inmediatamente sin cambiar lógica. Tiempo estimado: 10 min.
3. **Documentar la dependencia de idempotencia de `self.session`** — previene regresiones futuras. Tiempo estimado: 5 min.

### Qué NO tocar todavía

- La lógica del UPDATE atómico con `notin_` — está bien diseñada y tiene comentario explicativo.
- Los métodos `_batch_pickings` y `_batch_repartos` — el batch loading con `joinedload` es correcto y eficiente.
- El self-join de `_tiempo_medio` — es la solución correcta al N+1 anterior.

---

## 6. Tests que deberían existir

- `test_actualizar_estado_operativo_no_sobreescribe_protegidos` — verifica que un empleado en `en_pausa` no cambia de estado cuando se llama `_actualizar_estado_operativo`.
- `test_actualizar_estado_operativo_empleado_id_none_no_lanza` — verifica que el guard `if not empleado_id` funciona con `None`, `0` y string vacío.
- `test_batch_pickings_ids_vacios_devuelve_defaultdict` — verifica que con `ids=[]` se retorna el defaultdict sin lanzar query.
- `test_batch_repartos_ids_vacios_devuelve_defaultdict` — análogo para repartos.
- `test_batch_pickings_clasifica_activos_y_completados` — dado un mix de pickings con estados activos y COMPLETADO, verifica que cada uno va al bucket correcto.
- `test_tiempo_medio_sin_registros_devuelve_none` — verifica que cuando no hay historial el resultado es `None` en lugar de excepción.
- `test_session_es_idempotente_en_mismo_request` — verifica que dos accesos consecutivos a `self.session` dentro del mismo request Flask devuelven el mismo objeto.

---

## 7. Veredicto final

**Estado general del archivo:** Sólido. El código está bien estructurado, los patrones de batch loading son correctos, y los comentarios documentan los supuestos importantes. Los problemas son de grado, no de diseño fundamental.

**¿Bloquea crecimiento?** No directamente. El uso de threads en lugar de RQ es una deuda técnica que escala mal pero no impide añadir funcionalidad hoy.

**¿Bloquea testeo?** Parcialmente. El closure con `SessionLocal` dentro de `_ejecutar` requiere parchear el módulo `database` para testear el comportamiento del thread, lo que añade fricción a los tests.

**¿Tiene riesgo operativo real?** Sí, bajo-medio. El riesgo de thread storm ante picos de tráfico es real si el dashboard tiene uso intensivo simultáneo. El riesgo de fallo silencioso de batch queries es real en producción con SQL Server bajo carga.
