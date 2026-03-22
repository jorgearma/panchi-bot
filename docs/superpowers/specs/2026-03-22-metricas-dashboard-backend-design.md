# Backend de Métricas — Dashboard de Administrador

**Fecha:** 2026-03-22
**Estado:** Aprobado
**Rama:** `migrar-bd`

---

## Objetivo

Construir la capa backend que expone los datos necesarios para dos paneles de administración:

1. **Panel del encargado** — operación en tiempo real: quién está, qué hay en cola, qué alertas hay ahora
2. **Panel del dueño** — analítica histórica: rendimiento, tendencias, comparativas entre empleados

No se construye frontend en este spec. No se implementa caché. El mecanismo de actualización del panel de operación es polling desde el cliente.

---

## Arquitectura

```
blueprints/
  metricas_operacion.py    →  /metricas/operacion/...   (encargado, tiempo real)
  metricas_analitica.py    →  /metricas/analitica/...   (dueño, histórico)

managers/
  gestor_metricas.py       →  toda la lógica de cálculo, sin lógica operativa
```

### Principios de diseño

- `GestorMetricas` es **solo lectura** — no modifica estados, no asigna nada. Eso sigue en `GestorDashboard`.
- Los blueprints de métricas **no duplican** rutas de `dashboard.py`. Si ya existe un endpoint equivalente, se reutiliza.
- La autenticación sigue el patrón existente: sesión Flask con verificación de rol.
- Todos los endpoints devuelven JSON con la estructura `{"ok": true, "data": {...}}` igual que el resto del proyecto.

---

## Blueprint: `metricas_operacion.py`

**Prefijo:** `/metricas/operacion`
**Usuario:** Encargado de turno
**Actualización:** Polling cada 30-60 segundos desde el cliente
**Parámetros de fecha:** Ninguno — siempre datos del momento actual

### Endpoints

#### `GET /metricas/operacion/resumen`

KPIs del panel principal. Diseñado para mostrarse en tarjetas en la parte superior del panel.

**Devuelve:**
```json
{
  "pedidos_activos": 12,
  "empleados_en_turno": 5,
  "cola_picking": 3,
  "cola_reparto": 2,
  "entregados_hoy": 47,
  "tasa_entrega_hoy_pct": 94,
  "tiempo_medio_ciclo_hoy_min": 28
}
```

**Fuente:** `Pedido`, `CheckIn` (fin=NULL, fecha=hoy), `PickingPedido` (estado=PENDIENTE sin asignar), `Reparto` (estado=PENDIENTE), `HistorialEstadoPedido`

---

#### `GET /metricas/operacion/asistencia`

Por cada empleado con turno planificado hoy: si fichó, a qué hora y cuántos minutos de desfase.

**Devuelve:** lista de objetos por empleado
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

**Fuente:** `Turno` (fecha=hoy) JOIN `CheckIn` (fecha=hoy) JOIN `Empleado`

---

#### `GET /metricas/operacion/colas`

Detalle de los pedidos en espera, ordenados por antigüedad (más tiempo esperando primero).

**Devuelve:**
```json
{
  "cola_picking": [
    {
      "pedido_id": 2341,
      "minutos_esperando": 14,
      "items": 3
    }
  ],
  "cola_reparto": [
    {
      "pedido_id": 2338,
      "minutos_esperando": 22,
      "items": 5
    }
  ]
}
```

**Fuente:** `PickingPedido` (estado=PENDIENTE, empleado_id=NULL) + `Reparto` (estado=PENDIENTE) + `HistorialEstadoPedido` para calcular antigüedad

---

#### `GET /metricas/operacion/pedidos-estado`

Distribución de pedidos activos por estado. Para mostrar un desglose tipo barra o lista.

**Devuelve:**
```json
{
  "en_preparacion": 4,
  "preparado": 2,
  "en_reparto": 6,
  "confirmando_pago": 1
}
```

**Fuente:** `Pedido` agrupado por `Estado`, filtrado por estados operativos (no terminales)

---

#### `GET /metricas/operacion/alertas`

Lista de alertas activas calculadas en tiempo real. Cada alerta tiene tipo, mensaje legible y severidad.

**Devuelve:**
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

**Condiciones que generan alerta:**
- Empleado con turno que no ha fichado pasados 15 min del inicio → severidad alta
- Cola de picking > 3 pedidos sin asignar → severidad alta
- Cola de reparto > 3 pedidos sin asignar → severidad alta
- Pedido lleva más del doble del tiempo medio del día en el mismo estado → severidad media
- Repartidor en turno (CheckIn abierto) sin reparto activo en más de 45 min → severidad media

**Fuente:** cruce de `Turno`, `CheckIn`, `PickingPedido`, `Reparto`, `HistorialEstadoPedido`

---

## Blueprint: `metricas_analitica.py`

**Prefijo:** `/metricas/analitica`
**Usuario:** Dueño / director
**Parámetros:** Todos aceptan `?desde=YYYY-MM-DD&hasta=YYYY-MM-DD`
**Default si no se pasan:** últimos 7 días
**Rol requerido:** admin o supervisor

### Endpoints

#### `GET /metricas/analitica/resumen`

KPIs agregados del período seleccionado.

**Devuelve:**
```json
{
  "pedidos_completados": 312,
  "tasa_entrega_pct": 93,
  "tiempo_medio_ciclo_min": 31,
  "ratio_cancelacion_pct": 4,
  "pedidos_por_forma_pago": {
    "online": 187,
    "efectivo": 98,
    "tarjeta": 27
  },
  "dias_analizados": 7
}
```

**Fuente:** `Pedido`, `HistorialEstadoPedido`

---

#### `GET /metricas/analitica/pedidos`

Análisis detallado del flujo de pedidos: throughput por día y desglose de tiempos por fase.

**Devuelve:**
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

**Fuente:** `Pedido`, `HistorialEstadoPedido` (timestamps de cada transición)

---

#### `GET /metricas/analitica/picking`

Métricas de la fase de preparación.

**Devuelve:**
```json
{
  "tiempo_medio_picking_min": 11,
  "tiempo_medio_espera_asignacion_min": 4,
  "items_total": 1847,
  "items_encontrados_pct": 88,
  "items_sin_stock_pct": 7,
  "items_sustituidos_pct": 5,
  "top_productos_sin_stock": [
    {"producto": "Coca-Cola 2L", "veces_sin_stock": 23}
  ]
}
```

**Fuente:** `PickingPedido`, `PickingItem` (agrupado por estado), `Producto`

---

#### `GET /metricas/analitica/reparto`

Métricas de la fase de entrega.

**Devuelve:**
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

**Fuente:** `Reparto`, `HistorialEstadoPedido`, `Empleado`

---

#### `GET /metricas/analitica/empleados`

Rendimiento de todos los empleados en el período, filtrable por rol.

**Parámetro adicional:** `?rol=picker|repartidor` (opcional)

**Devuelve:** lista por empleado
```json
[
  {
    "empleado_id": 7,
    "nombre": "Ana García",
    "rol": "picker",
    "pedidos_procesados": 134,
    "horas_trabajadas": 38.5,
    "productividad_pedidos_hora": 3.5,
    "tiempo_medio_operacion_min": 10,
    "ratio_incidencias_pct": 2,
    "puntualidad_media_min": 3
  }
]
```

**Fuente:** `CheckIn` (horas trabajadas), `PickingPedido` o `Reparto` según rol, `Turno` (puntualidad via `minutos_tarde`)

---

#### `GET /metricas/analitica/empleado/<id>`

Ficha completa de un empleado individual.

**Devuelve:**
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
    "pedidos_procesados": 134,
    "horas_trabajadas": 38.5,
    "productividad_pedidos_hora": 3.5,
    "tiempo_medio_operacion_min": 10
  },
  "evolucion_semanal": [
    {"semana": "2026-W11", "pedidos": 32, "tiempo_medio_min": 11},
    {"semana": "2026-W12", "pedidos": 38, "tiempo_medio_min": 9}
  ]
}
```

**Fuente:** `Turno`, `CheckIn`, `Ausencia`, `PickingPedido` o `Reparto`, `GestorEmpleado.puntualidad_empleado()`

---

#### `GET /metricas/analitica/comparativa`

Ranking de empleados del mismo rol, ordenados por productividad compuesta.

**Parámetro requerido:** `?rol=picker|repartidor`

**Devuelve:**
```json
{
  "rol": "picker",
  "periodo": {"desde": "2026-03-15", "hasta": "2026-03-22"},
  "ranking": [
    {
      "posicion": 1,
      "empleado_id": 7,
      "nombre": "Ana García",
      "pedidos_procesados": 134,
      "productividad_pedidos_hora": 3.5,
      "tiempo_medio_min": 10,
      "ratio_incidencias_pct": 2,
      "puntualidad_media_min": 3
    }
  ],
  "media_equipo": {
    "productividad_pedidos_hora": 2.8,
    "tiempo_medio_min": 13,
    "ratio_incidencias_pct": 5
  }
}
```

**Fuente:** misma que `rendimiento_empleados`, filtrado por rol, con media del equipo añadida

---

#### `GET /metricas/analitica/asistencia`

Resumen de asistencia y puntualidad de todo el equipo en el período.

**Devuelve:**
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

**Fuente:** `Turno`, `CheckIn`, `Ausencia`

---

#### `GET /metricas/analitica/incidencias`

Análisis de incidencias operativas del período.

**Devuelve:**
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
  "reincidentes": [
    {"tipo": "sin_stock", "producto": "Coca-Cola 2L", "veces": 23}
  ]
}
```

**Fuente:** `PickingItem` (estado=sin_stock|sustituido), `Reparto` (estado=NO_ENTREGADO), agrupados por empleado y tipo

---

## Manager: `GestorMetricas`

### Estructura interna

```python
class GestorMetricas:

    @property
    def session(self): ...   # igual que el resto de managers

    # =========================================================
    # BLOQUE 1 — Tiempo real (sin parámetros de fecha)
    # =========================================================

    def resumen_operacion(self) -> dict: ...
    def asistencia_hoy(self) -> list[dict]: ...
    def colas_detalle(self) -> dict: ...
    def pedidos_por_estado(self) -> dict: ...
    def alertas_tiempo_real(self) -> list[dict]: ...

    # =========================================================
    # BLOQUE 2 — Analítica (fecha_inicio, fecha_fin requeridos)
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

    def _horas_trabajadas(self, empleado_id: int, desde: date, hasta: date) -> float: ...
    def _tiempo_entre_estados(self, pedido_id: int, estado_a: str, estado_b: str) -> int | None: ...
    def _operaciones_empleado(self, empleado_id: int, rol: str, desde: date, hasta: date) -> list: ...
```

### Helpers clave

**`_horas_trabajadas(empleado_id, desde, hasta)`**
Suma `(CheckIn.fin - CheckIn.inicio)` para todos los check-ins del empleado en el período. Base de todos los cálculos de productividad normalizada.

**`_tiempo_entre_estados(pedido_id, estado_a, estado_b)`**
Busca en `HistorialEstadoPedido` los timestamps de dos estados consecutivos y devuelve la diferencia en minutos. Es la función central para desglosar el ciclo de vida de un pedido por fases.

**`_operaciones_empleado(empleado_id, rol, desde, hasta)`**
Devuelve la lista de `PickingPedido` o `Reparto` completados por el empleado según su rol, en el período. Reutilizado en rendimiento individual, comparativa y ficha.

---

## Fuentes de datos — resumen por área

| Área de métrica | Tablas principales | Campo clave |
|-----------------|-------------------|-------------|
| Tiempos de ciclo y por fase | `HistorialEstadoPedido` | `cambiado_en` por estado |
| Rendimiento pickers | `PickingPedido`, `CheckIn` | `estado`, `fin - inicio` |
| Rendimiento repartidores | `Reparto`, `CheckIn` | `hora_entrega_real - hora_salida` |
| Puntualidad | `CheckIn`, `Turno` | `CheckIn.minutos_tarde` |
| Asistencia | `Turno`, `CheckIn`, `Ausencia` | presencia de check-in vs turno planificado |
| Stock e incidencias picking | `PickingItem` | `estado` agrupado |
| Productividad | operaciones ÷ horas trabajadas | normalizado por `CheckIn` |
| Comparativa entre empleados | mismas fuentes + media del grupo | filtrado por `rol_id` |

---

## Tests

Patrón existente del proyecto: `patch.object(type(gestor), 'session', new_callable=PropertyMock)`.

Cada método del manager tendrá tests unitarios que verifican:
- Estructura del dict devuelto (claves presentes)
- Cálculos básicos (productividad, tiempos, ratios)
- Comportamiento con datos vacíos (período sin pedidos, sin empleados)
- Parámetros de fecha: default correcto cuando no se pasan

Los blueprints se testean con el cliente de test Flask, mockeando el manager completo.

---

## Lo que NO entra en este spec

- Frontend / templates HTML
- Caché (Redis o tabla de métricas diarias)
- WebSockets o SSE
- Exportación a CSV/Excel
- Notificaciones push
- Permisos granulares por empleado (todos los endpoints son admin/supervisor)
