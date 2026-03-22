# Dashboard Admin — Plan de Frontend

> **Para agentes:** Este documento es un plan de diseño y arquitectura frontend, no un plan de implementación paso a paso. Cuando el usuario esté listo para implementar, usar superpowers:writing-plans para convertir cada pantalla en un plan TDD.

**Objetivo:** Construir el dashboard de administración completo para gestión de turnos, pedidos, rendimiento de empleados, estadísticas históricas e incidencias.

**Arquitectura:** Jinja2 server-rendered + Tailwind CSS + Alpine.js. Sin frameworks SPA. Cada pantalla es una ruta Flask independiente con su propio HTML y Alpine component. Los datos en tiempo real usan polling fetch (como el monitor actual).

**Stack:** Tailwind CSS (CDN), Alpine.js 3.x, Leaflet.js (mapa), Google Fonts Manrope, Chart.js (nuevo, para gráficos históricos).

---

## Resumen Ejecutivo

El panel admin actual (`/dashboard`, `/dashboard/monitor`) cubre la **operación en tiempo real**: pedidos activos, asignación de pickers/repartidores, mapa, alertas vivas. Está bien construido y no hay que tocarlo.

**Lo que falta** son las vistas de *retrospectiva y gestión*:

| Gap | Pantalla a construir |
|-----|----------------------|
| Ver historial de pedidos con filtros | Historial de Pedidos |
| Saber quién trabajó y cuánto | Turnos y Asistencia |
| Medir el rendimiento de cada empleado | Rendimiento por Empleado |
| Ver tendencias de ventas y tiempos | Estadísticas e Histórico |
| Profundizar en un pedido concreto | Detalle de Pedido (modal/panel) |
| Registrar y seguir incidencias | Gestión de Incidencias |

**Filosofía de diseño:** Consistencia con lo que ya existe. Light mode con glass-panels para vistas de gestión (como `dashboard/index.html`). Dark mode para la pantalla de monitor en tiempo real (como ya está). Sin reinventar el sistema visual.

---

## Mapa de Pantallas

```
/dashboard                ← YA EXISTE: panel operativo en tiempo real
/dashboard/monitor        ← YA EXISTE: centro de control dark mode

/dashboard/historial      ← NUEVA: tabla de pedidos históricos
/dashboard/turnos         ← NUEVA: asistencia y turnos del día/semana
/dashboard/rendimiento    ← NUEVA: métricas por empleado
/dashboard/estadisticas   ← NUEVA: charts e histórico
/dashboard/incidencias    ← NUEVA: log de incidencias (post-MVP)
```

### Navegación general

```
┌─────────────────────────────────────────────┐
│  PANCHI OPS  [LIVE•]  [🔔 alertas]  [menú] │
├─────────────────────────────────────────────┤
│  nav tabs:                                   │
│  Hoy  |  Historial  |  Turnos  |  Rendim.  │
│       |  Estadíst.  |  Incid.  |           │
└─────────────────────────────────────────────┘
```

- Header persistente (igual al actual) con indicador live y badge de alertas.
- Tabs de navegación debajo del header — no sidebar (el panel es usado en tablet/escritorio).
- En móvil: tabs colapsan en un `<select>` o hamburger icon.
- La ruta activa queda resaltada en el tab.

---

## Detalle por Pantalla

---

### P1 — Panel Operativo (`/dashboard`) ← YA EXISTE

**Estado:** Funcional. No requiere cambios en este plan.

Solo añadir el **tab de navegación** al header existente para enlazar con las nuevas pantallas sin romper lo que hay.

---

### P2 — Monitor en Tiempo Real (`/dashboard/monitor`) ← YA EXISTE

**Estado:** Funcional (dark mode). No requiere cambios.

---

### P3 — Historial de Pedidos (`/dashboard/historial`) — MVP

**Objetivo:** Consultar cualquier pedido pasado o presente. Tabla paginada con filtros. Ver el detalle completo de un pedido sin salir de la pantalla.

**Datos que muestra:**
- Tabla: PedidoID, Cliente (nombre/teléfono), Fecha, Estado, Total €, Forma de pago, Picker asignado, Repartidor asignado, Tiempo total.
- Panel lateral (o modal) al hacer clic en una fila: detalle completo del pedido con historial de estados (timeline), items del carrito, datos de reparto, motivo de cancelación si aplica.

**Filtros:**
- Rango de fechas (hoy / ayer / esta semana / este mes / custom datepicker)
- Estado: todos | activos | entregados | cancelados | reembolsados
- Forma de pago: online | efectivo | tarjeta
- Empleado (picker o repartidor) — dropdown
- Búsqueda libre: por PedidoID, nombre de cliente, teléfono

**Componentes:**
- `<FilterBar>` — barra de filtros colapsable en móvil
- `<OrdersTable>` — tabla con columnas ordenables, paginación (20/50/100 por página)
- `<OrderDetailPanel>` — panel lateral deslizante (slide-over) con:
  - Timeline de estados con timestamps
  - Items del pedido (con estado picking por item)
  - Datos del reparto (repartidor, hora salida, hora entrega)
  - Acciones: cancelar pedido (si no es terminal), ver en mapa
- `<EmptyState>` — "No hay pedidos con estos filtros"
- `<LoadingSkeleton>` — filas grises animadas mientras carga
- `<ErrorBanner>` — si falla la API

**Acciones del usuario:**
- Aplicar/limpiar filtros → recarga la tabla
- Click en fila → abre detalle
- Exportar CSV (post-MVP)
- Cancelar pedido desde el detalle (si el estado lo permite)

**Tiempo real:** No necesario. Botón "Actualizar" manual o auto-refresh opcional cada 60s.

**Endpoints necesarios (NUEVOS en backend):**
```
GET /dashboard/historial-pedidos
  ?desde=&hasta=&estado=&forma_pago=&empleado_id=&q=&page=&per_page=
  → { pedidos: [...], total: N, page: N, pages: N }

GET /dashboard/pedido/<id>/detalle
  → { pedido, items, historial_estados, picking, reparto, pagos }
```

**Experiencia móvil:** Tabla scrollable horizontalmente. El panel de detalle ocupa pantalla completa en móvil.

---

### P4 — Turnos y Asistencia (`/dashboard/turnos`) — MVP

**Objetivo:** Ver quién está trabajando hoy, a qué hora llegó, cuántas horas lleva, y consultar el historial de turnos por empleado o por fecha.

**Datos que muestra:**

*Vista "Hoy":*
- Tarjetas por empleado: nombre, rol, hora de check-in, horas activas (contador en vivo), estado operativo actual (disponible / en picking / en reparto / pausa / desconectado).
- Resumen: N empleados activos | N ausentes hoy | N en pausa.

*Vista "Historial":*
- Tabla: Fecha, Empleado, Rol, Hora entrada, Hora salida, Horas trabajadas, Pedidos gestionados.
- Agrupable por empleado o por fecha.

**Filtros:**
- Pestaña Hoy / Semana / Mes
- Empleado (dropdown)
- Rol (picker / repartidor / manager)

**Componentes:**
- `<ShiftSummaryBar>` — 3 badges: activos / ausentes / en pausa
- `<EmployeeShiftCard>` — tarjeta con nombre, rol, avatar inicial, estado con color, horas activas (si está trabajando: contador live con `setInterval`)
- `<ShiftHistoryTable>` — tabla paginada con columnas ordenables
- `<EmptyState>` — "Nadie ha hecho check-in hoy"

**Acciones del usuario:**
- Filtrar por rol o empleado
- Click en empleado → ir a su pantalla de rendimiento
- (Post-MVP) Registrar turno manual si olvidó hacer check-in

**Tiempo real:** Solo la vista "Hoy". Polling cada 30s para actualizar contadores y estados operativos.

**Endpoints necesarios (NUEVOS en backend):**
```
GET /dashboard/turnos/hoy
  → { empleados: [{ id, nombre, rol, check_in, horas_activas, estado_operativo }] }

GET /dashboard/turnos/historial
  ?desde=&hasta=&empleado_id=&rol=&page=
  → { turnos: [...], total, pages }
```

---

### P5 — Rendimiento por Empleado (`/dashboard/rendimiento`) — MVP

**Objetivo:** Medir y comparar el rendimiento de pickers y repartidores. Ver métricas individuales y ranking.

**Datos que muestra:**

*Vista resumen (todos los empleados):*
- Tabla/cards comparativa: Empleado, Rol, Pedidos gestionados, Tiempo medio (preparación o entrega), Incidencias, Tasa de completado %.
- Ordenable por cualquier columna.
- Período seleccionable: hoy / esta semana / este mes.

*Vista individual (click en empleado):*
- KPIs principales: pedidos completados, tiempo medio, mejor tiempo, incidencias.
- Gráfico de barras: pedidos por día (últimos 7 días).
- Historial de turnos recientes.
- Tabla de últimos pedidos gestionados.

**Filtros:**
- Período: hoy / semana / mes / custom
- Rol: todos / pickers / repartidores
- Ordenar por: pedidos | tiempo medio | incidencias

**Componentes:**
- `<PeriodSelector>` — tabs de hoy/semana/mes + datepicker custom
- `<RankingTable>` — tabla con columnas ordenables y highlights (mejor/peor)
- `<EmployeeKpiCard>` — 4 métricas en grid 2×2
- `<MiniBarChart>` — Chart.js, pedidos por día (7 barras)
- `<RecentOrdersList>` — lista compacta de últimos pedidos
- `<EmptyState>` — "Sin datos para el período"

**Acciones del usuario:**
- Cambiar período → recarga métricas
- Click en empleado → vista individual
- Volver → lista comparativa

**Endpoints necesarios (NUEVOS en backend):**
```
GET /dashboard/rendimiento
  ?periodo=hoy|semana|mes&rol=picker|repartidor
  → { empleados: [{ id, nombre, rol, pedidos, tiempo_medio, incidencias, tasa }] }

GET /dashboard/rendimiento/<empleado_id>
  ?periodo=
  → { kpis: {...}, pedidos_por_dia: [...], turnos_recientes: [...], ultimos_pedidos: [...] }
```

---

### P6 — Estadísticas e Histórico (`/dashboard/estadisticas`) — MVP

**Objetivo:** Ver tendencias de ventas, volumen de pedidos y tiempos de operación a lo largo del tiempo. Identificar patrones (pico de pedidos, días flojos, mejora/degradación de tiempos).

**Datos que muestra:**
- KPIs de período: ingresos totales, pedidos totales, pedidos entregados, tasa cancelación, tiempo medio preparación, tiempo medio entrega.
- Gráfico de líneas: ingresos y pedidos por día.
- Gráfico de barras horizontales: pedidos por estado (distribución).
- Gráfico de dona: forma de pago (online / efectivo / tarjeta).
- Gráfico de líneas doble: tiempos medios (preparación y entrega) por día.
- Tabla resumen por día con columnas exportables (post-MVP).

**Filtros:**
- Período: última semana / último mes / últimos 3 meses / custom
- Granularidad: por día / por semana (cuando el rango es > 1 mes)

**Componentes:**
- `<KpiSummaryGrid>` — 6 tarjetas métricas en grid responsive
- `<LineChart>` — Chart.js, dual-axis (pedidos izq, ingresos der)
- `<HorizontalBarChart>` — distribución de estados
- `<DonutChart>` — forma de pago
- `<TimeChart>` — tiempos medios
- `<PeriodSelector>` — reutilizado de rendimiento

**Acciones del usuario:**
- Cambiar período → recarga todos los charts
- Hover en punto de gráfico → tooltip detallado
- (Post-MVP) Exportar datos CSV

**Endpoints necesarios (NUEVOS en backend):**
```
GET /dashboard/estadisticas
  ?desde=&hasta=&granularidad=dia|semana
  → {
      kpis: { ingresos, pedidos, entregados, cancelados, t_prep, t_entrega },
      serie_pedidos_ingresos: [{ fecha, pedidos, ingresos }],
      distribucion_estados: { ... },
      forma_pago: { online, efectivo, tarjeta },
      serie_tiempos: [{ fecha, t_prep, t_entrega }]
    }
```

---

### P7 — Incidencias (`/dashboard/incidencias`) — Post-MVP

**Objetivo:** Registrar, clasificar y hacer seguimiento de incidencias operativas (stock, cliente no responde, retrasos extremos).

**Datos que muestra:**
- Tabla: ID, Fecha, Tipo, Pedido relacionado, Empleado, Descripción, Estado (abierta/cerrada).
- Filtros por tipo, estado y período.
- Detalle expandible en línea.

**Componentes:**
- `<IncidentTable>` — tabla con expand
- `<IncidentBadge>` — tipo con color (stock / cliente / retraso / otro)
- `<NewIncidentForm>` — modal con campos tipo, pedido relacionado, descripción

**Nota:** El modelo `Incidencia` ya existe en `models.py` (importado en gestor_dashboard.py). Revisar si tiene los campos necesarios antes de construir la pantalla.

---

## Componentes Reutilizables

Estos componentes aparecen en múltiples pantallas. Deben diseñarse primero para garantizar consistencia.

### Sistema de diseño base (ya existe — no cambiar)
```
Variables CSS: --bg, --panel, --panel-strong, --line, --ink, --muted,
               --brand, --brand-soft, --warning, --danger, --success
Clases CSS:    .glass-panel, .soft-card, .metric-card, .section-title
Fuente:        Manrope
```

### Componentes nuevos a construir (una sola vez, incluir vía Jinja2 macros o inline)

| Componente | Usado en | Descripción |
|---|---|---|
| `FilterBar` | Historial, Turnos, Rendimiento, Estadísticas | Fila de filtros colapsable |
| `PeriodSelector` | Rendimiento, Estadísticas | Tabs hoy/semana/mes + datepicker |
| `DataTable` | Historial, Turnos, Rendimiento | Tabla con sort, paginación, loading skeleton |
| `EmptyState` | Todas | Ilustración + mensaje + acción sugerida |
| `LoadingSkeleton` | Todas | Filas grises animadas mientras carga |
| `ErrorBanner` | Todas | Banner rojo con mensaje + botón reintentar |
| `SlideOverPanel` | Historial (detalle pedido) | Panel lateral deslizante |
| `StatusBadge` | Historial, Rendimiento | Pastilla de color con estado del pedido/empleado |
| `KpiCard` | Estadísticas, Rendimiento | Tarjeta con número grande + etiqueta + delta opcional |
| `MiniBarChart` | Rendimiento individual | Chart.js encapsulado en Alpine component |
| `ConfirmDialog` | Historial (cancelar pedido) | Modal de confirmación con motivo |

### Estrategia para componentes con Alpine.js

Cada pantalla tiene un Alpine component principal:

```js
// Patrón: datos + fetch + estado de UI en un solo x-data
Alpine.data('historialPedidos', () => ({
  pedidos: [],
  total: 0,
  pagina: 1,
  filtros: { desde: '', hasta: '', estado: '', q: '' },
  cargando: false,
  error: null,
  pedidoDetalle: null,

  async init() { await this.cargar() },
  async cargar() { ... fetch con filtros ... },
  abrirDetalle(id) { ... },
  cerrarDetalle() { this.pedidoDetalle = null },
}))
```

---

## Consideraciones Transversales

### Tiempo real
- Pantallas operativas (P1, P2): polling cada 15-30s. Ya implementado.
- Turnos hoy (P4): polling cada 30s solo para contadores de horas activas.
- Historial, Rendimiento, Estadísticas: sin polling. Botón "Actualizar" manual.
- Nunca WebSockets — el stack actual no los soporta y el polling es suficiente.

### Tablas
- Paginación server-side para historial (> 100 registros potenciales).
- Ordenación client-side para tablas pequeñas (< 50 filas, rendimiento empleados).
- Columnas mínimas en móvil — ocultar columnas secundarias con `hidden sm:table-cell`.
- Scroll horizontal en móvil antes de quitar columnas críticas.

### Gráficos (Chart.js)
- Solo en P5 y P6 — no en el monitor en tiempo real (es overhead innecesario).
- Cargar Chart.js solo en las rutas que lo necesiten (`{% block scripts %}`).
- Todos los charts: paleta basada en variables CSS del sistema de diseño.
- Sin animaciones largas — `animation: { duration: 300 }`.
- Tooltip en español. No usar el tooltip por defecto.
- Fallback: si Chart.js no carga, mostrar tabla de datos en su lugar.

### Alertas
- Alertas operativas (pedido retrasado, sin repartidor): ya en el monitor.
- En historial y rendimiento: alertas informativas inline (`<ErrorBanner>`) para errores de carga.
- Badge de alertas activas en el header → link al monitor.

### Experiencia móvil vs escritorio
| Elemento | Escritorio | Móvil |
|---|---|---|
| Navegación | Tabs horizontales | Select dropdown |
| Tablas | Todas las columnas | 3-4 columnas esenciales |
| FilterBar | Siempre visible | Colapsable con botón "Filtros" |
| SlideOverPanel | 40% del ancho | Full screen |
| Charts | Tamaño completo | Apilados, altura reducida |
| KpiGrid | 3-4 columnas | 2 columnas |

### Estados vacíos
Cada pantalla con datos tiene un estado vacío explícito:
- Icono temático (no genérico)
- Texto descriptivo ("Aún no hay pedidos para este período")
- Acción sugerida si aplica ("Ver pedidos de hoy")

### Estados de error
- Error de red → `ErrorBanner` con "Error al cargar. ¿Reintentar?"
- Error 403 → redirect a login (ya lo hace Flask)
- Error 500 → banner con código de error para reportar

### Loading
- Primera carga: `LoadingSkeleton` (filas grises animadas) — nunca spinner giratorio solo.
- Actualizaciones polling: no bloquear UI. Actualizar datos silenciosamente.
- Acciones (cancelar pedido, asignar): botón muestra spinner inline + disabled.

---

## Roadmap de Implementación Frontend

### MVP — Pantallas prioritarias

```
Sprint 1 (base técnica)
├── Añadir navegación por tabs al header existente
├── Crear macros Jinja2 para EmptyState, LoadingSkeleton, ErrorBanner, StatusBadge
└── Añadir Chart.js al base template (solo cuando se necesite)

Sprint 2 (historial — mayor valor)
├── Backend: endpoint /dashboard/historial-pedidos
├── Backend: endpoint /dashboard/pedido/<id>/detalle
├── Frontend: dashboard/historial.html + Alpine component
└── Frontend: SlideOverPanel con timeline de estados

Sprint 3 (turnos — operativo)
├── Backend: endpoint /dashboard/turnos/hoy
├── Backend: endpoint /dashboard/turnos/historial
├── Frontend: dashboard/turnos.html + polling para "hoy"
└── Frontend: tabla historial de turnos

Sprint 4 (rendimiento — analítico)
├── Backend: endpoint /dashboard/rendimiento
├── Backend: endpoint /dashboard/rendimiento/<id>
├── Frontend: dashboard/rendimiento.html (lista + individual)
└── Frontend: MiniBarChart con Chart.js

Sprint 5 (estadísticas — histórico)
├── Backend: endpoint /dashboard/estadisticas
├── Frontend: dashboard/estadisticas.html
└── Frontend: charts de tendencia (líneas + dona)
```

### Post-MVP

```
Sprint 6
├── Exportar CSV desde historial y estadísticas
├── Registro manual de turno (override check-in/out)
└── Filtro avanzado por cliente en historial

Sprint 7
├── Pantalla de incidencias (/dashboard/incidencias)
├── Notificaciones push en browser (si se añade SW)
└── Modo impresión para turnos (hoja de asistencia)
```

---

## Endpoints de Backend Necesarios (resumen)

Todos bajo `@requiere_rol('manager', 'admin')`:

```
# Historial
GET  /dashboard/historial-pedidos        → pedidos paginados con filtros
GET  /dashboard/pedido/<id>/detalle      → pedido completo con timeline

# Turnos
GET  /dashboard/turnos/hoy               → empleados con check-in de hoy
GET  /dashboard/turnos/historial         → turnos históricos paginados

# Rendimiento
GET  /dashboard/rendimiento              → comparativa por período
GET  /dashboard/rendimiento/<id>         → métricas individuales

# Estadísticas
GET  /dashboard/estadisticas             → series temporales + KPIs
```

El backend de métricas base ya está en `managers/gestor_dashboard.py`. Los endpoints nuevos extienden `GestorDashboard` con métodos nuevos siguiendo el mismo patrón.

---

## Notas de Implementación

- **No crear un base template nuevo**. Los templates actuales son self-contained con Tailwind CDN. Mantener ese patrón — cada pantalla incluye su propio `<head>` con los scripts que necesita.
- **Chart.js**: incluir solo en estadísticas.html y rendimiento.html. No en el bundle global.
- **Consistencia visual**: usar las mismas clases CSS (`.glass-panel`, `.soft-card`, `.metric-card`) que ya usa `dashboard/index.html`. No inventar estilos nuevos.
- **El monitor dark-mode** es la excepción. Todas las demás pantallas usan light mode con el sistema de colores actual.
- **Alpine.js store**: si los filtros de período se comparten entre rendimiento y estadísticas, considerar `Alpine.store('periodo', ...)` en lugar de duplicar estado.
