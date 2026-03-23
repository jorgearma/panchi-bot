# Backend de Métricas — Dashboard de Administrador

**Fecha:** 2026-03-22
**Estado:** Revisado v3
**Rama:** `migrar-bd`

---

## Objetivo

Construir la capa backend que expone los datos necesarios para dos paneles de administración:

1. **Panel del encargado** — operación en tiempo real: quién está, qué hay en cola, qué alertas hay ahora
2. **Panel del dueño** — analítica histórica: rendimiento, tendencias, comparativas entre empleados

No se construye frontend en este spec. No se implementa caché. El mecanismo de actualización del panel de operación es polling desde el cliente.

---

## Relación con GestorDashboard existente

`GestorDashboard` (~1700 líneas) contiene lógica operativa (asignar pickers, cambiar estados, marcar entregas) **y** algunos métodos de métricas básicas: `metricas()`, `alertas()`, `picking_activo()`, `repartidores()`, `monitor_empleados()`.

**Decisión de diseño:** los métodos de métricas existentes en `GestorDashboard` **no se tocan ni se eliminan**. `GestorMetricas` es un manager nuevo que añade métricas que no existen hoy. Si hay solapamiento parcial en lo que calculan, los nuevos blueprints de métricas usan `GestorMetricas` exclusivamente; el blueprint `dashboard.py` existente sigue usando `GestorDashboard` sin cambios.

Esto evita romper el dashboard operativo actual mientras se construye el de métricas.

---

## Arquitectura

```
blueprints/
  metricas_operacion.py    →  /metricas/operacion/...   (encargado, tiempo real)
  metricas_analitica.py    →  /metricas/analitica/...   (dueño, histórico)

managers/
  gestor_metricas.py       →  toda la lógica de cálculo, sin lógica operativa
```

Ambos blueprints se registran en `main.py` igual que el resto.

### Principios

- `GestorMetricas` es **solo lectura** — no modifica estados, no asigna nada.
- Sigue el patrón del proyecto: `self.session` como property que llama a `get_db()`. Nunca `db.session` global.
- Todos los endpoints devuelven `{"ok": true, "data": {...}}` igual que el resto del proyecto.
- Autenticación: `@requiere_rol('admin', 'manager')` en todos los endpoints de ambos blueprints.

---

## Definiciones operativas (evitar ambigüedad en implementación)

**"Empleado en turno"** = tiene un `CheckIn` con `fin IS NULL` y `fecha = hoy`. Es el criterio más fiable porque refleja presencia real, no planificación.

**"Cola de picking"** = `PickingPedido` con `estado = 'pendiente'` y `empleado_id IS NULL`.

**"Cola de reparto"** = `Reparto` con `estado = 'pendiente'` (sin repartidor asignado aún).

**"Tasa de entrega del día"** = `ENTREGADO_hoy / (ENTREGADO_hoy + NO_ENTREGADO_hoy)`. Solo sobre repartos cerrados del día, no sobre todos los pedidos creados.

**"Tiempo medio de ciclo"** = mediana de `timestamp(ENTREGADO) − timestamp(EN_PREPARACION)` usando `HistorialEstadoPedido`. Se usa mediana, no media, para resistir outliers.

**"Operación completada"** (base de productividad):
- Para pickers: `PickingPedido` con `estado = 'completado'`
- Para repartidores: `Reparto` con `estado = 'entregado'`

**"Incidencia"** en este contexto = exclusivamente `PickingItem.estado in ('sin_stock', 'sustituido')` para picking, y `Reparto.estado = 'no_entregado'` para reparto. El modelo `Incidencia` (tabla general) no se usa en este spec.

**Rango de fechas por defecto** = `[hoy - 6 días, hoy]`, es decir, los últimos 7 días incluyendo hoy. Los datos de hoy son parciales; el frontend debe indicarlo visualmente, pero no es responsabilidad del backend.

**"Puntual"** = `CheckIn.minutos_tarde <= 5` (margen de 5 minutos, igual que `GestorEmpleado.puntualidad_empleado()`). `CheckIn.minutos_tarde` ya existe en el modelo desde la migración 003.

**Nulos en `Reparto.hora_salida`** = si `hora_salida IS NULL`, ese reparto se excluye del cálculo de tiempo de entrega. No es un error, es un reparto sin salida registrada.

**Alerta "pedido bloqueado" — fallback sin datos del día** = la alerta usa `2 × tiempo_medio_ciclo_hoy_min`. Si aún no hay pedidos entregados hoy (turno recién empezado), se usa la mediana de los últimos 7 días como referencia. Si tampoco hay datos de 7 días, la alerta se omite.

**`_horas_trabajadas` y filtro por rol** = el helper usa `CheckIn.fin - CheckIn.inicio` (duración total del turno, sin desglosar por rol). Esto es válido porque cada empleado tiene un rol dominante. `TramoTurno` no se usa en este helper — si en el futuro se necesita desglosar por rol para empleados polivalentes, se crea un helper separado.

**`media_equipo` en comparativa** = media aritmética de `productividad_operaciones_hora` calculada solo sobre empleados con al menos 1 operación completada en el período. Empleados con 0 operaciones se excluyen de la media (pero sí aparecen en el ranking con productividad 0).

**Tabla raíz del JOIN en asistencia analítica** = `Turno` es la tabla raíz. Solo aparecen empleados que tenían turno planificado en el rango. Los empleados que ficharon sin turno planificado no aparecen en el endpoint de asistencia (esos casos se detectan en `/operacion/alertas`). `Ausencia` se une como LEFT JOIN adicional para enriquecer días sin CheckIn.

---

## Blueprint: `metricas_operacion.py`

**Prefijo:** `/metricas/operacion`
**Rol requerido:** `admin`, `manager`
**Sin parámetros de fecha** — siempre datos del momento actual

### Endpoints

#### `GET /metricas/operacion/resumen`

KPIs para tarjetas del panel principal.

```json
{
  "pedidos_activos": 12,
  "empleados_en_turno": 5,
  "cola_picking_count": 3,
  "cola_reparto_count": 2,
  "entregados_hoy": 47,
  "tasa_entrega_hoy_pct": 94,
  "tiempo_medio_ciclo_hoy_min": 28
}
```

`cola_picking_count` y `cola_reparto_count` son escalares (COUNT). El detalle de cada cola está en `/colas`.

**Fuente:** `Pedido` (estados operativos), `CheckIn` (fin=NULL, fecha=hoy), `PickingPedido` (pendiente sin asignar), `Reparto` (pendiente), `HistorialEstadoPedido` (ciclo).

---

#### `GET /metricas/operacion/asistencia`

Por cada empleado con turno planificado hoy. Se construye con un único JOIN entre `Turno`, `CheckIn` y `Empleado` para toda la lista, no query por empleado.

```json
[
  {
    "empleado_id": 7,
    "nombre": "Ana García",
    "rol": "picker",
    "turno_inicio": "09:00",
    "turno_fin": "17:00",
    "hora_fichaje": "09:08",
    "minutos_tarde": 8,
    "activo": true,
    "ausente": false
  }
]
```

`ausente = true` cuando no hay ningún `CheckIn` con `fecha = hoy` para ese empleado. `activo = true` cuando el `CheckIn` existe y `fin IS NULL`.

**Fuente:** `Turno` (fecha=hoy) LEFT JOIN `CheckIn` (fecha=hoy) JOIN `Empleado`.

---

#### `GET /metricas/operacion/colas`

Detalle de pedidos en espera, ordenados por antigüedad (más tiempo esperando primero). `minutos_esperando` se calcula desde el timestamp del último cambio de estado del pedido usando `HistorialEstadoPedido`.

```json
{
  "cola_picking": [
    {"pedido_id": 2341, "minutos_esperando": 14, "num_items": 3}
  ],
  "cola_reparto": [
    {"pedido_id": 2338, "minutos_esperando": 22, "num_items": 5}
  ]
}
```

`num_items` = COUNT de `PedidoDetalle` del pedido. No se incluye detalle de ítems en este endpoint.

---

#### `GET /metricas/operacion/pedidos-estado`

COUNT de pedidos activos por estado operativo (excluye terminales: entregado, cancelado, reembolsado).

```json
{
  "en_preparacion": 4,
  "preparado": 2,
  "en_reparto": 6,
  "confirmando_pago": 1
}
```

---

#### `GET /metricas/operacion/alertas`

Lista de alertas activas. Vacía si no hay ninguna. Ordenada por severidad descendente.

```json
[
  {
    "tipo": "ausencia_no_fichada",
    "severidad": "alta",
    "mensaje": "Carlos Ruiz tiene turno desde las 09:00 y no ha fichado (23 min de retraso)",
    "empleado_id": 12
  },
  {
    "tipo": "cola_picking_alta",
    "severidad": "alta",
    "mensaje": "3 pedidos en cola de picking sin picker asignado",
    "pedidos_afectados": [2341, 2342, 2343]
  },
  {
    "tipo": "pedido_bloqueado",
    "severidad": "media",
    "mensaje": "Pedido #2330 lleva 38 min en estado 'preparado' sin salir a reparto",
    "pedido_id": 2330
  }
]
```

**Condiciones y umbrales:**
| Tipo | Condición | Severidad |
|------|-----------|-----------|
| `ausencia_no_fichada` | Turno iniciado hace >15 min sin CheckIn | alta |
| `cola_picking_alta` | ≥3 pedidos en cola picking sin asignar | alta |
| `cola_reparto_alta` | ≥3 pedidos en cola reparto sin asignar | alta |
| `pedido_bloqueado` | Pedido lleva >2× el tiempo medio del día en el mismo estado | media |
| `repartidor_inactivo` | CheckIn abierto + rol repartidor + sin Reparto activo en >45 min | media |

---

## Blueprint: `metricas_analitica.py`

**Prefijo:** `/metricas/analitica`
**Rol requerido:** `admin`, `manager`
**Parámetros:** `?desde=YYYY-MM-DD&hasta=YYYY-MM-DD`. Default: últimos 7 días incluyendo hoy.

### Endpoints

#### `GET /metricas/analitica/resumen`

```json
{
  "pedidos_completados": 312,
  "tasa_entrega_pct": 93,
  "tiempo_medio_ciclo_min": 31,
  "ratio_cancelacion_pct": 4,
  "pedidos_por_forma_pago": {"online": 187, "efectivo": 98, "tarjeta": 27},
  "dias_analizados": 7
}
```

---

#### `GET /metricas/analitica/pedidos`

```json
{
  "throughput_por_dia": [
    {"fecha": "2026-03-15", "completados": 44, "cancelados": 2}
  ],
  "tiempo_medio_por_fase_min": {
    "confirmacion_a_preparacion": 3,
    "preparacion": 12,
    "espera_repartidor": 8,
    "reparto": 18
  },
  "distribucion_estado_final": {
    "entregado": 312,
    "cancelado": 14,
    "reembolsado": 2
  }
}
```

Fases calculadas con `_tiempo_entre_estados()`. Pares de estados:
- `confirmacion_a_preparacion`: PAGADO/CONTRA_REEMBOLSO → EN_PREPARACION
- `preparacion`: EN_PREPARACION → PREPARADO
- `espera_repartidor`: PREPARADO → EN_REPARTO
- `reparto`: EN_REPARTO → ENTREGADO

---

#### `GET /metricas/analitica/picking`

```json
{
  "tiempo_medio_picking_min": 11,
  "tiempo_medio_espera_asignacion_min": 4,
  "items_total": 1847,
  "items_encontrados_pct": 88,
  "items_sin_stock_pct": 7,
  "items_sustituidos_pct": 5,
  "top_productos_sin_stock": [
    {"producto_id": 12, "nombre": "Coca-Cola 2L", "veces_sin_stock": 23}
  ]
}
```

`tiempo_medio_picking_min` = media de (PickingPedido.updated_at − PickingPedido.created_at) donde estado=completado.
`tiempo_medio_espera_asignacion_min` = media del tiempo entre PAGADO y asignación de picker (primer empleado_id no nulo en PickingPedido).

---

#### `GET /metricas/analitica/reparto`

```json
{
  "tiempo_medio_entrega_min": 19,
  "tiempo_medio_espera_antes_salida_min": 7,
  "tasa_entrega_exitosa_pct": 93,
  "entregas_por_repartidor": [
    {
      "empleado_id": 4,
      "nombre": "Luis Martín",
      "entregas": 78,
      "tiempo_medio_min": 17,
      "tasa_exito_pct": 97
    }
  ]
}
```

Solo se incluyen repartos con `hora_salida IS NOT NULL` en el cálculo de tiempos.

---

#### `GET /metricas/analitica/empleados`

Parámetro adicional opcional: `?rol=picker|repartidor`.

```json
[
  {
    "empleado_id": 7,
    "nombre": "Ana García",
    "rol": "picker",
    "operaciones_completadas": 134,
    "horas_trabajadas": 38.5,
    "productividad_operaciones_hora": 3.5,
    "tiempo_medio_operacion_min": 10,
    "ratio_incidencias_pct": 2,
    "puntualidad_media_min": 3
  }
]
```

`horas_trabajadas` = suma de `(CheckIn.fin - CheckIn.inicio)` del período. CheckIns sin `fin` (turno aún abierto) se excluyen del cálculo histórico.
`ratio_incidencias_pct` = para pickers: `PickingItem sin_stock+sustituido / PickingItem total × 100`. Para repartidores: `Reparto no_entregado / Reparto total × 100`.

---

#### `GET /metricas/analitica/empleado/<id>`

```json
{
  "empleado_id": 7,
  "nombre": "Ana García",
  "rol": "picker",
  "asistencia": {
    "dias_planificados": 10,
    "dias_trabajados": 9,
    "ausencias": 1,
    "tasa_asistencia_pct": 90
  },
  "puntualidad": {
    "tasa_puntualidad_pct": 78,
    "media_minutos_tarde": 6,
    "tarde": 2,
    "puntuales": 7
  },
  "rendimiento": {
    "operaciones_completadas": 134,
    "horas_trabajadas": 38.5,
    "productividad_operaciones_hora": 3.5,
    "tiempo_medio_operacion_min": 10
  },
  "evolucion_semanal": [
    {"semana_inicio": "2026-03-09", "operaciones": 32, "tiempo_medio_min": 11},
    {"semana_inicio": "2026-03-16", "operaciones": 38, "tiempo_medio_min": 9}
  ]
}
```

`evolucion_semanal`: un punto por semana natural (lunes a domingo) que caiga dentro del rango `desde-hasta`. Se calcula desde tablas fuente (`PickingPedido` o `Reparto`), no desde `MetricaDiariaEmpleado` (esa tabla se reserva para uso futuro con caché).
`puntualidad` se obtiene llamando al método ya existente `GestorEmpleado.puntualidad_empleado(empleado_id, desde, hasta)`.

---

#### `GET /metricas/analitica/comparativa`

Parámetro requerido: `?rol=picker|repartidor`. Error 400 si no se pasa.

El ranking se ordena por `productividad_operaciones_hora` descendente. Es la métrica principal porque normaliza por tiempo trabajado. Las demás métricas se muestran como contexto.

```json
{
  "rol": "picker",
  "periodo": {"desde": "2026-03-15", "hasta": "2026-03-22"},
  "ranking": [
    {
      "posicion": 1,
      "empleado_id": 7,
      "nombre": "Ana García",
      "operaciones_completadas": 134,
      "productividad_operaciones_hora": 3.5,
      "tiempo_medio_operacion_min": 10,
      "ratio_incidencias_pct": 2,
      "puntualidad_media_min": 3
    }
  ],
  "media_equipo": {
    "productividad_operaciones_hora": 2.8,
    "tiempo_medio_operacion_min": 13,
    "ratio_incidencias_pct": 5
  }
}
```

---

#### `GET /metricas/analitica/asistencia`

```json
{
  "tasa_asistencia_global_pct": 92,
  "tasa_puntualidad_global_pct": 81,
  "por_empleado": [
    {
      "empleado_id": 7,
      "nombre": "Ana García",
      "dias_planificados": 10,
      "dias_trabajados": 9,
      "ausencias": 1,
      "tasa_puntualidad_pct": 78,
      "media_minutos_tarde": 6
    }
  ]
}
```

---

#### `GET /metricas/analitica/incidencias`

"Incidencia" en este endpoint = `PickingItem.estado in ('sin_stock', 'sustituido')` para picking + `Reparto.estado = 'no_entregado'` para reparto.

```json
{
  "total": 47,
  "por_tipo": {
    "sin_stock": 31,
    "entrega_fallida": 12,
    "sustitucion": 4
  },
  "por_empleado": [
    {
      "empleado_id": 9,
      "nombre": "Pedro López",
      "total_incidencias": 8,
      "ratio_sobre_operaciones_pct": 9
    }
  ],
  "productos_mas_afectados": [
    {"producto_id": 12, "nombre": "Coca-Cola 2L", "veces_sin_stock": 23}
  ]
}
```

`productos_mas_afectados` = top 10 productos con más `PickingItem.estado = 'sin_stock'` en el período. No existe el concepto "reincidente" como entidad — esto se aproxima mostrando frecuencia por producto.

---

## Manager: `GestorMetricas`

```python
class GestorMetricas:

    @property
    def session(self):
        from database import get_db
        return get_db()

    # =========================================================
    # BLOQUE 1 — Tiempo real
    # =========================================================
    def resumen_operacion(self) -> dict: ...
    def asistencia_hoy(self) -> list[dict]: ...
    def colas_detalle(self) -> dict: ...
    def pedidos_por_estado(self) -> dict: ...
    def alertas_tiempo_real(self) -> list[dict]: ...

    # =========================================================
    # BLOQUE 2 — Analítica
    # =========================================================
    def resumen_periodo(self, desde: date, hasta: date) -> dict: ...
    def metricas_pedidos(self, desde: date, hasta: date) -> dict: ...
    def metricas_picking(self, desde: date, hasta: date) -> dict: ...
    def metricas_reparto(self, desde: date, hasta: date) -> dict: ...
    def rendimiento_empleados(self, desde: date, hasta: date, rol: str | None = None) -> list[dict]: ...
    def ficha_empleado(self, empleado_id: int, desde: date, hasta: date) -> dict: ...
    def comparativa_empleados(self, desde: date, hasta: date, rol: str) -> dict: ...
    def asistencia_periodo(self, desde: date, hasta: date) -> dict: ...
    def metricas_incidencias(self, desde: date, hasta: date) -> dict: ...

    # =========================================================
    # HELPERS PRIVADOS
    # =========================================================
    def _horas_trabajadas(self, empleado_id: int, desde: date, hasta: date) -> float:
        """Suma (CheckIn.fin - CheckIn.inicio) del período. Excluye CheckIns sin fin."""

    def _tiempo_entre_estados(self, pedido_id: int, estado_a: str, estado_b: str) -> int | None:
        """Minutos entre dos estados en HistorialEstadoPedido. None si alguno no existe."""

    def _operaciones_empleado(self, empleado_id: int, rol: str, desde: date, hasta: date) -> list:
        """PickingPedido completados (rol=picker) o Reparto entregados (rol=repartidor)."""
```

---

## Fuentes de datos

| Área | Tablas | Nota |
|------|--------|------|
| Tiempos de ciclo y por fase | `HistorialEstadoPedido.cambiado_en` | Par de estados por fase |
| Puntualidad | `CheckIn.minutos_tarde` | Campo ya existente desde migración 003 |
| Asistencia | `Turno` LEFT JOIN `CheckIn` LEFT JOIN `Ausencia` | Un JOIN, no N queries |
| Picking | `PickingPedido` + `PickingItem` agrupado por estado | |
| Reparto | `Reparto.hora_entrega_real - Reparto.hora_salida` | Excluir nulos en hora_salida |
| Productividad | operaciones ÷ horas (de CheckIn) | Normalizado por tiempo real trabajado |
| Comparativa | mismas fuentes + media calculada en Python | Ordenado por productividad |

---

## Tests

Patrón: `patch.object(type(gestor), 'session', new_callable=PropertyMock)`.

Por método del manager:
- Estructura del dict devuelto (claves presentes)
- Cálculos: productividad, tiempos medios, ratios porcentuales
- Datos vacíos: período sin pedidos, empleado sin operaciones, sin turnos planificados
- Nulos: `hora_salida IS NULL` en Reparto, `CheckIn.fin IS NULL`

Por blueprint:
- Cliente Flask test con manager mockeado completamente
- Verificación de código HTTP y estructura de respuesta
- Parámetro `desde/hasta` ausente → usa default de 7 días
- `?rol=` ausente en `/comparativa` → devuelve 400

---

## Lo que NO entra en este spec

- Frontend / templates HTML
- Caché (Redis o MetricaDiariaEmpleado como caché)
- WebSockets o SSE
- Exportación CSV/Excel
- Permisos granulares por empleado
- Modificación de GestorDashboard o dashboard.py existentes
