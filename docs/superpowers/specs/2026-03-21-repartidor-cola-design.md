# Cola de repartos sin asignar — Diseño

**Fecha:** 2026-03-21
**Rama:** refactorizar-estructura

## Objetivo

Permitir que los repartidores elijan sus propios pedidos desde una cola de repartos pendientes, de la misma manera que los pickers reclaman pickings desde su cola.

## Cambios por capa

### 1. `managers/gestor_dashboard.py`

#### `completar_picking()` (modificación)
Cuando el picking se completa y el pedido pasa a `PREPARADO`, insertar automáticamente un `Reparto` si no existe. La inserción va **justo después del** `s.add(HistorialEstadoPedido(...))` y antes del `s.commit()`:

```python
reparto_existente = s.query(Reparto).filter_by(pedido_id=pedido_id).first()
if not reparto_existente:
    s.add(Reparto(pedido_id=pedido_id, repartidor_id=None, estado=EstadoReparto.PENDIENTE.value))
```

Si ya existe un Reparto para ese pedido (asignado manualmente desde el dashboard antes de que termine el picking), no crear uno nuevo.

**Nota:** `completar_picking()` escribe `pedido.Estado` directamente en el ORM (no vía `actualizar_estado()`). Esto es una desviación conocida de la convención del proyecto. La lógica de creación del Reparto va dentro de ese mismo bloque para mantener la atomicidad con el commit.

**Race condition:** Si `completar_picking()` y `asignar_repartidor()` corren concurrentemente y ambos encuentran que no existe Reparto, el segundo INSERT lanzará `IntegrityError` por la restricción `UNIQUE` en `pedido_id`. El bloque de creación debe capturar `IntegrityError` y tratarlo como no-op (el reparto ya fue creado por el otro hilo).

#### `repartos_sin_asignar()` (nuevo método)
Query con join a `Pedido`:
- `Reparto.repartidor_id == None`
- `Reparto.estado == EstadoReparto.PENDIENTE.value`
- `Pedido.Estado == EstadoPedido.PREPARADO.value`
- Ordenado por `Reparto.created_at` ASC

Devuelve lista de dicts:
```json
[{
  "reparto_id": 1,
  "pedido_id": 42,
  "n_items": 3,
  "direccion_entrega": "Calle Mayor 10",
  "segundos_esperando": 180
}]
```

`direccion_entrega` se obtiene de `Pedido.DireccionEntrega` (columna real en la tabla `pedidos`).

#### `reclamar_reparto(reparto_id, empleado_id)` (nuevo método)
UPDATE atómico sobre `Reparto` filtrando `id=reparto_id AND repartidor_id IS NULL AND estado=PENDIENTE`:
- Asigna `repartidor_id = empleado_id`
- Cambia `estado = ASIGNADO`

Tras éxito, llamar `self._actualizar_estado_operativo(empleado_id, 'ocupado')` (igual que `reclamar_picking()`).

Retorna:
- `(True, 'ok')` — asignado correctamente
- `(False, 'no_encontrado')` — reparto_id no existe
- `(False, 'ya_cogido')` — otro repartidor se adelantó (rowcount == 0)
- `(False, 'error')` — error de BD

### 2. `blueprints/repartidor.py`

#### `GET /repartidor/cola`
- Decoradores: `@requiere_rol('repartidor', 'manager', 'admin')`
- Llama `gestor_dashboard.repartos_sin_asignar()`
- Responde `{"cola": [...], "total": N}`

#### `POST /repartidor/cola/coger/<int:reparto_id>`
- Decoradores: `@requiere_rol('repartidor', 'manager', 'admin')`
- Llama `gestor_dashboard.reclamar_reparto(reparto_id, empleado_id)`
- Códigos de respuesta:
  - 200 `{"ok": true, "reparto_id": N}`
  - 404 `{"error": "no_encontrado"}`
  - 409 `{"error": "ya_cogido"}`
  - 400 `{"error": "error"}`

### 3. `templates/repartidor/index.html`

Añadir tab "Cola" junto al tab "Mis pedidos" existente, con:
- Contador de repartos disponibles (badge rojo)
- Lista de cards por reparto: dirección, tiempo en espera, número de items
- Botón "Coger →" por card (disabled durante petición en vuelo)
- Estado `ya_cogido` con feedback visual si otro se adelanta
- Botón "Actualizar" manual
- Estado vacío: "No hay pedidos sin asignar ahora mismo"

La lógica JS sigue el mismo patrón Alpine.js que `picker/index.html`:
- `cola[]`, `colaTotal`, `cogiendo` (reparto_id en vuelo)
- `cargarCola()` — fetch GET /repartidor/cola
- `cogerReparto(reparto_id)` — fetch POST /repartidor/cola/coger/:id

## Estados implicados

```
EstadoReparto.PENDIENTE  → (reclamar_reparto) → EstadoReparto.ASIGNADO
```

El repartidor ve el reparto en "Mis pedidos" tras reclamarlo (ya existe `repartos_del_repartidor` que incluye ASIGNADO).

## Compatibilidad con dashboard

El dashboard puede seguir asignando repartidores manualmente. `asignar_repartidor()` ya crea o actualiza el Reparto con el empleado_id directamente — esos repartos nunca pasan por la cola.

## Tests a añadir en `tests/test_repartidor.py`

- `test_repartos_sin_asignar` — devuelve repartos con `repartidor_id=None` y pedido en PREPARADO
- `test_repartos_sin_asignar_excluye_asignados` — no devuelve repartos ya asignados
- `test_reclamar_reparto_ok` — asigna correctamente
- `test_reclamar_reparto_ya_cogido` — devuelve `(False, 'ya_cogido')` si rowcount == 0
- `test_reclamar_reparto_no_encontrado` — devuelve `(False, 'no_encontrado')`
- `test_completar_picking_crea_reparto` — tras completar picking, existe Reparto con `repartidor_id=None`
- `test_completar_picking_no_duplica_reparto` — si ya existe Reparto, no crea uno nuevo
