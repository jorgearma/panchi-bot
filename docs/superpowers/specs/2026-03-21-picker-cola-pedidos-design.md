# Picker — Cola de Pedidos Sin Asignar — Design Spec

## Goal

Permitir que un picker vea y reclame pedidos sin asignar directamente desde su app, sin necesidad de que el manager lo asigne manualmente.

## Context

Actualmente los pickers solo ven pedidos que el manager les ha asignado explícitamente (`PickingPedido.empleado_id = picker_id`). Los pedidos sin asignar (`empleado_id IS NULL`, `estado = 'pendiente'`) son invisibles para ellos. Esta feature añade una tab "Cola" en la app `/picker` desde la que cualquier picker puede ver esos pedidos y reclamar uno.

---

## Data Model

No se añaden tablas ni columnas. Se reutiliza `PickingPedido`:

| Campo | Valor para pedidos en cola |
|-------|---------------------------|
| `empleado_id` | `NULL` |
| `estado` | `'pendiente'` |

Un pedido "sin asignar" puede ser:
- `tipo: sin_picker` — ya tiene fila en `PickingPedido` pero sin picker asignado
- `tipo: sin_asignar` — pagado pero sin fila en `PickingPedido` todavía (creados por el webhook de pago)

**Scope de esta feature:** solo `sin_picker` (ya tienen fila). Los `sin_asignar` requieren crear la fila primero — se deja para fase futura.

---

## Architecture

```
GET /picker/cola
    → GestorDashboard.pickings_sin_asignar()
    → SELECT * FROM picking_pedido WHERE empleado_id IS NULL AND estado = 'pendiente'
    → [{picking_id, pedido_id, n_items, segundos_esperando}]

POST /picker/cola/coger/<picking_id>
    → GestorDashboard.reclamar_picking(picking_id, empleado_id)
    → UPDATE picking_pedido SET empleado_id=? WHERE id=? AND empleado_id IS NULL
    → 0 rows → (False, 'ya_cogido') → 409
    → 1 row → (True, picking)     → 200
```

---

## Backend

### `GestorDashboard.pickings_sin_asignar() -> list[dict]`

```python
def pickings_sin_asignar(self) -> list[dict]:
    """Pedidos con PickingPedido creado pero sin picker asignado."""
    s = self.session
    pickings = (
        s.query(PickingPedido)
        .filter(
            PickingPedido.empleado_id == None,
            PickingPedido.estado == EstadoPicking.PENDIENTE.value,
        )
        .order_by(PickingPedido.created_at.asc())
        .all()
    )
    ahora = datetime.utcnow()
    return [
        {
            'picking_id':         p.id,
            'pedido_id':          p.pedido_id,
            'n_items':            len(p.items),
            'segundos_esperando': int((ahora - p.created_at).total_seconds()),
        }
        for p in pickings
    ]
```

### `GestorDashboard.reclamar_picking(picking_id, empleado_id) -> tuple[bool, str]`

```python
def reclamar_picking(self, picking_id: int, empleado_id: int) -> tuple[bool, str]:
    """
    Asigna el picking al empleado de forma atómica.
    Returns: (True, 'ok') | (False, 'ya_cogido') | (False, 'no_encontrado')
    """
    s = self.session
    try:
        resultado = (
            s.query(PickingPedido)
            .filter(
                PickingPedido.id == picking_id,
                PickingPedido.empleado_id == None,
                PickingPedido.estado == EstadoPicking.PENDIENTE.value,
            )
            .update({'empleado_id': empleado_id}, synchronize_session=False)
        )
        s.commit()
        if resultado == 0:
            return False, 'ya_cogido'
        return True, 'ok'
    except SQLAlchemyError as e:
        s.rollback()
        logger.error("Error reclamando picking %s: %s", picking_id, e)
        return False, 'error'
```

---

## API Endpoints

Añadir a `blueprints/picker.py`:

### `GET /picker/cola`

- Auth: `@requiere_rol('picker', 'manager', 'admin')`
- Llama a `gestor_dashboard.pickings_sin_asignar()`
- Response 200: `{"cola": [...], "total": N}`
- Response 500: `{"error": "Error interno"}`

### `POST /picker/cola/coger/<int:picking_id>`

- Auth: `@requiere_rol('picker', 'manager', 'admin')`
- Llama a `gestor_dashboard.reclamar_picking(picking_id, session['empleado_id'])`
- Response 200: `{"ok": true, "picking_id": N}`
- Response 409: `{"error": "ya_cogido"}`
- Response 400: `{"error": "error"}` (error de BD)

---

## Frontend — `templates/picker/index.html`

### Cambios en el Alpine component

**Nuevas propiedades:**
```javascript
cola:          [],   // lista de pickings sin asignar
colaTotal:     0,
cogiendo:      null, // picking_id en proceso de reclamación
```

**Nuevo método `cargarCola()`:**
```javascript
async cargarCola() {
  try {
    const r = await fetch('/picker/cola');
    if (r.ok) {
      const d = await r.json();
      this.cola = d.cola || [];
      this.colaTotal = d.total || 0;
    }
  } catch (_) {}
},
```

**Nuevo método `cogerPedido(pickingId)`:**
```javascript
async cogerPedido(pickingId) {
  if (this.cogiendo) return;
  this.cogiendo = pickingId;
  try {
    const r = await fetch(`/picker/cola/coger/${pickingId}`, { method: 'POST' });
    if (r.ok) {
      this.cola = this.cola.filter(p => p.picking_id !== pickingId);
      this.colaTotal = Math.max(0, this.colaTotal - 1);
      await this.cargarMisPedidos();
    } else if (r.status === 409) {
      const item = this.cola.find(p => p.picking_id === pickingId);
      if (item) item.ya_cogido = true;
    }
  } catch (_) {} finally {
    this.cogiendo = null;
  }
},
```

**`init()` actualizado:**
```javascript
async init() {
  await Promise.all([this.cargarMisPedidos(), this.cargarCola()]);
},
```

### Cambios en HTML

- Nueva tab "📋 Cola" con badge rojo junto a "📦 Mis pedidos"
- Sección de cola visible solo cuando la tab está activa
- Cada fila: `Pedido #N · hace Xm · 🛒 N productos · [Coger →]`
- Estado `ya_cogido`: fila deshabilitada en rojo, botón = "Cogido"
- Estado vacío: mensaje "No hay pedidos sin asignar ahora mismo"
- Botón "↻ Actualizar" que llama a `cargarCola()`

---

## Concurrencia

El UPDATE atómico garantiza que solo un picker puede reclamar cada pedido:

```sql
UPDATE picking_pedido
SET empleado_id = ?
WHERE id = ? AND empleado_id IS NULL AND estado = 'pendiente'
```

Si `rowcount == 0` → ya fue reclamado → 409. No se necesitan locks adicionales.

---

## Testing

- `TestGestorDashboardCola::test_pickings_sin_asignar_devuelve_lista`
- `TestGestorDashboardCola::test_pickings_sin_asignar_vacio`
- `TestGestorDashboardCola::test_reclamar_picking_ok`
- `TestGestorDashboardCola::test_reclamar_picking_ya_cogido` (mock UPDATE retorna 0)
- `TestBlueprintPickerCola::test_cola_sin_sesion_rechazado`
- `TestBlueprintPickerCola::test_cola_devuelve_json`
- `TestBlueprintPickerCola::test_coger_ok`
- `TestBlueprintPickerCola::test_coger_409_ya_cogido`

---

## Out of Scope

- Pedidos `tipo: sin_asignar` (sin fila en `PickingPedido` — requieren creación previa)
- Polling automático / WebSocket en tiempo real
- Límite de pedidos simultáneos por picker
- Notificación al manager cuando un picker se auto-asigna
