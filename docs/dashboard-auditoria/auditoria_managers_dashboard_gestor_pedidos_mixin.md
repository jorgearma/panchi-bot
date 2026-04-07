# Auditoría de `managers/dashboard/gestor_pedidos_mixin.py`

> Auditoría técnica estricta. Fecha: 2026-04-08.
> Archivos analizados: `managers/dashboard/gestor_pedidos_mixin.py`, `managers/dashboard/_helpers.py`, `managers/dashboard/_base.py`, `states.py`, `managers/gestor_dashboard.py`.

---

## 1. Rol del archivo

**Responsabilidad principal:** Mixin de acceso a datos para el panel operativo. Expone consultas de lectura (pedidos activos, métricas diarias, alertas, historial paginado, detalle de pedido) y serializa los resultados a dicts planos listos para el blueprint.

**Qué debería hacer:** Emitir queries a la DB, serializar ORM objects a dicts, aplicar filtros básicos de fechas y estado.

**Qué no debería hacer:** Interpretar lógica de negocio (clasificar alertas, definir umbrales de retraso, construir mensajes de error humanos), tomar decisiones basadas en estado (qué constituye un "retraso"), ni importar módulos de nivel superior de forma diferida dentro de métodos.

**Dependencias clave:**
- `managers/dashboard/_helpers.py` — constantes `_ESTADOS_OPERATIVOS`, `_UMBRALES_RETRASO`, `_COLORES_ESTADO`, helper `_iso`.
- `managers/dashboard/_base.py` — `GestorDashboardBase` (provee `self.session` y `_tiempo_medio`).
- `models.py` — `Pedido`, `PedidoDetalle`, `PickingPedido`, `Reparto`, `Producto`, `HistorialEstadoPedido`.
- `states.py` — `EstadoPedido`, `EstadoPicking`, `EstadoReparto`.

**Nivel de criticidad:** Alto — Es el núcleo del panel operativo. Un bug aquí afecta todas las vistas del dashboard en tiempo real.

---

## 2. Lo que hace bien

- **Carga eager consistente** (líneas 116-124): usa `joinedload` y `selectinload` correctamente, evitando N+1 en `pedidos_activos`.
- **GROUP BY en métricas** (líneas 33-38): un solo `GROUP BY` reemplaza tres queries de estado separadas, optimización explícita y documentada.
- **Paginación con límite forzado** (línea 301): `per_page = min(per_page, 100)` previene que el caller sature la DB.
- **Escape de LIKE** (líneas 333-336): escapa `%` y `_` antes de usarlos en `ilike`, protegiendo contra inyección SQL via LIKE wildcards.
- **`load_only` en alertas** (líneas 206-210): carga solo las columnas necesarias para la evaluación de umbrales.
- **Serializacion defensiva** (ej. línea 175): `float(p.Total) if p.Total else 0.0` en lugar de asumir no-null.
- **`_UMBRALES_RETRASO` centralizado** en `_helpers.py`: umbrales no están dispersos en el mixin.
- **Ordenación de alertas por severidad** (líneas 256-257): la lista devuelta ya viene ordenada, lo que simplifica el frontend.

---

## 3. Hallazgos

### Hallazgo 1

**Tipo:** diseño
**Severidad:** Media

**Problema:** `historial_pedidos` contiene un import diferido de `math.ceil`, `sqlalchemy.or_` y `models.Usuario` dentro del cuerpo del método (líneas 291-293). Esto oculta dependencias, hace que el IDE no pueda resolverlas en el contexto del módulo y dificulta el mocking en tests.

**Evidencia:**
```python
# líneas 291-293
from math import ceil
from sqlalchemy import or_
from models import Usuario
```

**Impacto real:** Bajo en runtime (Python cachea imports), pero rompe la convención del resto del mixin (todos los demás imports están al nivel del módulo) y complica el análisis estático.

**Recomendación mínima concreta:** Mover los tres imports al bloque de imports del módulo (parte superior del archivo). `math.ceil` y `sqlalchemy.or_` ya están disponibles en el contexto global; `Usuario` debería importarse junto a los demás modelos en la línea 12.

---

### Hallazgo 2

**Tipo:** diseño / observabilidad
**Severidad:** Media

**Problema:** `historial_pedidos` silencia errores de parseo de fechas (líneas 307-311 y 313-317) con un `pass` vacío, sin logging. Si un caller pasa `desde='not-a-date'`, el filtro simplemente se ignora y la query devuelve datos sin rango, sin ninguna señal de que algo fue incorrecto.

**Evidencia:**
```python
# líneas 307-311
try:
    dt_desde = datetime.strptime(desde, '%Y-%m-%d')
    query = query.filter(Pedido.FechaCreacion >= dt_desde)
except ValueError:
    pass  # silencioso
```

**Impacto real:** Un bug en el caller (por ejemplo, el blueprint pasa la fecha en formato europeo `DD/MM/YYYY`) provoca que la query devuelva todo el historial sin filtro de fecha, potencialmente retornando miles de pedidos. No hay trazabilidad.

**Recomendación mínima concreta:**
```python
except ValueError:
    logger.warning("historial_pedidos: formato de fecha inválido '%s', ignorado", desde)
```
O mejor aún: validar el formato antes de la query y retornar un error estructurado al caller.

---

### Hallazgo 3

**Tipo:** rendimiento
**Severidad:** Media

**Problema:** `historial_pedidos` ejecuta `query.count()` (línea 341) y luego `query.all()` (líneas 344-351) como dos roundtrips separados a la DB sobre la misma query. En SQL Server esto es especialmente costoso porque implica dos planes de ejecución.

**Evidencia:**
```python
# líneas 341-350
total = query.count()          # roundtrip 1
# ...
pedidos = (
    query
    .options(joinedload(Pedido.cliente))
    .order_by(...)
    .offset(...)
    .limit(per_page)
    .all()                     # roundtrip 2
)
```

**Impacto real:** Con un historial grande (miles de pedidos) y filtros amplios, cada llamada al historial cuesta dos queries completas. Bajo carga concurrente esto se multiplica.

**Recomendación mínima concreta:** Usar `SELECT COUNT(*) OVER()` via `func.count().over()` en una subquery, o aceptar el doble roundtrip pero añadir un índice compuesto en `(Estado, FechaCreacion)` para que ambas queries sean cubiertas. En el contexto actual, el doble roundtrip es aceptable si existe ese índice.

---

### Hallazgo 4

**Tipo:** diseño (lógica de negocio en capa de datos)
**Severidad:** Baja

**Problema:** `alertas` (líneas 198-258) contiene lógica de negocio operativa: decide qué constituye una alerta, qué nivel asignarle, construye mensajes en español para el usuario final, y ordena por severidad. Según la arquitectura del proyecto, esto debería estar en `controllers/`, no en `managers/`.

**Evidencia:**
```python
# línea 222-226
resultado.append({
    "tipo": "pedido_retrasado",
    "nivel": nivel,
    "mensaje": f"Pedido #{p.PedidoID} lleva {int(minutos)}min {desc}",
    ...
})
# línea 250-254
resultado.append({
    "tipo": "stock_bajo",
    "nivel": "info" if prod.Stock > 0 else "warning",
    ...
})
```

**Impacto real:** El mixin toma decisiones de presentación (`nivel`, texto del `mensaje`). Si se cambia el idioma, el umbral o la política de alertas, hay que modificar el manager, no el controller. Además mezcla tres dominios distintos (pedidos, repartos, stock) en un solo método.

**Recomendación mínima concreta:** Mantener como está en el corto plazo (el coste de mover supera el beneficio ahora), pero documentar explícitamente en el docstring que esta función contiene reglas de negocio y que los umbrales se definen en `_helpers.py`. Si el sistema crece, extraer a `controllers/alertas.py`.

---

### Hallazgo 5

**Tipo:** rendimiento
**Severidad:** Baja

**Problema:** `metricas` (líneas 23-105) ejecuta **6 queries separadas** de forma secuencial, más 2 llamadas a `_tiempo_medio` (otras 2 queries). Son 8 roundtrips a la DB por cada carga del dashboard. No hay caché.

**Evidencia:** Líneas 28-30, 33-38, 44-47, 49-51, 53-55, 57-60, 63-71, 75-83, y las llamadas a `_tiempo_medio` en líneas 96-101.

**Impacto real:** Bajo uso actual (una sola instancia, pocas peticiones concurrentes), el impacto es tolerable. Con polling del dashboard cada 5-10 segundos desde múltiples pestañas, puede saturar el pool de conexiones.

**Recomendación mínima concreta:** Añadir caché Redis de 30 segundos sobre el resultado completo de `metricas()`, similar a lo que hace `gestor_metricas.py`. No es urgente pero sí necesario antes de escalar a múltiples operadores simultáneos.

---

### Hallazgo 6

**Tipo:** observabilidad
**Severidad:** Baja

**Problema:** Ningún método del mixin tiene logging de errores. Si una query falla (timeout de SQL Server, error de conexión), la excepción sube sin contexto adicional. `_tiempo_medio` en `_base.py` tampoco hace logging.

**Evidencia:** No hay ningún bloque `try/except` ni `logger.*` en todo el archivo (líneas 1-457).

**Impacto real:** En producción, un error de DB en `pedidos_activos()` o `metricas()` aparecerá en Sentry (si está configurado) pero sin el contexto del método, los filtros aplicados ni los IDs involucrados.

**Recomendación mínima concreta:** No añadir try/except genéricos que oculten errores, pero sí añadir `logger.debug` al inicio de los métodos más críticos (`metricas`, `pedidos_activos`, `alertas`) con los parámetros recibidos, para facilitar diagnóstico.

---

### Hallazgo 7

**Tipo:** validación de inputs
**Severidad:** Baja

**Problema:** `pedidos_activos(estado: str)` (línea 107) acepta el parámetro `estado` sin validarlo contra los valores del enum `EstadoPedido`. Un estado inválido simplemente devuelve una lista vacía, sin error ni log.

**Evidencia:**
```python
# líneas 113-114
if estado:
    query = query.filter(Pedido.Estado == estado)
```

**Impacto real:** El caller puede pasar cualquier string (incluso por error tipográfico) y recibir silenciosamente una lista vacía, creyendo que no hay pedidos en ese estado. No hay riesgo de seguridad (es un filtro de igualdad, no concatenación) pero sí de confusión operativa.

**Recomendación mínima concreta:**
```python
if estado:
    if estado not in [e.value for e in EstadoPedido]:
        logger.warning("pedidos_activos: estado desconocido '%s'", estado)
    query = query.filter(Pedido.Estado == estado)
```

---

## 4. Riesgos principales si no se toca

| Riesgo | Escenario concreto |
|--------|-------------------|
| Historial sin rango de fecha | Un blueprint pasa `desde` en formato incorrecto; la query ignora el filtro y devuelve todo el historial; el dashboard se cuelga o expone datos no esperados. |
| Sin caché en métricas | El dashboard se recarga cada 10s desde 5 pestañas simultáneas; 8 queries × 5 × 6/min = 240 queries/min sostenidas contra SQL Server. |
| Alertas mezcla dominios | Cambio en política de stock mínimo requiere tocar `managers/`, violando la separación de capas y arriesgando regressions en lógica de pedidos. |
| Imports diferidos en `historial_pedidos` | Un refactor que mueva `Usuario` a otro módulo no es detectado por el linter hasta que se llama al método en runtime. |

---

## 5. Refactor mínimo recomendado

### Qué tocar primero (en orden de impacto)
1. **Mover imports diferidos al top del archivo** (Hallazgo 1) — cambio de 3 líneas, riesgo cero.
2. **Añadir `logger.warning` en bloques `except ValueError`** (Hallazgo 2) — una línea por bloque.
3. **Añadir `logger.warning` en `pedidos_activos` para estado inválido** (Hallazgo 7) — dos líneas.

### Qué NO tocar todavía
- La lógica de alertas (Hallazgo 4): extraerla a controllers requeriría cambios en el blueprint y en los tests. El beneficio no compensa el riesgo ahora.
- La caché de métricas (Hallazgo 5): necesita coordinación con `container.py` y Redis. Hacer por separado con un task dedicado.
- El doble roundtrip en paginación (Hallazgo 3): aceptable hasta que el historial supere los 50k registros.

---

## 6. Tests que deberían existir

- `test_metricas_devuelve_estructura_completa` — verifica que todas las claves del dict están presentes con tipos correctos.
- `test_metricas_sin_pedidos_hoy` — verifica que los valores son 0 / Decimal("0.00") cuando no hay datos, no None ni error.
- `test_pedidos_activos_filtro_estado_invalido` — verifica que un estado desconocido devuelve lista vacía sin excepción.
- `test_historial_fecha_invalida_ignorada` — verifica que `desde='bad-date'` no lanza excepción y devuelve resultados.
- `test_historial_paginacion_limite_forzado` — verifica que `per_page=500` queda truncado a 100.
- `test_alertas_pedido_retrasado` — verifica que un pedido con `FechaActualizacion` > umbral aparece con nivel correcto.
- `test_alertas_sin_repartidor` — verifica la alerta `sin_repartidor` cuando `Reparto.repartidor_id` es None.
- `test_alertas_stock_bajo` — verifica alerta con `nivel=info` para stock > 0 y `nivel=warning` para stock = 0.
- `test_detalle_pedido_no_existente` — verifica que retorna `None`, no excepción.
- `test_alertas_ordenadas_por_severidad` — verifica que `error` precede a `warning`, que precede a `info`.

---

## 7. Veredicto final

**Estado general del archivo:** Sólido. El código está bien estructurado, las queries están optimizadas respecto a versiones anteriores (evidenciado por los comentarios inline), y las abstracciones están en el lugar correcto. Los hallazgos son mejoras de calidad, no bugs activos.

**¿Bloquea crecimiento?** No activamente, pero la ausencia de caché en `metricas()` lo hará si el número de operadores del dashboard crece por encima de 3-4 simultáneos con polling activo.

**¿Bloquea testeo?** Levemente. Los imports diferidos en `historial_pedidos` y la ausencia de logging en bloques `except` hacen que los tests deban cubrir casos edge de forma más exhaustiva para detectar errores silenciosos.

**¿Tiene riesgo operativo real?** Bajo. El único riesgo operativo concreto es el filtro de fechas ignorado silenciosamente en `historial_pedidos` (Hallazgo 2), que podría confundir a un operador que crea que está viendo datos filtrados cuando no lo está.
