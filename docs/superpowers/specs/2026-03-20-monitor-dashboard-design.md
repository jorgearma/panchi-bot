# Monitor Dashboard — Diseño

**Fecha:** 2026-03-20
**Rama:** refactorizar-estructura
**Estado:** Aprobado por el usuario

---

## Contexto

El monitor (`/dashboard/monitor`) es la pantalla de control operativo en tiempo real del restaurante. Se usa en dos contextos simultáneos:

1. **Pantalla fija (TV/monitor en cocina o mostrador):** solo visualización, nadie interactúa con el ratón. Debe ser legible a 2 metros.
2. **Portátil del encargado:** misma URL, el encargado toma decisiones mirando la pantalla.

El objetivo es que el encargado identifique cuellos de botella y tome decisiones correctas en segundos, sin scroll ni navegación adicional.

---

## Principios de diseño

- **Todo visible a la vez:** el layout completo cabe en 100vh sin scroll.
- **Solo visualización:** no se ejecutan acciones desde el monitor (cancelar, asignar, etc. se hacen en otras pantallas del dashboard).
- **Legible en TV:** texto suficientemente grande, colores con alto contraste, sin elementos que requieran hover para entenderse.
- **Tiempo real:** auto-refresh cada 15 segundos (ya implementado).

---

## Layout

```
┌──────────────────────────────────────────── HEADER (sticky, ~48px) ──┐
│ PANCHI | Centro de Control       🟢 EN VIVO  Actualizado 3s  ↻  ←    │
├───────────────────────────────────────────── KPI BAR (~52px) ─────────┤
│ Hoy:28  Activos:6  Prep:4  Reparto:3  Entregados:12  💰342€  ⏱18m  🚚35m │
├───────────────────────── ALERT BANNER (0–40px, solo si hay alertas) ──┤
│ 🔴 Pedido #14 lleva 45min en preparación  ·  #09 preparado sin rider  │
├──────────────────────────────────── PIPELINE KANBAN (~180px fijo) ────┤
│  PAGADO/CR  │  EN PREPARACIÓN  │   PREPARADO   │  EN REPARTO  │  ✓   │
│  [tarjetas] │   [tarjetas]     │  [tarjetas]   │  [tarjetas]  │ stat │
├─────────────────────────────────────── EMPLOYEES GRID (resto) ────────┤
│  📦 PICKERS (col 1/3)  │  🛵 REPARTIDORES (col 2/3)  │  🚨 ALERTAS  │
│                        │                              │  📡 FEED     │
└────────────────────────┴──────────────────────────────┴───────────────┘
```

---

## Zona 1: KPI Bar

### Métricas mostradas (8 chips, sin cambio de estructura)

| Chip | Valor | Color |
|------|-------|-------|
| Pedidos hoy | número | blanco |
| Activos | número | naranja |
| En preparación | número | azul |
| En reparto | número | amarillo |
| Entregados | número | verde |
| Ingresos hoy | €€€ | esmeralda |
| T.Preparación | Xmin | rojo si >30min |
| T.Entrega | Xmin | rojo si >40min |

### Nueva funcionalidad: tooltip en "Ingresos hoy"

Al pasar el ratón (portátil) sobre el chip de ingresos, se muestra un tooltip con:
- 💳 Online: X€
- 💵 Efectivo: X€
- 💳 Tarjeta: X€
- ❌ Cancelaciones hoy: N

Estos datos ya llegan en `metricas.ingresos_por_metodo` y `metricas.cancelaciones_hoy` pero no se visualizan actualmente.

---

## Zona 2: Alert Banner

### Cambio respecto al diseño actual

Actualmente el banner muestra **solo errores O solo warnings**, nunca ambos. Nuevo comportamiento: mostrar ambos en la misma franja separados por un divisor vertical, priorizando errores a la izquierda.

```
🔴 #14 lleva 45min en preparación  ·  #09 preparado sin rider   │  ⚠ Stock bajo: Tomates (2 ud)
```

### Badge de alertas en header

Añadir un badge numérico (naranja) junto al indicador EN VIVO del header que muestra el total de alertas activas. Visible desde lejos en TV.

---

## Zona 3: Pipeline Kanban (nueva)

Esta zona es la principal adición al monitor. Muestra todos los pedidos activos distribuidos en columnas según su estado, permitiendo ver el flujo y los cuellos de botella de un vistazo.

### Columnas

| Columna | Estado(s) del pedido | Color de cabecera |
|---------|---------------------|-------------------|
| PAGADO / CR | `pagado`, `contra-reembolso` | esmeralda/púrpura |
| EN PREPARACIÓN | `en-preparacion` | azul |
| PREPARADO | `preparado` | índigo |
| EN REPARTO | `en-reparto` | naranja |
| ENTREGADOS | `entregado` (hoy) | verde (solo stats) |

### Tarjeta de pedido

```
┌──────────────────────────┐
│ #14              45min   │  ← timer color según umbral
│ 💵 cobrar   ·   3 items  │
└──────────────────────────┘
```

Campos por tarjeta:
- `#ID` del pedido
- Timer: minutos acumulados en el estado actual
- Icono de forma de pago: 💳 online / 💵 cobrar
- Número de items

En portátil: hover sobre la tarjeta muestra tooltip con nombre del cliente, dirección de entrega.

### Lógica de color del timer

Los umbrales se **alinean con `_UMBRALES_RETRASO`** del backend para que el Kanban y el alert banner sean consistentes:

| Estado | Normal (verde) | Warning (amarillo) | Error (rojo + pulso) |
|--------|---------------|-------------------|----------------------|
| Pagado/CR | < 10min | 10–15min | > 15min (umbral backend: 10min) |
| En preparación | < 20min | 20–30min | > 30min (umbral backend: 30min) |
| Preparado | < 10min | 10–15min | > 15min (umbral backend: 15min, nivel error) |
| En reparto | < 40min | 40–60min | > 60min (umbral backend: 60min, nivel error) |

El umbral de error del Kanban coincide con el umbral del backend. El amarillo es una "zona de aviso previo" exclusiva del Kanban, antes de que salte la alerta.

### Columna cuello de botella

Si una columna tiene ≥ 3 pedidos con timer en rojo, el **fondo de la columna entera pulsa** suavemente en rojo oscuro. Detectable desde 3 metros en TV.

### Columna "Entregados"

No muestra tarjetas individuales. Muestra solo stats del día:
- Número grande: `metricas.entregados_hoy` (ya disponible)
- Subtexto: ingresos acumulados de esas entregas (`metricas.ingresos_hoy_eur`)

No requiere query adicional — usa datos ya presentes en `metricas`.

### Overflow de tarjetas

La zona del pipeline tiene altura fija de ~180px. Altura máxima de cada tarjeta: 52px (normal), 36px (comprimida).

- **≤ 3 pedidos:** tarjetas normales (52px, padding completo)
- **4–5 pedidos:** tarjetas comprimidas (36px, sin padding vertical extra)
- **≥ 6 pedidos:** se muestran las primeras 5 + chip "+N más" con fondo rojo. El chip no es clicable (monitor es solo visualización).

Esta regla garantiza que el pipeline siempre cabe en la altura fija sin scroll, incluso en TV.

### Datos de backend

El endpoint `/dashboard/monitor/datos` ya devuelve `pipeline` y `pedidos_sin_picker` / `pedidos_sin_repartidor`. El template recibe estos datos pero no los renderiza. La nueva zona usará:
- `data.pedidos_activos_por_estado` (nuevo campo a añadir en el endpoint, o derivado de `pipeline`)
- Para cada pedido: `pedido_id`, `estado`, `forma_pago`, `n_items`, `minutos_en_estado`

---

## Zona 4: Employees Grid (sin cambios estructurales)

Las columnas de Pickers y Repartidores conservan su diseño y funcionalidad actual. Se mantienen:
- Cards colapsables por empleado
- Barra de progreso de picking
- Stats: completados hoy / tiempo medio / incidencias
- Modal de historial
- Pedidos sin picker y sin repartidor como secciones destacadas arriba de cada columna

---

## Zona 5: Alertas + Feed (mejoras menores)

### Alertas

- Stock bajo (`nivel: info`) se eleva a `nivel: warning` si stock = 0, para que sea visible en la lista
- El orden de prioridad se mantiene: error → warning → info

### Feed de actividad

- Los eventos de tipo `cancelado` se muestran con fondo rojo tenue para destacar visualmente entre el flujo normal
- Sin cambios estructurales

---

## Cambios en backend necesarios

### Nuevo campo `pedidos_pipeline` en el endpoint `/dashboard/monitor/datos`

**Archivo:** `blueprints/dashboard.py`

El endpoint añade la clave `pedidos_pipeline` llamando a `gestor_dashboard.pedidos_activos()` y proyectando solo los campos necesarios:

```python
pedidos_pipeline = [
    {
        "pedido_id": p["pedido_id"],
        "estado":    p["estado"],
        "forma_pago": p["forma_pago"],
        "n_items":   len(p["items"]),          # len() del array items
        "minutos_en_estado": p["minutos_en_estado"],
        "total":     p["total"],
        "cliente_nombre": p["cliente_nombre"], # para tooltip hover
        "direccion_entrega": p["direccion_entrega"],
    }
    for p in gestor_dashboard.pedidos_activos()
]
```

**Nota sobre `minutos_en_estado`:** `pedidos_activos()` calcula este campo usando `FechaActualizacion` como proxy del último cambio de estado. Esto es una aproximación aceptable — `FechaActualizacion` se actualiza en cada transición de estado vía `actualizar_estado()`. En casos donde se modifiquen otros campos del pedido sin cambiar estado, el timer podría reiniciarse; se acepta esta limitación de momento.

### Clave `pipeline` en el estado Alpine.js

El estado Alpine.js actual tiene `this.pipeline = data.pipeline || {}` pero el endpoint no devuelve una clave `pipeline`. Esta variable está huérfana. La nueva implementación:
- Mantiene `this.pipeline` como variable de conteo por estado (no se usa actualmente, puede eliminarse)
- Añade `this.pedidosPipeline = data.pedidos_pipeline || []` como nueva variable para el Kanban
- No hay colisión de nombres

---

## Cambios en frontend

| Cambio | Archivo | Descripción |
|--------|---------|-------------|
| Nueva zona HTML Pipeline Kanban | `templates/dashboard/monitor.html` | Franja fija entre KPI bar y employees grid |
| Tooltip en KPI "Ingresos hoy" | mismo archivo | Hover muestra desglose por método + cancelaciones |
| Alert banner unificado | mismo archivo | Errores + warnings en la misma franja |
| Badge de alertas en header | mismo archivo | Contador numérico junto a indicador EN VIVO |
| Eventos `cancelado` con fondo rojo | mismo archivo | Estilo en el feed de actividad |
| Alpine.js: lógica del pipeline | mismo archivo | Renderizado de tarjetas, timers, color por umbral, overflow |

---

## Lo que NO se incluye

- Acciones desde el monitor (asignar picker/rider, cancelar pedidos)
- Mapa de repartidores (no fue priorizado)
- Notificaciones sonoras / push
- Modo TV separado con URL distinta

Estas funcionalidades pueden ser fases futuras independientes.
