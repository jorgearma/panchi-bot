# Auditoría de `managers/dashboard/empleados_rendimiento.py`

> Auditoría técnica estricta. Fecha: 2026-04-08.
> Archivos analizados: `managers/dashboard/empleados_rendimiento.py`, `managers/dashboard/_helpers.py`, `models.py` (clases `Empleado`, `PickingPedido`, `Reparto`, `CheckIn`, `MetricaDiariaEmpleado`).

---

## 1. Rol del archivo

**Responsabilidad principal:** Calcular y devolver métricas de rendimiento de empleados (ranking de equipo y detalle individual) consultando directamente `PickingPedido` y `Reparto`, sin usar la caché `MetricaDiariaEmpleado`.

**Qué debería hacer:** Leer datos operativos del período solicitado, agregar KPIs en memoria y devolver estructuras serializables listas para el dashboard o una API.

**Qué no debería hacer:** Contener imports lazy dentro de funciones de producción, mezclar la lógica de agregación de pickings y repartos con la lógica de presentación, duplicar cálculos ya implementados en `_helpers.py`.

**Dependencias clave:** `models.Empleado`, `models.PickingPedido`, `models.Reparto`, `models.CheckIn` (import lazy), `managers/dashboard/_helpers._iso`, `self.session`.

**Nivel de criticidad:** Medio — alimenta el panel de rendimiento del dashboard y el ranking de equipo. Un cálculo incorrecto de KPIs produce decisiones de gestión equivocadas, pero no afecta el flujo transaccional de pedidos.

---

## 2. Lo que hace bien

- **Dos funciones bien delimitadas** (líneas 13 y 115): `rendimiento_resumen` para el equipo y `rendimiento_empleado` para el detalle individual. Responsabilidades claramente separadas.
- **Reutilización de `_iso`** (líneas 228, 263, 264, 270): serialización UTC correcta importada del módulo compartido; no reinventa el formato de fecha.
- **Batch-load de empleados** (líneas 87–91): la query de empleados usa `IN` sobre los IDs acumulados en `agg`, evitando N+1 en `rendimiento_resumen`.
- **Fallback de nombre** (línea 103): `f'#{emp_id}'` cuando el empleado ya no existe en DB, sin lanzar excepción.
- **Documentación de retorno explícita** (líneas 24–26 y 122–131): el docstring detalla la estructura exacta del dict devuelto, útil para los consumidores.
- **No depende de `MetricaDiariaEmpleado`**: la nota en el docstring (líneas 17–19) documenta la decisión de diseño de consultar directamente las tablas operativas.
- **Cálculo de `tasa_pct` protegido** (línea 98): guarda de división por cero correcta con `if (pedidos + incidencias) > 0`.

---

## 3. Hallazgos

### Hallazgo 1

**Tipo:** diseño  
**Severidad:** Media

**Problema:** `rendimiento_empleado` tiene un import lazy de `CheckIn` dentro de la función (línea 133). El resto de modelos se importan al nivel de módulo (línea 6). Los imports lazy dentro de funciones ocultan dependencias, dificultan el análisis estático, complican el mocking en tests y son un antipatrón documentado en el proyecto (la consistencia es clave cuando el mixin se compone con otros).

**Evidencia:**
```python
# línea 6 — imports a nivel de módulo
from models import Empleado, PickingPedido, Reparto

# línea 133 — import lazy dentro de la función
def rendimiento_empleado(self, empleado_id: int, periodo: str = 'semana') -> dict | None:
    from models import CheckIn
```

**Impacto real:** Si `models.CheckIn` cambia de nombre o de módulo, el error solo se detecta en tiempo de ejecución al llamar a `rendimiento_empleado`, no al importar el mixin. En tests, hay que parchear `managers.dashboard.empleados_rendimiento.CheckIn` de forma diferente al resto de modelos.

**Recomendación mínima concreta:** Mover `from models import CheckIn` a la línea 6, junto con el resto de imports del módulo. Cambio de 2 líneas, sin efecto funcional.

---

### Hallazgo 2

**Tipo:** rendimiento  
**Severidad:** Media

**Problema:** `rendimiento_empleado` ejecuta **5 queries independientes** sobre la misma DB para construir la respuesta (líneas 136, 151, 160, 212, 232–253). Las dos últimas (líneas 232–253) repiten exactamente el mismo filtro que las queries de KPI (líneas 151–168) pero con `LIMIT 10` y sin el estado `con_incidencias`/`no_entregado`. Esto significa que `PickingPedido` y `Reparto` se leen **dos veces** por invocación.

**Evidencia:**
```python
# Primera lectura de PickingPedido (líneas 151-159) — para KPIs
pickings_periodo = s.query(PickingPedido).filter(
    PickingPedido.empleado_id == empleado_id,
    PickingPedido.estado.in_(['completado', 'con_incidencias']),
    PickingPedido.completado_en >= desde_dt,
).all()

# Segunda lectura de PickingPedido (líneas 232-242) — para ultimos_pedidos
pickings = s.query(PickingPedido).filter(
    PickingPedido.empleado_id == empleado_id,
    PickingPedido.estado == 'completado',
    PickingPedido.completado_en >= desde_dt,
).order_by(...).limit(10).all()
```

El mismo patrón se repite para `Reparto` (líneas 160–168 vs. 243–253).

**Impacto real:** 4 queries en lugar de 2 por cada llamada a `rendimiento_empleado`. Con SQL Server y latencia de red, esto duplica el tiempo de respuesta del endpoint. Si el período es `'mes'`, cada query puede retornar cientos de filas.

**Recomendación mínima concreta:** Reutilizar los resultados ya cargados en `pickings_periodo` y `repartos_periodo` para construir `ultimos_pedidos`. Filtrar y ordenar en Python:
```python
ultimos_pick = sorted(
    [pk for pk in pickings_periodo if pk.estado == 'completado' and pk.completado_en],
    key=lambda pk: pk.completado_en, reverse=True
)[:10]
```
Eliminar las queries de las líneas 232–253.

---

### Hallazgo 3

**Tipo:** rendimiento  
**Severidad:** Baja

**Problema:** `rendimiento_resumen` carga todos los campos de `PickingPedido` y `Reparto` con `.all()` (líneas 42–49 y 65–72), cuando solo necesita `empleado_id`, `estado`, `iniciado_en`, `completado_en` / `repartidor_id`, `estado`, `hora_salida`, `hora_entrega_real`. Para períodos de un mes con muchos pedidos, se transfieren columnas innecesarias (`notas`, `created_at`, `prueba_entrega_url`, etc.).

**Evidencia:**
```python
# línea 42–49 — carga completa del ORM
pickings = (
    s.query(PickingPedido)
    .filter(...)
    .all()
)
```

**Impacto real:** Bajo con el volumen actual (restaurante pequeño en Tarancón). Si el volumen de pedidos crece, el impacto en memoria y transferencia de red con SQL Server aumenta proporcionalmente.

**Recomendación mínima concreta:** Usar `load_only` de SQLAlchemy cuando haya evidencia de lentitud:
```python
from sqlalchemy.orm import load_only
s.query(PickingPedido).options(
    load_only(PickingPedido.empleado_id, PickingPedido.estado,
              PickingPedido.iniciado_en, PickingPedido.completado_en)
).filter(...)
```
No es urgente; documentar como deuda técnica.

---

### Hallazgo 4

**Tipo:** consistencia  
**Severidad:** Baja

**Problema:** En `rendimiento_empleado`, cuando `periodo='mes'` (30 días), la sección `pedidos_por_dia` solo muestra los últimos 7 días (líneas 192–209), ignorando el período completo. La variable `desde_dt` del período general y `siete_dias_dt` se calculan de forma independiente (líneas 148 y 193). Los pickings y repartos del mes completo ya están cargados en memoria, pero la iteración para el gráfico diario filtra nuevamente por `siete_dias_dt`, descartando silenciosamente los días 8–30 del mes.

**Evidencia:**
```python
# línea 148 — desde_dt puede ser 30 días atrás
desde_dt = datetime(desde.year, desde.month, desde.day)

# línea 192-193 — siete_dias siempre son 7 días atrás, ignora 'mes'
siete_dias = hoy - timedelta(days=6)
siete_dias_dt = datetime(siete_dias.year, siete_dias.month, siete_dias.day)
```

**Impacto real:** El gráfico de `pedidos_por_dia` en el dashboard siempre muestra 7 días, independientemente del período seleccionado. Si el diseño del dashboard _intenta_ mostrar 30 días cuando `periodo='mes'`, hay un bug silencioso. Si el diseño siempre muestra 7 días, el comportamiento es correcto pero la variable `desde_dt` carga datos innecesarios del mes completo para calcular KPIs.

**Recomendación mínima concreta:** Documentar explícitamente en el docstring que `pedidos_por_dia` siempre cubre los últimos 7 días independientemente del período. Si en el futuro se quieren 30 días, el bucle de línea 204 debe ajustarse a `range(periodo_dias)`.

---

### Hallazgo 5

**Tipo:** validación de inputs  
**Severidad:** Baja

**Problema:** El parámetro `periodo` acepta cualquier string. Un valor desconocido (ej. `'trimestre'`) cae silenciosamente en el `else` de la línea 33/144, que lo trata como `'hoy'`, devolviendo datos de un solo día sin advertencia.

**Evidencia:**
```python
# líneas 28-33
if periodo == 'semana':
    desde = hoy - timedelta(days=6)
elif periodo == 'mes':
    desde = hoy - timedelta(days=29)
else:
    desde = hoy   # cualquier valor desconocido → 'hoy'
```

**Impacto real:** Un blueprint que pase `periodo='week'` (en inglés por error) obtiene datos de solo 1 día sin ninguna indicación de que algo está mal.

**Recomendación mínima concreta:**
```python
_PERIODOS_VALIDOS = {'hoy', 'semana', 'mes'}
if periodo not in _PERIODOS_VALIDOS:
    logger.warning("rendimiento_resumen: periodo desconocido '%s', usando 'hoy'", periodo)
```

---

### Hallazgo 6

**Tipo:** observabilidad  
**Severidad:** Baja

**Problema:** El logger se importa (línea 8) pero no se usa en ningún punto del archivo. No hay trazas cuando el empleado no existe en `rendimiento_empleado` (devuelve `None` en línea 137 silenciosamente), ni cuando el período no tiene datos (devuelve `{'empleados': []}` en `rendimiento_resumen`).

**Evidencia:**
```python
# línea 8 — importado sin uso
logger = logging.getLogger(__name__)

# línea 137 — None devuelto sin log
if not emp:
    return None
```

**Impacto real:** Si un controller llama a `rendimiento_empleado` con un ID incorrecto, obtiene `None` sin saber por qué. Un simple `logger.warning` permite rastrear el problema en logs.

**Recomendación mínima concreta:**
```python
if not emp:
    logger.warning("rendimiento_empleado: empleado_id=%d no encontrado", empleado_id)
    return None
```

---

### Hallazgo 7

**Tipo:** diseño  
**Severidad:** Baja

**Problema:** La lógica de cálculo de duración (tiempo en minutos entre dos timestamps) se duplica en múltiples puntos del archivo:
- Líneas 58–60: duración de picking en `rendimiento_resumen`
- Líneas 176–178: duración de picking en `rendimiento_empleado`
- Líneas 258–259: duración de picking en `ultimos_pedidos`
- Líneas 80–83, 183–185, 267–269: duplicados equivalentes para reparto

El módulo `_helpers.py` ya define `_dur_picking(pk)` y `_dur_reparto(r)` con exactamente esta lógica, pero `empleados_rendimiento.py` no las importa ni usa.

**Evidencia:**
```python
# _helpers.py líneas 8-19 — ya existe
def _dur_picking(pk) -> float | None:
    if pk.iniciado_en and pk.completado_en:
        return (pk.completado_en - pk.iniciado_en).total_seconds() / 60

# empleados_rendimiento.py línea 58-60 — duplicado
if pk.iniciado_en and pk.completado_en:
    agg[key]['tiempos'].append(
        (pk.completado_en - pk.iniciado_en).total_seconds() / 60
    )
```

**Impacto real:** Si se cambia la definición de "duración" (ej. usar `iniciado_en` desde el primer item asignado en lugar del PickingPedido), hay que actualizar múltiples puntos. La divergencia ya existe con `_helpers.py`.

**Recomendación mínima concreta:** Importar `_dur_picking` y `_dur_reparto` desde `._helpers` y reemplazar los bloques inline. La importación ya existe para `_iso`; añadir:
```python
from managers.dashboard._helpers import _iso, _dur_picking, _dur_reparto
```

---

## 4. Riesgos principales si no se toca

| Riesgo | Escenario concreto |
|--------|-------------------|
| Doble lectura de PickingPedido/Reparto (Hallazgo 2) | Con 500 pedidos en el mes, `rendimiento_empleado` ejecuta 4 queries pesadas en lugar de 2 por cada carga del panel de detalle. Si 10 supervisores abren el panel simultáneamente, son 40 queries cuando podrían ser 20. |
| Import lazy de CheckIn (Hallazgo 1) | En un test que mockea `models`, el parche de `CheckIn` se aplica en el módulo equivocado y la query real llega a la DB, causando un fallo críptico en CI. |
| Período desconocido silencioso (Hallazgo 5) | Un template pasa `periodo` desde un `<select>` HTML con valor incorrecto; el dashboard muestra datos de "hoy" creyendo que muestra "la semana", sin ningún error visible. |
| Divergencia de cálculo de duración (Hallazgo 7) | Se corrige `_dur_picking` en `_helpers.py` pero los cálculos inline de `empleados_rendimiento.py` quedan desactualizados; los KPIs del dashboard de rendimiento difieren de los de métricas, confundiendo a los supervisores. |

---

## 5. Refactor mínimo recomendado

### Qué tocar primero (en orden de impacto)

1. **Eliminar doble lectura de PickingPedido/Reparto** (Hallazgo 2): reutilizar `pickings_periodo` y `repartos_periodo` para construir `ultimos_pedidos`. Reducción directa de 2 queries por llamada.
2. **Mover import lazy de CheckIn al nivel de módulo** (Hallazgo 1): 2 líneas, previene bugs en tests.
3. **Usar `_dur_picking` y `_dur_reparto` de `_helpers`** (Hallazgo 7): elimina 6 bloques inline, centraliza la lógica de duración.
4. **Añadir warning para período inválido** (Hallazgo 5): 3 líneas.
5. **Añadir warning para empleado no encontrado** (Hallazgo 6): 1 línea.

### Qué NO tocar todavía

- `load_only` en las queries de `rendimiento_resumen` (Hallazgo 3): el impacto es despreciable con el volumen actual.
- La estructura del dict devuelto: cualquier cambio rompe los templates y tests existentes.
- La decisión de no usar `MetricaDiariaEmpleado`: es una decisión de diseño consciente documentada en el docstring.

---

## 6. Tests que deberían existir

- `test_rendimiento_resumen_hoy_solo_picker` — verifica que con `rol='picker'` solo se agregan PickingPedidos, sin Repartos.
- `test_rendimiento_resumen_hoy_solo_repartidor` — verifica que con `rol='repartidor'` solo se agregan Repartos.
- `test_rendimiento_resumen_sin_datos` — verifica que devuelve `{'empleados': []}` cuando no hay actividad en el período.
- `test_rendimiento_resumen_tasa_pct_cero_incidencias` — verifica `tasa_pct=100` cuando no hay incidencias.
- `test_rendimiento_resumen_tasa_pct_todos_incidencias` — verifica `tasa_pct=0` cuando todos son incidencias.
- `test_rendimiento_resumen_empleado_borrado` — verifica el fallback `f'#{emp_id}'` cuando el empleado no existe en DB.
- `test_rendimiento_empleado_no_existe` — verifica que devuelve `None` para un `empleado_id` inexistente.
- `test_rendimiento_empleado_kpis_picking` — verifica `pedidos`, `tiempo_medio_min`, `mejor_tiempo_min` e `incidencias` para un picker.
- `test_rendimiento_empleado_kpis_repartidor` — mismo para un repartidor.
- `test_rendimiento_empleado_pedidos_por_dia_siempre_7_dias` — verifica que `pedidos_por_dia` tiene siempre 7 entradas independientemente del período.
- `test_rendimiento_empleado_turnos_recientes_limit_5` — verifica que `turnos_recientes` devuelve máximo 5 entradas.
- `test_rendimiento_empleado_ultimos_pedidos_limit_10` — verifica que `ultimos_pedidos` devuelve máximo 10 entradas mezclando pickings y repartos.
- `test_periodo_invalido_usa_hoy` — verifica que un período desconocido devuelve datos de hoy (y emite warning).

---

## 7. Veredicto final

**Estado general del archivo:** Funcional y bien estructurado en sus responsabilidades de alto nivel. Los problemas identificados son deuda técnica acumulable, no bugs bloqueantes, con una excepción: la doble lectura de datos (Hallazgo 2) tiene impacto real en rendimiento si el tráfico crece.

**¿Bloquea crecimiento?** No directamente, pero el patrón de doble lectura y la duplicación de lógica de duración harán más costoso cualquier cambio en los KPIs de rendimiento.

**¿Bloquea testeo?** Parcialmente. El import lazy de `CheckIn` (Hallazgo 1) complica el mocking unitario y puede producir fallos crípticos en CI si no se parchea correctamente.

**¿Tiene riesgo operativo real?** Bajo. El mayor riesgo es la divergencia silenciosa de KPIs si `_helpers.py` se actualiza pero los cálculos inline de este archivo no (Hallazgo 7). En un panel de rendimiento que los supervisores usan para tomar decisiones de gestión de personal, datos inconsistentes entre secciones del dashboard erosionan la confianza en la herramienta.
