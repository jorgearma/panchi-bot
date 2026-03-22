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
- `tipo: sin_asignar` — pagado pero sin fila en `PickingPedido` todavía

**Scope de esta feature:** solo `sin_picker` (ya tienen fila). Los `sin_asignar` requieren crear la fila primero — se deja para fase futura.

---

## Architecture

```
GET /picker/cola
    → GestorDashboard.pickings_sin_asignar()
    → SELECT pp.* FROM picking_pedido pp
        JOIN pedidos p ON p.PedidoID = pp.pedido_id
        WHERE pp.empleado_id IS NULL
          AND pp.estado = 'pendiente'
          AND p.Estado IN ('Pagado', 'contra_reembolso', 'en_preparacion')
    → [{picking_id, pedido_id, n_items, segundos_esperando}]

POST /picker/cola/coger/<picking_id>
    → GestorDashboard.reclamar_picking(picking_id, empleado_id)
    → 1. Consulta previa por id solo → (False, 'no_encontrado') si no existe
    → 2. UPDATE atómico WHERE id=? AND empleado_id IS NULL AND estado='pendiente'
    → 0 rows → (False, 'ya_cogido') → 409
    → 1 row  → (True, 'ok')        → 200
```

---

## Backend

### `GestorDashboard.pickings_sin_asignar() -> list[dict]`

Filtra por `PickingPedido.empleado_id IS NULL` y `estado='pendiente'`, y además hace join con `Pedido` para excluir pickings de pedidos ya cancelados o reembolsados.

```python
def pickings_sin_asignar(self) -> list[dict]:
    """Pedidos con PickingPedido creado pero sin picker asignado.
    Solo incluye pedidos en estado activo (Pagado, contra_reembolso, en_preparacion).
    """
    from models import Pedido as _Pedido
    s = self.session
    estados_activos = [
        EstadoPedido.PAGADO.value,
        EstadoPedido.CONTRA_REEMBOLSO.value,
        EstadoPedido.EN_PREPARACION.value,
    ]
    pickings = (
        s.query(PickingPedido)
        .join(_Pedido, _Pedido.PedidoID == PickingPedido.pedido_id)
        .filter(
            PickingPedido.empleado_id == None,
            PickingPedido.estado == EstadoPicking.PENDIENTE.value,
            _Pedido.Estado.in_(estados_activos),
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

Primero verifica existencia, luego hace el UPDATE atómico. El `s.commit()` dentro del método sigue el patrón establecido en este manager (ver `completar_picking`, `marcar_entregado`).

Tras reclamar con éxito, llama a `_actualizar_estado_operativo(empleado_id)` para mantener consistencia con el panel de monitor.

```python
def reclamar_picking(self, picking_id: int, empleado_id: int) -> tuple[bool, str]:
    """
    Asigna el picking al empleado de forma atómica.
    Returns:
        (True,  'ok')           — asignado correctamente
        (False, 'no_encontrado') — picking_id no existe
        (False, 'ya_cogido')    — empleado_id IS NOT NULL o estado != pendiente
        (False, 'error')        — error de BD
    """
    s = self.session
    try:
        # 1. Verificar existencia antes del UPDATE para dar error preciso
        picking = s.query(PickingPedido).filter_by(id=picking_id).first()
        if not picking:
            return False, 'no_encontrado'

        # 2. UPDATE atómico — solo actualiza si sigue libre
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

        # 3. Actualizar estado operativo del picker (igual que en completar_picking)
        self._actualizar_estado_operativo(empleado_id)
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
- No body
- Llama a `gestor_dashboard.pickings_sin_asignar()`
- Response 200: `{"cola": [...], "total": N}`
- Response 500: `{"error": "Error interno"}`

### `POST /picker/cola/coger/<int:picking_id>`

- Auth: `@requiere_rol('picker', 'manager', 'admin')`
- No body — `picking_id` viene de la URL, `empleado_id` de `session['empleado_id']`
- Sin CSRF adicional — el blueprint no tiene middleware CSRF, igual que todos los demás endpoints POST de `/picker`
- Response 200: `{"ok": true, "picking_id": N}`
- Response 404: `{"error": "no_encontrado"}`
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
tabActiva:     'mis-pedidos',  // 'mis-pedidos' | 'cola'
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

**Polling:** `cargarCola()` se añade al ciclo de polling existente junto a `cargarMisPedidos()`, para que la cola se refresque automáticamente al mismo ritmo. No es polling independiente — reutiliza el intervalo ya configurado.

### Cambios en HTML

- Nueva tab "📋 Cola" con badge rojo junto a "📦 Mis pedidos"
- Las secciones se muestran/ocultan según `tabActiva`
- Cada fila cola: `Pedido #N · hace Xm · 🛒 N productos · [Coger →]`
- Estado `ya_cogido`: fila deshabilitada en rojo, botón = "Cogido"
- Estado vacío: "No hay pedidos sin asignar ahora mismo"
- Botón "↻ Actualizar" que llama a `cargarCola()`

---

## Concurrencia

El UPDATE atómico garantiza que solo un picker puede reclamar cada pedido:

```sql
UPDATE picking_pedido
SET empleado_id = ?
WHERE id = ? AND empleado_id IS NULL AND estado = 'pendiente'
```

Si `rowcount == 0` → el picking ya no estaba libre → 409. No se necesitan locks adicionales a nivel de aplicación.

---

## Testing

- `TestGestorDashboardCola::test_pickings_sin_asignar_devuelve_lista`
- `TestGestorDashboardCola::test_pickings_sin_asignar_excluye_pedido_cancelado`
- `TestGestorDashboardCola::test_pickings_sin_asignar_vacio`
- `TestGestorDashboardCola::test_reclamar_picking_ok`
- `TestGestorDashboardCola::test_reclamar_picking_ya_cogido` (mock UPDATE retorna 0)
- `TestGestorDashboardCola::test_reclamar_picking_no_encontrado`
- `TestBlueprintPickerCola::test_cola_sin_sesion_rechazado`
- `TestBlueprintPickerCola::test_cola_devuelve_json`
- `TestBlueprintPickerCola::test_coger_ok`
- `TestBlueprintPickerCola::test_coger_409_ya_cogido`
- `TestBlueprintPickerCola::test_coger_404_no_encontrado`

---

## Out of Scope

- Pedidos `tipo: sin_asignar` (sin fila en `PickingPedido`)
- Polling independiente para la cola (se reutiliza el ciclo existente)
- WebSocket / push en tiempo real
- Límite de pedidos simultáneos por picker
- Notificación al manager cuando un picker se auto-asigna
