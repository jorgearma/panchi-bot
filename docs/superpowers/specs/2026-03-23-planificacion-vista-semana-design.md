# Spec: Vista Semana en Planificación de Turnos

**Fecha:** 2026-03-23
**Estado:** Aprobado

---

## Objetivo

Añadir una vista de cuadrícula semanal a la tab de Planificación del dashboard de turnos, que permita ver de un vistazo los turnos de todos los empleados por día, navegar entre semanas y crear turnos directamente desde las celdas vacías.

---

## Contexto

La tab de Planificación actualmente muestra una tabla plana (fecha, empleado, horario, estado) con paginación de 25 filas. Con muchos empleados y varios días por delante, es difícil distinguir la cobertura por día y detectar huecos. La vista semana soluciona esto.

---

## Diseño

### Toggle de vista

En la cabecera de la tab, junto al botón "+ Nuevo turno", aparecen dos botones de vista:

```
[ ≡ Tabla ]  [ ▦ Semana ]                    + Nuevo turno
```

El botón activo tiene fondo azul. El botón inactivo es gris/outline.

### Vista semana

#### Navegación

```
← Anterior    Lun 23 — Dom 29 mar 2026    Siguiente →
```

Las flechas desplazan la semana visible ±7 días y recargan datos.

#### Cuadrícula

- **Columna izquierda fija:** nombre del empleado
- **7 columnas:** Lun, Mar, Mié, Jue, Vie, Sáb, Dom con fecha en la cabecera
- **Cabecera de hoy** destacada con fondo azul suave (`bg-blue-50 text-blue-700`)
- Solo aparecen en la cuadrícula los **empleados que tienen al menos un turno** en la semana visible
- Si ningún empleado tiene turno esa semana se muestra: `{{ empty_state('📅', 'Sin turnos', 'Sin turnos esta semana. Pulsa + en cualquier celda para crear uno.') }}`. Condición Alpine: `!planCargando && empleadosSemana().length === 0`

#### Celdas con turno

Un empleado puede tener **más de un turno en el mismo día** (ej. turno partido). La celda muestra todos los chips apilados verticalmente, uno por turno. Cada chip es compacto con el horario y color según tipo:

| Tipo     | Color                             |
|----------|-----------------------------------|
| mañana   | `bg-blue-100 text-blue-700`       |
| tarde    | `bg-amber-100 text-amber-700`     |
| noche    | `bg-indigo-100 text-indigo-700`   |
| partido  | `bg-emerald-100 text-emerald-700` |
| sin tipo | `bg-slate-100 text-slate-600`     |

Contenido de cada chip: `09:00–17:00`

#### Celdas vacías

Botón `+` tenue (`text-slate-300 hover:text-blue-500`) que al pulsarse abre el modal de crear turno con el campo empleado y la fecha ya pre-rellenados.

#### Paginación

Oculta en modo semana. En modo semana se carga siempre la semana completa.

---

## Cambios técnicos

### Backend

Un cambio mínimo requerido: elevar el cap de `per_page` en el blueprint de 100 a 200 para soportar la carga semanal completa.

```python
# blueprints/dashboard.py línea 312
per_page = min(int(request.args.get('per_page', 25)), 200)  # era 100
```

El endpoint se reutiliza sin más cambios:

```
GET /dashboard/turnos/planificacion?desde=YYYY-MM-DD&hasta=YYYY-MM-DD&per_page=200
```

Con `desde` = lunes de la semana y `hasta` = domingo de la misma semana.

### Frontend — Alpine.js (`turnosApp`)

Nuevas propiedades de estado:

```js
vistaGrid: false,          // false = tabla, true = semana
semanaBase: null,          // Date object del lunes de la semana visible; se inicializa en init() al lunes de la fecha actual
```

`semanaBase` se inicializa en `init()` al lunes de `new Date()`. No persiste entre recargas de página — al recargar siempre arranca en la semana actual.

Nuevos helpers:

- `lunes(date)` → Date del lunes de la semana que contiene `date`
- `diasSemana()` → array de 7 Date objects [lun…dom] a partir de `semanaBase`
- `semanaLabel()` → string con formato "Lun 23 — Dom 29 mar 2026"; si la semana cruza dos meses se incluye el mes en ambos extremos: "Lun 28 feb — Dom 6 mar 2026"
- `esHoy(date)` → bool para destacar columna
- `semanaTurnos()` → dict `{ empleado_id: { 'YYYY-MM-DD': turno[] } }` — valor es **array** para soportar múltiples turnos el mismo día
- `empleadosSemana()` → lista única de `{ id, nombre }` de empleados con turno en la semana
- `formatISO(date)` → string `YYYY-MM-DD` a partir de un Date object; usado en el template para convertir cada entrada de `diasSemana()` en clave del dict antes de hacer el lookup

Comportamiento del toggle:
- Al activar modo semana: se dispara `cargarPlan()` con los parámetros de semana; `semanaBase` mantiene la última semana visitada (no se resetea al volver al modo tabla y regresar)
- Al activar modo tabla: se resetea `planPage = 1` y se dispara `cargarPlan()` con los parámetros de tabla actuales (`planFiltros`)
- Cada cambio de modo dispara exactamente una llamada a red

Cambios en `cargarPlan()`:
- Es el único punto de entrada para cargar datos de planificación; `cargar()` no necesita cambios porque ya llama a `cargarPlan()` cuando `tab === 'plan'`, y `cargarPlan()` ramificará internamente según `vistaGrid`
- En modo `vistaGrid`: `desde` = lunes formateado `YYYY-MM-DD`, `hasta` = domingo, `per_page=200`, `page=1` (puede omitirse ya que el backend lo defaultea a 1)
- En modo tabla: comportamiento actual sin cambios

Cambio en `abrirModalCrear(empleadoId?, fecha?)`:
- La función sigue siendo `async` y llama a `_cargarEmpleados()` antes de abrir el modal (sin cambio estructural)
- Si se pasan `empleadoId` y `fecha`, se asignan a `form.empleado_id` y `form.fecha` **después** de la inicialización del form y **después** de `_cargarEmpleados()`, sobreescribiendo el fallback de `planFiltros.desde`
- Compatibilidad hacia atrás: llamada sin argumentos funciona igual que ahora

Los claves del dict `semanaTurnos()` son **strings** (`String(empleado_id)`), consistente con la coerción automática de claves en objetos JS. El template usa `semanaTurnos()[String(emp.id)][fecha] || []`.

Estado de carga en vista semana: reutilizar el bloque `x-show="planCargando"` existente con el mismo `loading_skeleton(rows=5, cols=5)` — es suficiente para indicar carga mientras llegan los datos.

### Template — `templates/dashboard/turnos.html`

1. Reemplazar bloque de filtros + tabla de Planificación por:
   - Barra de cabecera con toggle vista + botón nuevo turno
   - Bloque de navegación semanal (solo visible en `vistaGrid`)
   - Filtros de fecha/rol (solo visibles en modo tabla)
   - Vista tabla: sin cambios funcionales
   - Vista semana: `<table>` con `<thead>` de días y `<tbody>` de empleados × días; cada celda itera sobre `semanaTurnos()[String(emp.id)][formatISO(dia)] || []`

---

## Criterios de éxito

- La cuadrícula muestra correctamente los turnos de la semana actual al activarse por primera vez
- Empleados con dos turnos el mismo día muestran dos chips apilados en la misma celda
- Las flechas de navegación cargan la semana anterior/siguiente sin errores
- Las celdas vacías muestran `+` y al pulsarlo el modal se abre con empleado y fecha pre-rellenos
- Semanas sin ningún turno muestran el `empty_state` con mensaje apropiado
- Al volver al modo semana después de usar la tabla, se muestra la última semana visitada
- El modo tabla sigue funcionando igual que antes
- `per_page=200` se sirve correctamente (cap elevado a 200 en blueprint)
