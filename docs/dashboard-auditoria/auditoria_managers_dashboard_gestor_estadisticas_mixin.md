# Auditoría de `managers/dashboard/gestor_estadisticas_mixin.py`

> Auditoría técnica estricta. Fecha: 2026-04-08.
> Archivos analizados: `managers/dashboard/gestor_estadisticas_mixin.py`, `managers/dashboard/_base.py`, `states.py`, `managers/gestor_dashboard.py`.

---

## 1. Rol del archivo

**Responsabilidad principal:** Mixin de analítica histórica. Provee un único método público `estadisticas()` que calcula KPIs de ventas y operaciones para un rango de fechas dado, con series temporales por día o semana.

**Qué debería hacer:** Cargar pedidos del rango, calcular KPIs agregados (ingresos, tasa de cancelación, tiempos medios), y construir series temporales para gráficas.

**Qué no debería hacer:** Decidir qué estados cuentan como "ingresos" ni cuáles van en la distribución (lógica de negocio), ni implementar lógica de agrupación temporal compleja dentro del propio manager.

**Dependencias clave:**
- `managers/dashboard/_base.py` — `GestorDashboardBase` (provee `self.session`).
- `models.py` — `Pedido`, `HistorialEstadoPedido`.
- `states.py` — `EstadoPedido`.

**Nivel de criticidad:** Medio — Alimenta el módulo de analítica histórica. Un error produce KPIs incorrectos en el dashboard de métricas, pero no bloquea el flujo operativo de pedidos.

---

## 2. Lo que hace bien

- **Una sola query principal** (líneas 41-52): carga todos los pedidos del rango en memoria con `load_only` sobre columnas mínimas (`PedidoID`, `Estado`, `Total`, `FechaCreacion`, `forma_pago`), evitando N+1 y cargando solo lo necesario.
- **Segunda query de historial en lote** (líneas 71-83): recupera todos los `HistorialEstadoPedido` relevantes en una sola query con `IN` sobre los `pedido_ids`, no query por pedido.
- **Cálculo de tiempos en Python** (líneas 84-112): el procesamiento del historial en Python evita un self-join SQL potencialmente costoso para rangos pequeños-medianos.
- **Granularidad extensible** (líneas 34-35): fallback a `'dia'` si se recibe un valor desconocido, sin excepción.
- **`_gen_keys` / `_dias_in_key` como closures** (líneas 145-173): limpian la generación de series y la hacen fácil de seguir.
- **Respeta el contrato de retorno documentado** (líneas 21-28): el docstring especifica exactamente las claves del dict devuelto.
- **Tasa de cancelación con `None` cuando no hay datos** (línea 62): correcto, evita división por cero y distingue "no hay pedidos" de "0% cancelación".

---

## 3. Hallazgos

### Hallazgo 1

**Tipo:** rendimiento
**Severidad:** Alta

**Problema:** Para rangos amplios (por ejemplo, un mes con 1.000 pedidos), el método carga **todos los pedidos en memoria** como objetos ORM y luego procesa KPIs en Python (líneas 55-142). El cálculo de distribución de estados (líneas 123-126), forma de pago (líneas 130-132) y series por día (líneas 136-142) se hace con bucles Python sobre la lista completa. Para el rango por defecto de 7 días con volumen bajo esto es aceptable, pero no escala.

**Evidencia:**
```python
# líneas 55-60
total_pedidos = len(pedidos)
entregados   = [p for p in pedidos if p.Estado == EstadoPedido.ENTREGADO.value]
cancelados   = [p for p in pedidos if p.Estado in (...)]
ingresos     = sum(float(p.Total or 0) for p in entregados)
```
Tres pases completos sobre la lista en Python para calcular KPIs que un `GROUP BY` resolvería en una sola query.

**Impacto real:** Con 5.000 pedidos en el rango (un mes de operación a volumen medio), se cargan todos en memoria y se iteran múltiples veces. En SQL Server con un pool de conexiones pequeño, mantener el cursor abierto más tiempo del necesario puede bloquear otras operaciones.

**Recomendación mínima concreta:** Para el volumen actual (restaurante pequeño, máx. ~100 pedidos/día), aceptable. Añadir un comentario explícito con el límite estimado de escala (`# ~500 pedidos/día max sin GROUP BY en DB`). Si el negocio crece, migrar KPIs básicos (count, sum) a `GROUP BY` SQL y mantener solo el cálculo de tiempos en Python.

---

### Hallazgo 2

**Tipo:** rendimiento
**Severidad:** Media

**Problema:** `_dias_in_key(key)` (líneas 160-173) itera sobre todo el rango de fechas **por cada clave generada**. Si el rango es `desde=2025-01-01` hasta `hasta=2025-12-31` (365 días) con granularidad `semana` (52 semanas), se hacen 52 × 365 = 18.980 iteraciones de `timedelta` en Python para construir las series.

**Evidencia:**
```python
# líneas 175-184
for key in _gen_keys():          # itera N keys
    dias = _dias_in_key(key)     # itera sobre todo el rango por cada key
    p_total = sum(...)
```

**Impacto real:** Para rangos de hasta 90 días (uso típico del dashboard de analítica), el impacto es imperceptible (<1ms). Para rangos anuales, la función se vuelve O(n²) en el número de días.

**Recomendación mínima concreta:** Precalcular el mapeo `day_iso → week_key` en un dict antes del bucle. Esto reduce la complejidad de O(n²) a O(n):
```python
day_to_key = {}
d = fecha_desde
while d <= fecha_hasta:
    if granularidad == 'semana':
        iso = d.isocalendar()
        day_to_key[d.isoformat()] = f"{iso[0]}-W{iso[1]:02d}"
    else:
        day_to_key[d.isoformat()] = d.isoformat()
    d += timedelta(days=1)
```

---

### Hallazgo 3

**Tipo:** validación de inputs / errores
**Severidad:** Media

**Problema:** Las fechas `desde` y `hasta` se parsean sin try/except (líneas 31-32). Si se pasa un string con formato incorrecto, el método lanza un `ValueError` sin capturar que sube sin contexto hasta el blueprint.

**Evidencia:**
```python
# líneas 31-32
fecha_desde = datetime.strptime(desde, '%Y-%m-%d').date() if desde else hoy - timedelta(days=6)
fecha_hasta = datetime.strptime(hasta, '%Y-%m-%d').date() if hasta else hoy
```

**Impacto real:** Un request malformado (o un bug en el blueprint que pasa la fecha en formato incorrecto) provoca una excepción no controlada. El blueprint recibe un 500 sin mensaje útil. Si Sentry no está configurado, el error desaparece.

**Recomendación mínima concreta:**
```python
try:
    fecha_desde = datetime.strptime(desde, '%Y-%m-%d').date() if desde else hoy - timedelta(days=6)
    fecha_hasta = datetime.strptime(hasta, '%Y-%m-%d').date() if hasta else hoy
except ValueError as exc:
    logger.warning("estadisticas: fecha inválida — %s", exc)
    fecha_desde = hoy - timedelta(days=6)
    fecha_hasta = hoy
```
Alternativamente, validar en el schema Pydantic antes de llegar al manager.

---

### Hallazgo 4

**Tipo:** diseño (lógica de negocio en capa de datos)
**Severidad:** Media

**Problema:** El método define internamente qué estados son "ingresos" (solo `ENTREGADO`, línea 60), qué estados van en la distribución (líneas 118-122), y cuáles se contabilizan como "cancelados" (línea 57-59). Estas son reglas de negocio, no decisiones de acceso a datos.

**Evidencia:**
```python
# líneas 56-60
entregados = [p for p in pedidos if p.Estado == EstadoPedido.ENTREGADO.value]
cancelados = [p for p in pedidos if p.Estado in (
    EstadoPedido.CANCELADO.value, EstadoPedido.REEMBOLSADO.value
)]
ingresos   = sum(float(p.Total or 0) for p in entregados)
```

**Impacto real:** Si la política cambia (por ejemplo, incluir `REEMBOLSADO` en ingresos para mostrar el flujo bruto antes de devoluciones), hay que modificar el manager. Riesgo bajo hoy, pero es una deuda de diseño que crece con el producto.

**Recomendación mínima concreta:** Documentar explícitamente en el docstring qué reglas de negocio están embebidas. No mover todavía — el coste de extracción supera el beneficio en este punto del proyecto.

---

### Hallazgo 5

**Tipo:** observabilidad
**Severidad:** Baja

**Problema:** El archivo no importa `logging` y no tiene ningún `logger.*`. No hay logging de módulo. Si la query falla, la segunda query de historial falla o el procesamiento de tiempos produce resultados inesperados, no hay trazabilidad.

**Evidencia:** Ausencia de `import logging` y `logger = logging.getLogger(__name__)` en el archivo (líneas 1-9).

**Impacto real:** En un error de producción, el stack trace indicará la línea que falló, pero no habrá contexto del rango de fechas ni de los parámetros recibidos. Dificulta el diagnóstico remoto.

**Recomendación mínima concreta:** Añadir al inicio del método:
```python
logger.debug("estadisticas: desde=%s hasta=%s granularidad=%s", desde, hasta, granularidad)
```
Y al inicio del archivo:
```python
import logging
logger = logging.getLogger(__name__)
```

---

### Hallazgo 6

**Tipo:** consistencia / correctitud
**Severidad:** Baja

**Problema:** El cálculo de tiempos de preparación usa `ts.setdefault(h.estado_nuevo, h.cambiado_en)` (línea 87), que toma el **primer** registro de cada estado. Esto es correcto bajo la máquina de estados actual (no hay re-entrada). Sin embargo, no hay validación de que `h.cambiado_en` sea no-None antes de usarlo en resta (línea 96).

**Evidencia:**
```python
# línea 96
mins = (ts[PREP] - ts[EN_PREP]).total_seconds() / 60
```
Si `cambiado_en` es `None` en algún registro histórico (por ejemplo, datos migrados con timestamps nulos), esta línea lanza `TypeError`.

**Impacto real:** Un único registro de historial con `cambiado_en=None` hace que `estadisticas()` lanze una excepción no controlada para cualquier rango que incluya ese pedido.

**Recomendación mínima concreta:**
```python
if EN_PREP in ts and PREP in ts and ts[EN_PREP] and ts[PREP]:
    mins = (ts[PREP] - ts[EN_PREP]).total_seconds() / 60
    if mins >= 0:
        ...
```

---

### Hallazgo 7

**Tipo:** testabilidad
**Severidad:** Baja

**Problema:** `_gen_keys` y `_dias_in_key` están definidas como closures anidados dentro de `estadisticas()` (líneas 145-173). No pueden ser testeadas de forma independiente sin llamar a `estadisticas()` completo con mocks de DB. Esto hace que un bug en la generación de series temporales solo pueda detectarse integracionalmente.

**Evidencia:**
```python
# líneas 145-158
def _gen_keys():
    ...
def _dias_in_key(key: str):
    ...
```

**Impacto real:** Tests de la lógica de agrupación por semana o por día requieren levantar un mock de DB completo, cuando deberían ser tests unitarios puros de 2-3 líneas.

**Recomendación mínima concreta:** Extraer `_gen_keys` y `_dias_in_key` como funciones de módulo privadas (con prefijo `_`) en `_helpers.py` o al nivel de módulo de este archivo. Esto no cambia el comportamiento pero hace que sean testeables directamente.

---

## 4. Riesgos principales si no se toca

| Riesgo | Escenario concreto |
|--------|-------------------|
| ValueError no capturado en parseo de fechas | El blueprint de analítica pasa `desde` como timestamp Unix; el manager lanza `ValueError`; el dashboard de analítica devuelve 500 para todos los usuarios. |
| TypeError con `cambiado_en=None` | Una migración de datos deja registros de historial con timestamp nulo; `estadisticas()` falla para cualquier rango que incluya esos pedidos; el dashboard de analítica queda inaccesible. |
| Escalado de memoria | Un gerente solicita estadísticas del año completo; se cargan 36.500 objetos ORM en memoria; la instancia Flask agota el heap y el servidor reinicia. |
| O(n²) en series semanales | Rango de 365 días con granularidad semana: 18.980 iteraciones de timedelta; latencia perceptible en la respuesta (~50-100ms extra). |

---

## 5. Refactor mínimo recomendado

### Qué tocar primero (en orden de impacto)
1. **Añadir guard de `None` en resta de tiempos** (Hallazgo 6) — 1 línea de cambio, previene excepción en producción con datos legacy.
2. **Añadir try/except en parseo de fechas con logging** (Hallazgo 3) — 5 líneas, previene 500 por input malformado.
3. **Añadir `import logging`** (Hallazgo 5) — 2 líneas, cero riesgo.
4. **Precalcular `day_to_key` dict** (Hallazgo 2) — 8 líneas, elimina O(n²).

### Qué NO tocar todavía
- La arquitectura de cálculo en Python vs GROUP BY (Hallazgo 1): el volumen actual no lo justifica. Documentar el umbral estimado y revisar cuando los pedidos/día superen 200.
- La extracción de reglas de negocio (Hallazgo 4): deuda de diseño aceptable en este punto.
- La extracción de closures (Hallazgo 7): mejora de testabilidad, no urgente.

---

## 6. Tests que deberían existir

- `test_estadisticas_rango_por_defecto` — sin argumentos devuelve los últimos 7 días con estructura correcta.
- `test_estadisticas_sin_pedidos_en_rango` — KPIs todos en 0/None, series con 0 pedidos por día, sin excepción.
- `test_estadisticas_fecha_invalida_no_lanza` — `desde='bad'` no lanza excepción; usa el rango por defecto.
- `test_estadisticas_granularidad_invalida_fallback_a_dia` — `granularidad='hora'` fallback silencioso a `'dia'`.
- `test_estadisticas_tiempos_con_cambiado_en_none` — historial con `cambiado_en=None` no lanza excepción; el pedido se excluye del cálculo de tiempos.
- `test_estadisticas_kpis_ingresos_solo_entregados` — verifica que `CANCELADO` no suma a ingresos.
- `test_estadisticas_tasa_cancelacion_cero_sin_pedidos` — `tasa_cancelacion_pct` es `None` cuando `total_pedidos=0`.
- `test_estadisticas_serie_semanal_agrupacion` — pedidos de la misma semana ISO aparecen en la misma clave `YYYY-WNN`.
- `test_estadisticas_forma_pago_desconocida_no_rompe` — un pedido con `forma_pago='bizum'` no lanza KeyError.
- `test_gen_keys_dia_genera_todos_los_dias` — (tras extraer el closure) verifica que genera exactamente `(hasta - desde).days + 1` claves.

---

## 7. Veredicto final

**Estado general del archivo:** Funcional y razonablemente bien estructurado para el volumen actual. La optimización de queries (una carga en lote + historial en lote) es correcta. Los hallazgos son riesgos de robustez (parseo sin try/except, `cambiado_en` nullable) y de escala (O(n²) en series, carga en memoria).

**¿Bloquea crecimiento?** Sí, en dos puntos concretos: el cálculo en Python sobre todos los pedidos en memoria no escala más allá de ~10k pedidos por rango, y el O(n²) en series semanales se hace perceptible a partir de rangos de 6+ meses.

**¿Bloquea testeo?** Parcialmente. Los closures anidados no son testeables directamente. La ausencia de try/except en parseo de fechas hace que los tests de input inválido deban mockar el comportamiento del método completo.

**¿Tiene riesgo operativo real?** Sí, moderado. El hallazgo 6 (`cambiado_en=None`) puede tirar el dashboard de analítica si existe un solo registro histórico corrupto. El hallazgo 3 (fechas sin try/except) puede producir un 500 consistente si hay un bug en el blueprint caller.
