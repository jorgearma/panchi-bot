# Cola de repartos sin asignar — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir que los repartidores reclamen repartos pendientes desde una cola, igual que los pickers reclaman pickings.

**Architecture:** Nuevos métodos `repartos_sin_asignar()` y `reclamar_reparto()` en `GestorDashboard`, dos nuevas rutas en `blueprints/repartidor.py`, y un tab "Cola" en `templates/repartidor/index.html`. La creación automática del `Reparto` se hace en `completar_picking()` tras el commit principal, en un bloque aislado para no afectar la finalización del picking si hay race condition.

**Tech Stack:** Flask, SQLAlchemy 2.x (SQL Server), Alpine.js 3, Tailwind CSS, pytest con mocks de session via `PropertyMock`

**Spec:** `docs/superpowers/specs/2026-03-21-repartidor-cola-design.md`

---

## File Map

| Archivo | Cambio |
|---------|--------|
| `managers/gestor_dashboard.py` | Añadir `repartos_sin_asignar()`, `reclamar_reparto()`, modificar `completar_picking()` |
| `blueprints/repartidor.py` | Añadir rutas `GET /repartidor/cola` y `POST /repartidor/cola/coger/<id>` |
| `templates/repartidor/index.html` | Añadir tab "Cola" con lógica Alpine.js |
| `tests/test_repartidor_cola.py` | Tests nuevos (crear archivo nuevo — el patrón del proyecto es un archivo por feature area, ver `test_picker_cola.py`; `tests/test_repartidor.py` existe y no se modifica) |

---

## Task 1: Tests para `repartos_sin_asignar()` y `reclamar_reparto()`

**Files:**
- Create: `tests/test_repartidor_cola.py`

- [ ] **Step 1: Escribir tests del manager**

Crear `tests/test_repartidor_cola.py` con este contenido:

```python
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from sqlalchemy.exc import SQLAlchemyError


def _mock_session(manager):
    patcher = patch.object(type(manager), 'session', new_callable=PropertyMock)
    mock_prop = patcher.start()
    mock_sess = MagicMock()
    mock_prop.return_value = mock_sess
    return patcher, mock_sess


class TestRepartosSinAsignar:

    def setup_method(self):
        from services import gestor_dashboard
        self.gd = gestor_dashboard

    def test_devuelve_lista(self, app):
        from datetime import datetime, timedelta
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                mock_pedido = MagicMock()
                mock_pedido.DireccionEntrega = 'Calle Mayor 10'
                mock_pedido.detalles = [MagicMock(), MagicMock(), MagicMock()]

                mock_rep = MagicMock()
                mock_rep.id = 1
                mock_rep.pedido_id = 42
                mock_rep.pedido = mock_pedido
                mock_rep.created_at = datetime.utcnow() - timedelta(minutes=3)

                mock_q = MagicMock()
                mock_q.join.return_value = mock_q
                mock_q.filter.return_value = mock_q
                mock_q.order_by.return_value = mock_q
                mock_q.all.return_value = [mock_rep]
                mock_sess.query.return_value = mock_q

                result = self.gd.repartos_sin_asignar()

                assert len(result) == 1
                assert result[0]['reparto_id'] == 1
                assert result[0]['pedido_id'] == 42
                assert result[0]['n_items'] == 3
                assert result[0]['direccion_entrega'] == 'Calle Mayor 10'
                assert result[0]['segundos_esperando'] >= 0
            finally:
                patcher.stop()

    def test_vacio(self, app):
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                mock_q = MagicMock()
                mock_q.join.return_value = mock_q
                mock_q.filter.return_value = mock_q
                mock_q.order_by.return_value = mock_q
                mock_q.all.return_value = []
                mock_sess.query.return_value = mock_q

                result = self.gd.repartos_sin_asignar()
                assert result == []
            finally:
                patcher.stop()

    def test_hace_join_y_filter(self, app):
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                mock_q = MagicMock()
                mock_q.join.return_value = mock_q
                mock_q.filter.return_value = mock_q
                mock_q.order_by.return_value = mock_q
                mock_q.all.return_value = []
                mock_sess.query.return_value = mock_q

                self.gd.repartos_sin_asignar()

                assert mock_q.join.called, "Debe hacer JOIN con Pedido"
                assert mock_q.filter.called
            finally:
                patcher.stop()


class TestReclamarReparto:

    def setup_method(self):
        from services import gestor_dashboard
        self.gd = gestor_dashboard

    def test_ok(self, app):
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                mock_rep = MagicMock()
                mock_rep.id = 5

                mock_q_exist = MagicMock()
                mock_q_exist.filter_by.return_value = mock_q_exist
                mock_q_exist.first.return_value = mock_rep

                mock_q_update = MagicMock()
                mock_q_update.filter.return_value = mock_q_update
                mock_q_update.update.return_value = 1

                mock_sess.query.side_effect = [mock_q_exist, mock_q_update]

                with patch.object(self.gd, '_actualizar_estado_operativo') as mock_aso:
                    ok, msg = self.gd.reclamar_reparto(5, empleado_id=7)
                    assert ok is True
                    assert msg == 'ok'
                    mock_aso.assert_called_once_with(7, 'ocupado')
            finally:
                patcher.stop()

    def test_no_encontrado(self, app):
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                mock_q = MagicMock()
                mock_q.filter_by.return_value = mock_q
                mock_q.first.return_value = None
                mock_sess.query.return_value = mock_q

                ok, msg = self.gd.reclamar_reparto(999, empleado_id=7)
                assert ok is False
                assert msg == 'no_encontrado'
            finally:
                patcher.stop()

    def test_ya_cogido(self, app):
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                mock_rep = MagicMock()

                mock_q_exist = MagicMock()
                mock_q_exist.filter_by.return_value = mock_q_exist
                mock_q_exist.first.return_value = mock_rep

                mock_q_update = MagicMock()
                mock_q_update.filter.return_value = mock_q_update
                mock_q_update.update.return_value = 0  # otro se adelantó

                mock_sess.query.side_effect = [mock_q_exist, mock_q_update]

                ok, msg = self.gd.reclamar_reparto(5, empleado_id=7)
                assert ok is False
                assert msg == 'ya_cogido'
            finally:
                patcher.stop()
```

- [ ] **Step 2: Verificar que fallan**

```bash
pytest tests/test_repartidor_cola.py -v
```

Esperado: `AttributeError` o `FAILED` — los métodos no existen aún.

---

## Task 2: Implementar `repartos_sin_asignar()` y `reclamar_reparto()`

**Files:**
- Modify: `managers/gestor_dashboard.py` — añadir al final de la sección "Repartidor methods" (después de `cierre_caja_repartidor`)

- [ ] **Step 3: Localizar dónde insertar**

El bloque `# Repartidor methods` está alrededor de la línea 1234. Insertar los nuevos métodos al final de esa sección, antes del cierre de clase o de la siguiente sección.

Buscar la última línea del método `cierre_caja_repartidor`:
```bash
grep -n "def cierre_caja_repartidor\|def _detalle\|def _iso" managers/gestor_dashboard.py | tail -5
```

- [ ] **Step 4: Añadir `repartos_sin_asignar()`**

Después del último método de la sección repartidor, añadir:

```python
    def repartos_sin_asignar(self) -> list[dict]:
        """Repartos con estado PENDIENTE y sin repartidor asignado.
        Solo incluye pedidos en estado PREPARADO.
        """
        s = self.session
        repartos = (
            s.query(Reparto)
            .join(Pedido, Pedido.PedidoID == Reparto.pedido_id)
            .filter(
                Reparto.repartidor_id == None,
                Reparto.estado == EstadoReparto.PENDIENTE.value,
                Pedido.Estado == EstadoPedido.PREPARADO.value,
            )
            .order_by(Reparto.created_at.asc())
            .all()
        )
        ahora = datetime.utcnow()
        return [
            {
                'reparto_id':         r.id,
                'pedido_id':          r.pedido_id,
                'n_items':            len(r.pedido.detalles) if r.pedido else 0,
                'direccion_entrega':  r.pedido.DireccionEntrega if r.pedido else '—',
                'segundos_esperando': int((ahora - r.created_at).total_seconds()),
            }
            for r in repartos
        ]

    def reclamar_reparto(self, reparto_id: int, empleado_id: int) -> tuple[bool, str]:
        """
        Asigna el reparto al empleado de forma atómica.
        Returns:
            (True,  'ok')            — asignado correctamente
            (False, 'no_encontrado') — reparto_id no existe
            (False, 'ya_cogido')     — otro repartidor se adelantó (rowcount == 0)
            (False, 'error')         — error de BD
        """
        s = self.session
        try:
            reparto = s.query(Reparto).filter_by(id=reparto_id).first()
            if not reparto:
                return False, 'no_encontrado'

            resultado = (
                s.query(Reparto)
                .filter(
                    Reparto.id == reparto_id,
                    Reparto.repartidor_id == None,
                    Reparto.estado == EstadoReparto.PENDIENTE.value,
                )
                .update(
                    {
                        'repartidor_id': empleado_id,
                        'estado': EstadoReparto.ASIGNADO.value,
                    },
                    synchronize_session=False,
                )
            )
            s.commit()

            if resultado == 0:
                return False, 'ya_cogido'

            self._actualizar_estado_operativo(empleado_id, 'ocupado')
            return True, 'ok'

        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error reclamando reparto %s: %s", reparto_id, e)
            return False, 'error'
```

- [ ] **Step 5: Pasar los tests**

```bash
pytest tests/test_repartidor_cola.py -v
```

Esperado: todos los tests de `TestRepartosSinAsignar` y `TestReclamarReparto` en PASSED.

- [ ] **Step 6: Commit**

```bash
git add managers/gestor_dashboard.py tests/test_repartidor_cola.py
git commit -m "feat: add repartos_sin_asignar and reclamar_reparto to GestorDashboard"
```

---

## Task 3: Auto-crear Reparto en `completar_picking()`

**Files:**
- Modify: `managers/gestor_dashboard.py` — dentro de `completar_picking()` (líneas ~1060-1107)

- [ ] **Step 7: Escribir test para auto-creación**

Añadir en `tests/test_repartidor_cola.py`:

```python
class TestCompletarPickingCreaReparto:

    def setup_method(self):
        from services import gestor_dashboard
        self.gd = gestor_dashboard

    def test_crea_reparto_si_no_existe(self, app):
        """Tras completar picking y pasar a PREPARADO, se crea Reparto PENDIENTE."""
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                from states import EstadoPicking, EstadoPedido, EstadoReparto

                mock_picking = MagicMock()
                mock_picking.id = 1
                mock_picking.empleado_id = 3
                mock_picking.estado = EstadoPicking.EN_PROCESO.value
                mock_picking.items = []

                mock_pedido = MagicMock()
                mock_pedido.PedidoID = 10
                mock_pedido.Estado = EstadoPedido.EN_PREPARACION.value
                mock_pedido.TelefonoEntrega = None
                mock_picking.pedido = mock_pedido

                # Primera query: picking by id
                mock_q_picking = MagicMock()
                mock_q_picking.filter_by.return_value = mock_q_picking
                mock_q_picking.first.return_value = mock_picking

                # Segunda query: Reparto existente (None = no existe)
                mock_q_reparto = MagicMock()
                mock_q_reparto.filter_by.return_value = mock_q_reparto
                mock_q_reparto.first.return_value = None

                # Tercera query: pickings activos del picker
                mock_q_activos = MagicMock()
                mock_q_activos.filter.return_value = mock_q_activos
                mock_q_activos.count.return_value = 0

                mock_sess.query.side_effect = [mock_q_picking, mock_q_reparto, mock_q_activos]

                with patch.object(self.gd, '_actualizar_estado_operativo'):
                    ok, msg, _ = self.gd.completar_picking(1, picker_id=3)

                assert ok is True
                # Verificar que se llamó s.add() con un Reparto (instancia real, no mock)
                from models import Reparto
                add_calls = mock_sess.add.call_args_list
                reparto_adds = [c for c in add_calls if isinstance(c.args[0], Reparto)]
                assert len(reparto_adds) == 1
            finally:
                patcher.stop()

    def test_integrity_error_no_falla_picking(self, app):
        """Si hay IntegrityError al crear el Reparto (race condition), el picking sigue ok."""
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                from states import EstadoPicking, EstadoPedido
                from sqlalchemy.exc import IntegrityError

                mock_picking = MagicMock()
                mock_picking.id = 1
                mock_picking.empleado_id = 3
                mock_picking.items = []

                mock_pedido = MagicMock()
                mock_pedido.PedidoID = 10
                mock_pedido.Estado = EstadoPedido.EN_PREPARACION.value
                mock_pedido.TelefonoEntrega = None
                mock_picking.pedido = mock_pedido

                mock_q_picking = MagicMock()
                mock_q_picking.filter_by.return_value = mock_q_picking
                mock_q_picking.first.return_value = mock_picking

                # Reparto no existe — pero el commit de creación lanzará IntegrityError
                mock_q_reparto = MagicMock()
                mock_q_reparto.filter_by.return_value = mock_q_reparto
                mock_q_reparto.first.return_value = None

                mock_q_activos = MagicMock()
                mock_q_activos.filter.return_value = mock_q_activos
                mock_q_activos.count.return_value = 0

                mock_sess.query.side_effect = [mock_q_picking, mock_q_reparto, mock_q_activos]

                # Simular que el segundo commit (creación de Reparto) lanza IntegrityError
                call_count = {'n': 0}
                def commit_side_effect():
                    call_count['n'] += 1
                    if call_count['n'] == 2:
                        raise IntegrityError("INSERT", {}, Exception("UNIQUE constraint"))
                mock_sess.commit.side_effect = commit_side_effect

                with patch.object(self.gd, '_actualizar_estado_operativo'):
                    ok, msg, _ = self.gd.completar_picking(1, picker_id=3)

                # El picking debe reportar éxito a pesar del error en el Reparto
                assert ok is True
            finally:
                patcher.stop()

    def test_no_duplica_reparto_existente(self, app):
        """Si ya existe Reparto, completar_picking no crea otro."""
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                from states import EstadoPicking, EstadoPedido, EstadoReparto
                from models import Reparto

                mock_picking = MagicMock()
                mock_picking.id = 1
                mock_picking.empleado_id = 3
                mock_picking.items = []

                mock_pedido = MagicMock()
                mock_pedido.PedidoID = 10
                mock_pedido.Estado = EstadoPedido.EN_PREPARACION.value
                mock_pedido.TelefonoEntrega = None
                mock_picking.pedido = mock_pedido

                mock_q_picking = MagicMock()
                mock_q_picking.filter_by.return_value = mock_q_picking
                mock_q_picking.first.return_value = mock_picking

                # Reparto ya existe
                mock_reparto_existente = MagicMock(spec=Reparto)
                mock_q_reparto = MagicMock()
                mock_q_reparto.filter_by.return_value = mock_q_reparto
                mock_q_reparto.first.return_value = mock_reparto_existente

                mock_q_activos = MagicMock()
                mock_q_activos.filter.return_value = mock_q_activos
                mock_q_activos.count.return_value = 0

                mock_sess.query.side_effect = [mock_q_picking, mock_q_reparto, mock_q_activos]

                with patch.object(self.gd, '_actualizar_estado_operativo'):
                    ok, msg, _ = self.gd.completar_picking(1, picker_id=3)

                assert ok is True
                from models import Reparto
                add_calls = mock_sess.add.call_args_list
                reparto_adds = [c for c in add_calls if isinstance(c.args[0], Reparto)]
                assert len(reparto_adds) == 0  # No se añade uno nuevo
            finally:
                patcher.stop()
```

- [ ] **Step 8: Ejecutar tests — deben fallar**

```bash
pytest tests/test_repartidor_cola.py::TestCompletarPickingCreaReparto -v
```

Esperado: FAILED (la lógica de creación no existe aún).

- [ ] **Step 9: Modificar `completar_picking()`**

En `managers/gestor_dashboard.py`, dentro de `completar_picking()`, localizar el bloque:

```python
            if pedido and transicion_valida_pedido(pedido.Estado, EstadoPedido.PREPARADO.value):
                estado_anterior = pedido.Estado
                pedido.Estado = EstadoPedido.PREPARADO.value
                s.add(HistorialEstadoPedido(
                    pedido_id=pedido.PedidoID,
                    estado_anterior=estado_anterior,
                    estado_nuevo=EstadoPedido.PREPARADO.value,
                    notas="Picking completado",
                ))

            s.commit()
```

Reemplazar por:

```python
            if pedido and transicion_valida_pedido(pedido.Estado, EstadoPedido.PREPARADO.value):
                estado_anterior = pedido.Estado
                pedido.Estado = EstadoPedido.PREPARADO.value
                s.add(HistorialEstadoPedido(
                    pedido_id=pedido.PedidoID,
                    estado_anterior=estado_anterior,
                    estado_nuevo=EstadoPedido.PREPARADO.value,
                    notas="Picking completado",
                ))

            s.commit()

            # Auto-crear Reparto pendiente para que los repartidores puedan reclamarlo.
            # NOTA: Bloque separado del commit del picking deliberadamente (desviación del spec).
            # Si pusiera la creación antes del s.commit() y hubiera una IntegrityError por race
            # condition con asignar_repartidor(), se haría rollback del picking completo.
            # Con el bloque separado, un fallo aquí no deshace el picking ya completado.
            # La race condition con asignar_repartidor() se detecta con el check filter_by()
            # y si aun así hay conflicto concurrente, se captura como IntegrityError (subclase
            # de Exception) y se loguea como INFO (es condición esperada, no un error real).
            if pedido:
                try:
                    reparto_existente = s.query(Reparto).filter_by(pedido_id=pedido.PedidoID).first()
                    if not reparto_existente:
                        s.add(Reparto(
                            pedido_id=pedido.PedidoID,
                            repartidor_id=None,
                            estado=EstadoReparto.PENDIENTE.value,
                        ))
                        s.commit()
                except Exception as _exc:
                    s.rollback()
                    from sqlalchemy.exc import IntegrityError
                    if isinstance(_exc, IntegrityError):
                        logger.info("Reparto ya creado concurrentemente para pedido %s", pedido.PedidoID)
                    else:
                        logger.warning("No se pudo crear Reparto para pedido %s: %s", pedido.PedidoID, _exc)
```

Verificar que `Reparto` y `EstadoReparto` están importados al principio del archivo (ya lo están).

- [ ] **Step 10: Pasar los tests**

```bash
pytest tests/test_repartidor_cola.py -v
```

Esperado: todos PASSED.

- [ ] **Step 11: Suite completa sin regresiones**

```bash
pytest -v --tb=short
```

Esperado: mismos tests pasan que antes (3 fallos pre-existentes de `TestWebhookMonei` son conocidos y no cuentan).

- [ ] **Step 12: Commit**

```bash
git add managers/gestor_dashboard.py tests/test_repartidor_cola.py
git commit -m "feat: auto-create pending Reparto when picking completes"
```

---

## Task 4: Rutas en `blueprints/repartidor.py`

**Files:**
- Modify: `blueprints/repartidor.py`

- [ ] **Step 13: Escribir tests de blueprint**

Añadir en `tests/test_repartidor_cola.py`:

```python
class TestBlueprintRepartidorCola:

    def test_cola_sin_sesion_rechazado(self, client):
        resp = client.get('/repartidor/cola')
        assert resp.status_code in (302, 401, 403)

    def test_cola_devuelve_json(self, client, app):
        from unittest.mock import patch
        from services import gestor_dashboard

        with client.session_transaction() as sess:
            sess['empleado_id'] = 1
            sess['rol'] = 'repartidor'

        with patch.object(gestor_dashboard, 'repartos_sin_asignar', return_value=[
            {'reparto_id': 3, 'pedido_id': 10, 'n_items': 2,
             'direccion_entrega': 'Calle Test 1', 'segundos_esperando': 60}
        ]):
            resp = client.get('/repartidor/cola')

        assert resp.status_code == 200
        data = resp.get_json()
        assert 'cola' in data
        assert 'total' in data
        assert data['total'] == 1
        assert data['cola'][0]['reparto_id'] == 3

    def test_coger_ok(self, client, app):
        from unittest.mock import patch
        from services import gestor_dashboard

        with client.session_transaction() as sess:
            sess['empleado_id'] = 7
            sess['rol'] = 'repartidor'

        with patch.object(gestor_dashboard, 'reclamar_reparto', return_value=(True, 'ok')) as mock_rec:
            resp = client.post('/repartidor/cola/coger/3')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert data['reparto_id'] == 3
        mock_rec.assert_called_once_with(3, 7)

    def test_coger_409_ya_cogido(self, client, app):
        from unittest.mock import patch
        from services import gestor_dashboard

        with client.session_transaction() as sess:
            sess['empleado_id'] = 7
            sess['rol'] = 'repartidor'

        with patch.object(gestor_dashboard, 'reclamar_reparto', return_value=(False, 'ya_cogido')):
            resp = client.post('/repartidor/cola/coger/3')

        assert resp.status_code == 409
        assert resp.get_json()['error'] == 'ya_cogido'

    def test_coger_404_no_encontrado(self, client, app):
        from unittest.mock import patch
        from services import gestor_dashboard

        with client.session_transaction() as sess:
            sess['empleado_id'] = 7
            sess['rol'] = 'repartidor'

        with patch.object(gestor_dashboard, 'reclamar_reparto', return_value=(False, 'no_encontrado')):
            resp = client.post('/repartidor/cola/coger/999')

        assert resp.status_code == 404
        assert resp.get_json()['error'] == 'no_encontrado'
```

- [ ] **Step 14: Verificar que fallan**

```bash
pytest tests/test_repartidor_cola.py::TestBlueprintRepartidorCola -v
```

Esperado: FAILED (rutas no existen).

- [ ] **Step 15: Añadir rutas en `blueprints/repartidor.py`**

Al final del archivo, antes del EOF, añadir:

```python
@blueprint_repartidor.route("/repartidor/cola")
@requiere_rol('repartidor', 'manager', 'admin')
def cola():
    try:
        lista = gestor_dashboard.repartos_sin_asignar()
        return jsonify({"cola": lista, "total": len(lista)})
    except Exception as e:
        logger.error("Error en /repartidor/cola: %s", e)
        return jsonify({"error": "Error interno"}), 500


@blueprint_repartidor.route("/repartidor/cola/coger/<int:reparto_id>", methods=["POST"])
@requiere_rol('repartidor', 'manager', 'admin')
def coger_reparto(reparto_id: int):
    empleado_id = session.get('empleado_id')
    try:
        ok, motivo = gestor_dashboard.reclamar_reparto(reparto_id, empleado_id)
    except Exception as e:
        logger.error("Error en /repartidor/cola/coger/%s: %s", reparto_id, e)
        return jsonify({"error": "Error interno"}), 500
    if ok:
        return jsonify({"ok": True, "reparto_id": reparto_id})
    if motivo == 'no_encontrado':
        return jsonify({"error": motivo}), 404
    if motivo == 'ya_cogido':
        return jsonify({"error": motivo}), 409
    return jsonify({"error": motivo}), 400
```

- [ ] **Step 16: Pasar los tests**

```bash
pytest tests/test_repartidor_cola.py -v
```

Esperado: todos PASSED.

- [ ] **Step 17: Commit**

```bash
git add blueprints/repartidor.py tests/test_repartidor_cola.py
git commit -m "feat: add GET /repartidor/cola and POST /repartidor/cola/coger endpoints"
```

---

## Task 5: Tab "Cola" en `templates/repartidor/index.html`

**Files:**
- Modify: `templates/repartidor/index.html`

Este task es solo HTML/JS — no hay tests automáticos. Verificación manual.

- [ ] **Step 18: Añadir variables Alpine al objeto de datos**

En el objeto retornado por `function repartidor(repartidorId)` (alrededor de línea 1089), localizar la línea `cargando: false,` y añadir después:

```javascript
        tabActiva: 'mis-entregas',   // 'mis-entregas' | 'cola'
        cola: [],
        colaTotal: 0,
        cogiendo: null,              // reparto_id en vuelo
```

- [ ] **Step 19: Añadir métodos `cargarCola()` y `cogerReparto()`**

Después del método `recargar()` (que termina alrededor de línea 1255), añadir:

```javascript
        async cargarCola() {
          try {
            const r = await fetch('/repartidor/cola');
            if (r.ok) {
              const data = await r.json();
              this.cola = data.cola || [];
              this.colaTotal = data.total || 0;
            }
          } catch (_) {}
        },

        async cogerReparto(repartoId) {
          if (this.cogiendo !== null) return;
          this.cogiendo = repartoId;
          try {
            const r = await fetch(`/repartidor/cola/coger/${repartoId}`, { method: 'POST' });
            if (r.ok) {
              this.cola = this.cola.map(p =>
                p.reparto_id === repartoId ? { ...p, ya_cogido: true } : p
              );
              this.colaTotal = Math.max(0, this.colaTotal - 1);
              await this.recargar();
              this.tabActiva = 'mis-entregas';
            } else {
              const data = await r.json().catch(() => ({}));
              if (data.error === 'ya_cogido') {
                this.cola = this.cola.map(p =>
                  p.reparto_id === repartoId ? { ...p, ya_cogido: true } : p
                );
              }
            }
          } catch (_) {}
          this.cogiendo = null;
        },
```

- [ ] **Step 20: Añadir tab bar dentro de la vista lista**

En `templates/repartidor/index.html`, localizar el inicio de la sección `VISTA LISTA`:

```html
  <div x-show="repartidorId && !cargando && vista === 'lista'" x-cloak>

    <!-- Sin pedidos -->
```

Después de la apertura del `<div>` y antes del comentario `<!-- Sin pedidos -->`, insertar el tab bar:

```html
    <!-- ---- Tabs ---- -->
    <div class="flex border-b-2 border-gray-800 sticky z-20 bg-gray-100"
         :style="'top:52px'">
      <button @click="tabActiva = 'mis-entregas'"
              class="flex-1 text-center py-3 text-sm font-medium transition"
              :class="tabActiva === 'mis-entregas'
                ? 'text-orange-400 border-b-2 border-orange-500 -mb-[2px]'
                : 'text-gray-500'">
        🛵 Mis entregas
        <span x-show="pedidosActivos.length > 0"
              class="ml-1.5 bg-gray-700 text-gray-300 text-xs rounded-full px-2 py-0.5"
              x-text="pedidosActivos.length"></span>
      </button>
      <button @click="tabActiva = 'cola'; cargarCola()"
              class="flex-1 text-center py-3 text-sm font-medium transition"
              :class="tabActiva === 'cola'
                ? 'text-orange-400 border-b-2 border-orange-500 -mb-[2px]'
                : 'text-gray-500'">
        📋 Cola
        <span x-show="colaTotal > 0"
              class="ml-1.5 bg-red-600 text-white text-xs rounded-full px-2 py-0.5"
              x-text="colaTotal"></span>
      </button>
    </div>
```

- [ ] **Step 21: Envolver contenido existente de "mis entregas" en condicional**

El contenido actual de la vista lista (el `<!-- Sin pedidos -->` + el `<div x-show="pedidosActivos.length > 0 || pedidosHistorial.length > 0"`) debe mostrarse solo cuando `tabActiva === 'mis-entregas'`.

Localizar:
```html
    <!-- Sin pedidos -->
    <div x-show="pedidosActivos.length === 0 && pedidosHistorial.length === 0"
```

Cambiar a:
```html
    <!-- Sin pedidos -->
    <div x-show="tabActiva === 'mis-entregas' && pedidosActivos.length === 0 && pedidosHistorial.length === 0"
```

Localizar:
```html
    <div x-show="pedidosActivos.length > 0 || pedidosHistorial.length > 0" class="p-4 space-y-4">
```

Cambiar a:
```html
    <div x-show="tabActiva === 'mis-entregas' && (pedidosActivos.length > 0 || pedidosHistorial.length > 0)" class="p-4 space-y-4">
```

- [ ] **Step 22: Añadir sección Cola**

Inmediatamente después del cierre del `<div x-show="tabActiva === 'mis-entregas' && (...)">` (que es el div principal de contenido), añadir antes del cierre del div `VISTA LISTA`:

```html
    <!-- ======== SECCIÓN COLA ======== -->
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
        <template x-for="p in cola" :key="p.reparto_id">
          <div class="bg-gray-800 rounded-2xl p-4 flex justify-between items-center slide-up"
               :class="p.ya_cogido ? 'opacity-40' : ''">
            <div>
              <div class="font-bold text-white text-sm">Pedido #<span x-text="p.pedido_id"></span></div>
              <div class="text-xs text-gray-400 mt-0.5">📍 <span x-text="p.direccion_entrega"></span></div>
              <div class="text-xs mt-1" :class="p.ya_cogido ? 'text-red-400' : 'text-gray-500'">
                <span x-show="!p.ya_cogido"
                      x-text="'hace ' + (p.segundos_esperando < 60
                        ? p.segundos_esperando + 's'
                        : Math.floor(p.segundos_esperando / 60) + 'min') + ' · 📦 ' + p.n_items + ' productos'"></span>
                <span x-show="p.ya_cogido">Ya cogido por otro repartidor</span>
              </div>
            </div>
            <button @click="cogerReparto(p.reparto_id)"
                    :disabled="p.ya_cogido || cogiendo !== null"
                    class="text-sm font-bold px-4 py-2 rounded-xl transition"
                    style="min-height:56px"
                    :class="p.ya_cogido
                      ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
                      : 'bg-orange-500 text-white active:bg-orange-600'">
              <span x-show="!p.ya_cogido && cogiendo !== p.reparto_id">Coger →</span>
              <span x-show="p.ya_cogido">Cogido</span>
              <span x-show="cogiendo === p.reparto_id && !p.ya_cogido">...</span>
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

- [ ] **Step 23: Verificación manual**

```bash
python main.py
```

1. Acceder a `/repartidor` con sesión válida.
2. Verificar que aparecen los dos tabs: "🛵 Mis entregas" y "📋 Cola".
3. Pulsar "Cola" — debe cargar y mostrar pedidos en `PREPARADO` sin repartidor, o el estado vacío.
4. Pulsar "Coger →" en un pedido — debe asignarse y pasar a "Mis entregas".

- [ ] **Step 24: Ejecutar suite de tests completa**

```bash
pytest -v --tb=short
```

Esperado: mismos fallos pre-existentes únicamente.

- [ ] **Step 25: Commit final**

```bash
git add templates/repartidor/index.html
git commit -m "feat: add cola tab to repartidor view for self-assignment of pending deliveries"
```
