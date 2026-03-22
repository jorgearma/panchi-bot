# Picker — Cola de Pedidos Sin Asignar — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir tab "Cola" en `/picker` para que un picker pueda ver pedidos sin asignar y reclamar uno con un tap, sin intervención del manager.

**Architecture:** Dos nuevos métodos en `GestorDashboard` (`pickings_sin_asignar`, `reclamar_picking`) + dos endpoints en `blueprints/picker.py` + tab Cola en `templates/picker/index.html` con Alpine.js. El UPDATE atómico en SQL garantiza que solo un picker puede reclamar cada pedido.

**Tech Stack:** Python/Flask, SQLAlchemy 2.x (SQL Server), Alpine.js 3, Tailwind CSS, pytest+unittest.mock

---

## File Map

| Acción | Archivo | Qué cambia |
|--------|---------|------------|
| Modificar | `managers/gestor_dashboard.py` | Añadir `pickings_sin_asignar()` y `reclamar_picking()` (al final de la clase) |
| Modificar | `blueprints/picker.py` | Añadir `GET /picker/cola` y `POST /picker/cola/coger/<picking_id>` (al final del fichero) |
| Modificar | `templates/picker/index.html` | Nueva tab + métodos Alpine `cargarCola()` y `cogerPedido()` + sección HTML Cola |
| Crear | `tests/test_picker_cola.py` | Tests unitarios de manager + tests de blueprint |

---

## Task 1: `GestorDashboard` — métodos backend

**Files:**
- Modify: `managers/gestor_dashboard.py` (al final de la clase)
- Create: `tests/test_picker_cola.py`

- [ ] **Step 1: Crear fichero de tests y escribir tests del manager (deben fallar)**

```python
# tests/test_picker_cola.py
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from sqlalchemy.exc import SQLAlchemyError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_session(manager):
    """Parchea la propiedad session de GestorDashboard con un mock."""
    patcher = patch.object(type(manager), 'session', new_callable=PropertyMock)
    mock_prop = patcher.start()
    mock_sess = MagicMock()
    mock_prop.return_value = mock_sess
    return patcher, mock_sess


# ---------------------------------------------------------------------------
# TestGestorDashboardCola
# ---------------------------------------------------------------------------

class TestGestorDashboardCola:

    def setup_method(self):
        from services import gestor_dashboard
        self.gd = gestor_dashboard

    def test_pickings_sin_asignar_devuelve_lista(self, app):
        from datetime import datetime, timedelta
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                mock_picking = MagicMock()
                mock_picking.id = 1
                mock_picking.pedido_id = 100
                mock_picking.items = [MagicMock(), MagicMock()]
                mock_picking.created_at = datetime.utcnow() - timedelta(minutes=5)

                mock_q = MagicMock()
                mock_q.join.return_value = mock_q
                mock_q.filter.return_value = mock_q
                mock_q.order_by.return_value = mock_q
                mock_q.all.return_value = [mock_picking]
                mock_sess.query.return_value = mock_q

                result = self.gd.pickings_sin_asignar()

                assert len(result) == 1
                assert result[0]['picking_id'] == 1
                assert result[0]['pedido_id'] == 100
                assert result[0]['n_items'] == 2
                assert result[0]['segundos_esperando'] >= 0
            finally:
                patcher.stop()

    def test_pickings_sin_asignar_vacio(self, app):
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                mock_q = MagicMock()
                mock_q.join.return_value = mock_q
                mock_q.filter.return_value = mock_q
                mock_q.order_by.return_value = mock_q
                mock_q.all.return_value = []
                mock_sess.query.return_value = mock_q

                result = self.gd.pickings_sin_asignar()
                assert result == []
            finally:
                patcher.stop()

    def test_pickings_sin_asignar_excluye_pedido_cancelado(self, app):
        """Verifica que el query filtra por estados_activos — no hay modo de testear
        el filtro sin BD, pero sí que el método llama a .join() y .filter()."""
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                mock_q = MagicMock()
                mock_q.join.return_value = mock_q
                mock_q.filter.return_value = mock_q
                mock_q.order_by.return_value = mock_q
                mock_q.all.return_value = []
                mock_sess.query.return_value = mock_q

                self.gd.pickings_sin_asignar()

                assert mock_q.join.called, "Debe hacer JOIN con Pedido"
                assert mock_q.filter.called, "Debe filtrar por estado y empleado_id"
            finally:
                patcher.stop()

    def test_reclamar_picking_ok(self, app):
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                mock_picking = MagicMock()
                mock_picking.id = 7

                # Primera query: existencia check
                # Segunda query: UPDATE atómico
                mock_q_exist = MagicMock()
                mock_q_exist.filter_by.return_value = mock_q_exist
                mock_q_exist.first.return_value = mock_picking

                mock_q_update = MagicMock()
                mock_q_update.filter.return_value = mock_q_update
                mock_q_update.update.return_value = 1   # 1 row updated

                mock_sess.query.side_effect = [mock_q_exist, mock_q_update]

                with patch.object(self.gd, '_actualizar_estado_operativo') as mock_aso:
                    ok, msg = self.gd.reclamar_picking(7, empleado_id=3)

                assert ok is True
                assert msg == 'ok'
                mock_aso.assert_called_once_with(3, 'ocupado')
            finally:
                patcher.stop()

    def test_reclamar_picking_no_encontrado(self, app):
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                mock_q = MagicMock()
                mock_q.filter_by.return_value = mock_q
                mock_q.first.return_value = None
                mock_sess.query.return_value = mock_q

                ok, msg = self.gd.reclamar_picking(999, empleado_id=3)

                assert ok is False
                assert msg == 'no_encontrado'
            finally:
                patcher.stop()

    def test_reclamar_picking_ya_cogido(self, app):
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                mock_picking = MagicMock()
                mock_picking.id = 7

                mock_q_exist = MagicMock()
                mock_q_exist.filter_by.return_value = mock_q_exist
                mock_q_exist.first.return_value = mock_picking

                mock_q_update = MagicMock()
                mock_q_update.filter.return_value = mock_q_update
                mock_q_update.update.return_value = 0  # 0 rows = ya cogido

                mock_sess.query.side_effect = [mock_q_exist, mock_q_update]

                ok, msg = self.gd.reclamar_picking(7, empleado_id=3)

                assert ok is False
                assert msg == 'ya_cogido'
            finally:
                patcher.stop()
```

- [ ] **Step 2: Ejecutar tests para confirmar que fallan**

```bash
cd /home/siemprearmando/proyectos/panchi-bot && venv/bin/pytest tests/test_picker_cola.py -v --tb=short 2>&1 | head -40
```

Expected: `AttributeError` o `ImportError` — los métodos no existen aún.

- [ ] **Step 3: Implementar `pickings_sin_asignar` y `reclamar_picking` en `GestorDashboard`**

Añadir al final de la clase `GestorDashboard` en `managers/gestor_dashboard.py`, justo antes del último cierre de clase (o al final del fichero si la clase llega hasta el final):

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

    def reclamar_picking(self, picking_id: int, empleado_id: int) -> tuple[bool, str]:
        """
        Asigna el picking al empleado de forma atómica.
        Returns:
            (True,  'ok')            — asignado correctamente
            (False, 'no_encontrado') — picking_id no existe
            (False, 'ya_cogido')     — otro picker se adelantó (rowcount == 0)
            (False, 'error')         — error de BD
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

            # 3. Actualizar estado operativo del picker
            self._actualizar_estado_operativo(empleado_id, 'ocupado')
            return True, 'ok'

        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error reclamando picking %s: %s", picking_id, e)
            return False, 'error'
```

- [ ] **Step 4: Ejecutar tests del manager para confirmar que pasan**

```bash
cd /home/siemprearmando/proyectos/panchi-bot && venv/bin/pytest tests/test_picker_cola.py::TestGestorDashboardCola -v --tb=short
```

Expected: 6 tests PASSED.

- [ ] **Step 5: Ejecutar suite completa para confirmar sin regresiones**

```bash
cd /home/siemprearmando/proyectos/panchi-bot && venv/bin/pytest -v --tb=short 2>&1 | tail -20
```

Expected: todos los tests pre-existentes pasan (3 `TestWebhookMonei` siguen fallando — eso es conocido y esperado).

- [ ] **Step 6: Commit**

```bash
cd /home/siemprearmando/proyectos/panchi-bot && git add managers/gestor_dashboard.py tests/test_picker_cola.py && git commit -m "feat: add pickings_sin_asignar and reclamar_picking to GestorDashboard"
```

---

## Task 2: Endpoints `GET /picker/cola` y `POST /picker/cola/coger/<picking_id>`

**Files:**
- Modify: `blueprints/picker.py` (añadir al final)
- Modify: `tests/test_picker_cola.py` (añadir clase `TestBlueprintPickerCola`)

- [ ] **Step 1: Añadir tests de blueprint al fichero existente**

Añadir al final de `tests/test_picker_cola.py`:

```python
# ---------------------------------------------------------------------------
# TestBlueprintPickerCola
# ---------------------------------------------------------------------------

class TestBlueprintPickerCola:

    def test_cola_sin_sesion_rechazado(self, client):
        resp = client.get('/picker/cola')
        # Redirige al login si no hay sesión
        assert resp.status_code in (302, 401, 403)

    def test_cola_devuelve_json(self, client, app):
        from unittest.mock import patch
        from services import gestor_dashboard

        with client.session_transaction() as sess:
            sess['empleado_id'] = 1
            sess['rol'] = 'picker'

        with patch.object(gestor_dashboard, 'pickings_sin_asignar', return_value=[
            {'picking_id': 5, 'pedido_id': 200, 'n_items': 3, 'segundos_esperando': 120}
        ]):
            resp = client.get('/picker/cola')

        assert resp.status_code == 200
        data = resp.get_json()
        assert 'cola' in data
        assert 'total' in data
        assert data['total'] == 1
        assert data['cola'][0]['picking_id'] == 5

    def test_coger_ok(self, client, app):
        from unittest.mock import patch
        from services import gestor_dashboard

        with client.session_transaction() as sess:
            sess['empleado_id'] = 3
            sess['rol'] = 'picker'

        with patch.object(gestor_dashboard, 'reclamar_picking', return_value=(True, 'ok')) as mock_rec:
            resp = client.post('/picker/cola/coger/7')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert data['picking_id'] == 7
        mock_rec.assert_called_once_with(7, 3)

    def test_coger_409_ya_cogido(self, client, app):
        from unittest.mock import patch
        from services import gestor_dashboard

        with client.session_transaction() as sess:
            sess['empleado_id'] = 3
            sess['rol'] = 'picker'

        with patch.object(gestor_dashboard, 'reclamar_picking', return_value=(False, 'ya_cogido')):
            resp = client.post('/picker/cola/coger/7')

        assert resp.status_code == 409
        assert resp.get_json()['error'] == 'ya_cogido'

    def test_coger_404_no_encontrado(self, client, app):
        from unittest.mock import patch
        from services import gestor_dashboard

        with client.session_transaction() as sess:
            sess['empleado_id'] = 3
            sess['rol'] = 'picker'

        with patch.object(gestor_dashboard, 'reclamar_picking', return_value=(False, 'no_encontrado')):
            resp = client.post('/picker/cola/coger/999')

        assert resp.status_code == 404
        assert resp.get_json()['error'] == 'no_encontrado'
```

- [ ] **Step 2: Ejecutar tests para confirmar que fallan**

```bash
cd /home/siemprearmando/proyectos/panchi-bot && venv/bin/pytest tests/test_picker_cola.py::TestBlueprintPickerCola -v --tb=short 2>&1 | head -30
```

Expected: 404 o error — las rutas no existen aún.

- [ ] **Step 3: Añadir los dos endpoints al final de `blueprints/picker.py`**

```python
@blueprint_picker.route("/picker/cola")
@requiere_rol('picker', 'manager', 'admin')
def cola():
    try:
        lista = gestor_dashboard.pickings_sin_asignar()
        return jsonify({"cola": lista, "total": len(lista)})
    except Exception as e:
        logger.error("Error en /picker/cola: %s", e)
        return jsonify({"error": "Error interno"}), 500


@blueprint_picker.route("/picker/cola/coger/<int:picking_id>", methods=["POST"])
@requiere_rol('picker', 'manager', 'admin')
def coger_picking(picking_id: int):
    empleado_id = session.get('empleado_id')
    ok, motivo = gestor_dashboard.reclamar_picking(picking_id, empleado_id)
    if ok:
        return jsonify({"ok": True, "picking_id": picking_id})
    if motivo == 'no_encontrado':
        return jsonify({"error": motivo}), 404
    if motivo == 'ya_cogido':
        return jsonify({"error": motivo}), 409
    return jsonify({"error": motivo}), 400
```

- [ ] **Step 4: Ejecutar tests de blueprint para confirmar que pasan**

```bash
cd /home/siemprearmando/proyectos/panchi-bot && venv/bin/pytest tests/test_picker_cola.py::TestBlueprintPickerCola -v --tb=short
```

Expected: 5 tests PASSED.

- [ ] **Step 5: Ejecutar suite completa**

```bash
cd /home/siemprearmando/proyectos/panchi-bot && venv/bin/pytest -v --tb=short 2>&1 | tail -20
```

Expected: todos los tests pre-existentes pasan (3 `TestWebhookMonei` siguen fallando — conocido).

- [ ] **Step 6: Commit**

```bash
cd /home/siemprearmando/proyectos/panchi-bot && git add blueprints/picker.py tests/test_picker_cola.py && git commit -m "feat: add GET /picker/cola and POST /picker/cola/coger endpoints"
```

---

## Task 3: Frontend — Tab Cola en `templates/picker/index.html`

**Files:**
- Modify: `templates/picker/index.html`

No hay tests de integración para la UI — se verifica manualmente. Los cambios se dividen en tres partes: (A) nuevas propiedades + métodos Alpine, (B) actualización de `init()` y polling, (C) HTML de la nueva tab.

### Parte A — Nuevas propiedades y métodos Alpine

- [ ] **Step 1: Añadir propiedades nuevas al return del componente**

Localizar en `templates/picker/index.html` el bloque de propiedades del componente (alrededor de línea 592). Justo después de `confirmarFinalizar: false,`, añadir:

```javascript
        // ---- Cola de pedidos sin asignar ----
        cola:          [],
        colaTotal:     0,
        cogiendo:      null,   // picking_id en proceso de reclamación
        tabActiva:     'mis-pedidos',  // 'mis-pedidos' | 'cola'
```

- [ ] **Step 2: Añadir métodos `cargarCola()` y `cogerPedido()` en la sección `// ---- Data ----`**

Localizar el método `recargar()` (línea ~666). Justo después del cierre de `recargar()`, añadir:

```javascript
        async cargarCola() {
          try {
            const r = await fetch('/picker/cola');
            if (r.ok) {
              const d = await r.json();
              this.cola      = d.cola  || [];
              this.colaTotal = d.total || 0;
            }
          } catch (_) {}
        },

        async cogerPedido(pickingId) {
          if (this.cogiendo) return;
          this.cogiendo = pickingId;
          try {
            const r = await fetch(`/picker/cola/coger/${pickingId}`, { method: 'POST' });
            if (r.ok) {
              this.cola      = this.cola.filter(p => p.picking_id !== pickingId);
              this.colaTotal = Math.max(0, this.colaTotal - 1);
              await this.recargar();
            } else if (r.status === 409) {
              const item = this.cola.find(p => p.picking_id === pickingId);
              if (item) item.ya_cogido = true;
            }
          } catch (_) {} finally {
            this.cogiendo = null;
          }
        },
```

### Parte B — Actualizar `init()` y el polling

- [ ] **Step 3: Actualizar `init()` para cargar cola en paralelo**

Localizar en `init()`:
```javascript
          await this.recargar();
          setInterval(() => {
            if (this.vistaActual === 'lista') this.recargar();
          }, 60000);
```

Reemplazar con:
```javascript
          await Promise.all([this.recargar(), this.cargarCola()]);
          setInterval(() => {
            if (this.vistaActual === 'lista') {
              this.recargar();
              this.cargarCola();
            }
          }, 60000);
```

### Parte C — HTML de la nueva tab

- [ ] **Step 4: Añadir selector de tabs en el header del área lista**

Localizar la sección `<!-- ======== VISTA LISTA ======== -->` (línea ~79). Dentro del `<div x-show="pickerId && !cargando && vistaActual === 'lista'" x-cloak>`, **antes** del bloque `<div x-show="pedidos.length === 0"`, insertar el selector de tabs y la sección de cola completa:

```html
    <!-- ---- Tabs ---- -->
    <div class="flex border-b-2 border-gray-800 sticky top-[52px] z-20 bg-gray-100">
      <button @click="tabActiva = 'mis-pedidos'"
              class="flex-1 text-center py-3 text-sm font-medium transition"
              :class="tabActiva === 'mis-pedidos'
                ? 'text-blue-400 border-b-2 border-blue-500 -mb-[2px]'
                : 'text-gray-500'">
        📦 Mis pedidos
        <span x-show="pedidos.length > 0"
              class="ml-1.5 bg-gray-700 text-gray-300 text-xs rounded-full px-2 py-0.5"
              x-text="pedidos.length"></span>
      </button>
      <button @click="tabActiva = 'cola'"
              class="flex-1 text-center py-3 text-sm font-medium transition"
              :class="tabActiva === 'cola'
                ? 'text-blue-400 border-b-2 border-blue-500 -mb-[2px]'
                : 'text-gray-500'">
        📋 Cola
        <span x-show="colaTotal > 0"
              class="ml-1.5 bg-red-600 text-white text-xs rounded-full px-2 py-0.5"
              x-text="colaTotal"></span>
      </button>
    </div>

    <!-- ---- Sección Cola ---- -->
    <div x-show="tabActiva === 'cola'" x-cloak class="p-4">

      <!-- Cabecera -->
      <div class="flex justify-between items-center mb-3">
        <p class="text-sm font-semibold text-green-400"
           x-text="colaTotal + ' pedido' + (colaTotal !== 1 ? 's' : '') + ' disponible' + (colaTotal !== 1 ? 's' : '')"></p>
        <button @click="cargarCola()"
                class="bg-gray-800 text-gray-400 text-xs px-3 py-1.5 rounded-lg active:bg-gray-700 transition">
          ↻ Actualizar
        </button>
      </div>

      <!-- Lista -->
      <div x-show="cola.length > 0" class="space-y-3">
        <template x-for="p in cola" :key="p.picking_id">
          <div class="bg-gray-800 rounded-2xl p-4 flex justify-between items-center slide-up"
               :class="p.ya_cogido ? 'opacity-40' : ''">
            <div>
              <div class="font-bold text-white text-sm">Pedido #<span x-text="p.pedido_id"></span></div>
              <div class="text-xs mt-1" :class="p.ya_cogido ? 'text-red-400' : 'text-gray-500'">
                <span x-show="!p.ya_cogido"
                      x-text="'hace ' + (p.segundos_esperando < 60
                        ? p.segundos_esperando + 's'
                        : Math.floor(p.segundos_esperando / 60) + 'min') + ' · 🛒 ' + p.n_items + ' productos'"></span>
                <span x-show="p.ya_cogido">Ya cogido por otro picker</span>
              </div>
            </div>
            <button @click="cogerPedido(p.picking_id)"
                    :disabled="p.ya_cogido || cogiendo !== null"
                    class="text-sm font-bold px-4 py-2 rounded-xl transition tap-xl"
                    :class="p.ya_cogido
                      ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
                      : 'bg-blue-600 text-white active:bg-blue-700'">
              <span x-show="!p.ya_cogido && cogiendo !== p.picking_id">Coger →</span>
              <span x-show="p.ya_cogido">Cogido</span>
              <span x-show="cogiendo === p.picking_id && !p.ya_cogido">...</span>
            </button>
          </div>
        </template>
      </div>

      <!-- Vacía -->
      <div x-show="cola.length === 0"
           class="flex flex-col items-center justify-center py-16 text-center px-6">
        <div class="text-5xl mb-3">📋</div>
        <p class="text-gray-500 text-sm">No hay pedidos sin asignar ahora mismo</p>
      </div>

    </div>
```

- [ ] **Step 5: Añadir `x-show="tabActiva === 'mis-pedidos'"` a los bloques de "Mis pedidos"**

Localizar los dos divs de la sección mis-pedidos (el de lista vacía y el de lista con pedidos):

```html
    <div x-show="pedidos.length === 0"
```
Reemplazar con:
```html
    <div x-show="tabActiva === 'mis-pedidos' && pedidos.length === 0"
```

```html
    <div x-show="pedidos.length > 0" class="p-4 space-y-3">
```
Reemplazar con:
```html
    <div x-show="tabActiva === 'mis-pedidos' && pedidos.length > 0" class="p-4 space-y-3">
```

- [ ] **Step 6: Verificar manualmente en el navegador**

```bash
cd /home/siemprearmando/proyectos/panchi-bot && python main.py
```

Abrir `http://localhost:5000/picker` con sesión de picker activa y confirmar:
- Tab "📦 Mis pedidos" muestra los pedidos asignados (comportamiento sin cambios)
- Tab "📋 Cola" muestra los pedidos sin asignar con botón "Coger →"
- Pulsar "Coger →" llama a `POST /picker/cola/coger/<id>` y el pedido aparece en "Mis pedidos"
- Pedido ya cogido por otro → aparece en rojo con botón deshabilitado "Cogido"
- Sin pedidos → "No hay pedidos sin asignar ahora mismo"

- [ ] **Step 7: Commit**

```bash
cd /home/siemprearmando/proyectos/panchi-bot && git add templates/picker/index.html && git commit -m "feat: add Cola tab to picker app with self-assignment UI"
```

---

## Notas para el implementador

- **`_actualizar_estado_operativo`** toma dos parámetros: `(empleado_id, nuevo_estado)`. El valor correcto para "picker reclamó un pedido" es `'ocupado'`.
- **Sin CSRF** en los endpoints POST del blueprint picker — consistente con el resto del blueprint.
- **Polling existente** es de 60 segundos (`setInterval(..., 60000)`). La cola se refresca al mismo ritmo.
- **`recargar()`** es el nombre real del método que carga mis-pedidos (equivale a `cargarMisPedidos()` en la spec). No renombrar.
- **3 tests `TestWebhookMonei`** fallan en CI por razones pre-existentes — no son regresiones.
