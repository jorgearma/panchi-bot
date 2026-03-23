# Métricas Dashboard Backend — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `GestorMetricas` + two blueprints (`metricas_operacion`, `metricas_analitica`) that expose real-time and historical metrics for the admin dashboard, without touching existing `GestorDashboard` or `dashboard.py`.

**Architecture:** Single read-only manager `managers/gestor_metricas.py` feeds two blueprints — `/metricas/operacion/*` (time-real polling, no date params) and `/metricas/analitica/*` (historical, `?desde=&hasta=`). Both blueprints registered in `main.py` alongside existing blueprints. All endpoints require `@requiere_rol('admin', 'manager')`.

**Tech Stack:** Flask blueprints, SQLAlchemy ORM, pytest + MagicMock/PropertyMock, Python `statistics.median`

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `managers/gestor_metricas.py` | All metric calculations, read-only |
| Create | `blueprints/metricas_operacion.py` | Routes `/metricas/operacion/*` |
| Create | `blueprints/metricas_analitica.py` | Routes `/metricas/analitica/*` |
| Modify | `main.py` | Register both new blueprints in `create_app()` |
| Create | `tests/test_gestor_metricas.py` | Unit tests for manager methods |
| Create | `tests/test_metricas_operacion.py` | Blueprint integration tests (operacion) |
| Create | `tests/test_metricas_analitica.py` | Blueprint integration tests (analitica) |

---

## Task 1: GestorMetricas scaffold + `resumen_operacion`

**Files:**
- Create: `managers/gestor_metricas.py`
- Create: `tests/test_gestor_metricas.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gestor_metricas.py
from unittest.mock import patch, MagicMock, PropertyMock
from datetime import date


def _make_gestor():
    from managers.gestor_metricas import GestorMetricas
    return GestorMetricas()


class TestResumenOperacion:
    def test_devuelve_claves_esperadas(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        # pedidos_activos: query count
        session_mock.query.return_value.filter.return_value.count.return_value = 5
        session_mock.query.return_value.filter_by.return_value.count.return_value = 3
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.resumen_operacion()
        claves = {
            'pedidos_activos', 'empleados_en_turno', 'cola_picking_count',
            'cola_reparto_count', 'entregados_hoy', 'tasa_entrega_hoy_pct',
            'tiempo_medio_ciclo_hoy_min'
        }
        assert claves == set(result.keys())

    def test_valores_son_numericos(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.count.return_value = 0
        session_mock.query.return_value.filter_by.return_value.count.return_value = 0
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.resumen_operacion()
        for v in result.values():
            assert isinstance(v, (int, float)) or v is None
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /home/siemprearmando/proyectos/panchi-bot && source venv/bin/activate && python -m pytest tests/test_gestor_metricas.py -v 2>&1 | head -30
```
Expected: `ModuleNotFoundError` or `ImportError`

- [ ] **Step 3: Create the manager scaffold**

```python
# managers/gestor_metricas.py
import logging
import statistics
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)

# Estados operativos (no terminales)
_ESTADOS_ACTIVOS = ('en_preparacion', 'preparado', 'en_reparto', 'confirmando_pago',
                    'enlace', 'enlace2', 'pendiente')
_ESTADOS_TERMINALES = ('entregado', 'cancelado', 'reembolsado')


class GestorMetricas:

    @property
    def session(self):
        from database import get_db
        return get_db()

    # =========================================================
    # BLOQUE 1 — Tiempo real
    # =========================================================

    def resumen_operacion(self) -> dict:
        from models import Pedido, CheckIn, PickingPedido, Reparto, HistorialEstadoPedido
        s = self.session
        hoy = date.today()

        pedidos_activos = (
            s.query(Pedido)
            .filter(Pedido.Estado.notin_(_ESTADOS_TERMINALES))
            .count()
        )

        empleados_en_turno = (
            s.query(CheckIn)
            .filter(
                CheckIn.fecha == hoy,
                CheckIn.fin.is_(None)
            )
            .count()
        )

        cola_picking_count = (
            s.query(PickingPedido)
            .filter(
                PickingPedido.estado == 'pendiente',
                PickingPedido.empleado_id.is_(None)
            )
            .count()
        )

        cola_reparto_count = (
            s.query(Reparto)
            .filter(Reparto.estado == 'pendiente')
            .count()
        )

        entregados_hoy = (
            s.query(Reparto)
            .filter(
                Reparto.estado == 'entregado',
                Reparto.updated_at >= datetime.combine(hoy, datetime.min.time())
            )
            .count()
        )

        no_entregados_hoy = (
            s.query(Reparto)
            .filter(
                Reparto.estado == 'no_entregado',
                Reparto.updated_at >= datetime.combine(hoy, datetime.min.time())
            )
            .count()
        )

        total_cerrados = entregados_hoy + no_entregados_hoy
        tasa_entrega_hoy_pct = (
            round(entregados_hoy * 100 / total_cerrados) if total_cerrados > 0 else None
        )

        tiempo_medio_ciclo_hoy_min = self._tiempo_medio_ciclo_hoy(hoy)

        return {
            'pedidos_activos': pedidos_activos,
            'empleados_en_turno': empleados_en_turno,
            'cola_picking_count': cola_picking_count,
            'cola_reparto_count': cola_reparto_count,
            'entregados_hoy': entregados_hoy,
            'tasa_entrega_hoy_pct': tasa_entrega_hoy_pct,
            'tiempo_medio_ciclo_hoy_min': tiempo_medio_ciclo_hoy_min,
        }

    def _tiempo_medio_ciclo_hoy(self, hoy: date) -> int | None:
        """Mediana de (ENTREGADO - EN_PREPARACION) para pedidos entregados hoy."""
        from models import HistorialEstadoPedido, Pedido
        s = self.session
        pedidos_entregados_hoy = (
            s.query(HistorialEstadoPedido.pedido_id)
            .filter(
                HistorialEstadoPedido.estado == 'entregado',
                HistorialEstadoPedido.cambiado_en >= datetime.combine(hoy, datetime.min.time())
            )
            .all()
        )
        ids = [r.pedido_id for r in pedidos_entregados_hoy]
        if not ids:
            return None
        tiempos = []
        for pid in ids:
            t = self._tiempo_entre_estados(pid, 'en_preparacion', 'entregado')
            if t is not None:
                tiempos.append(t)
        return round(statistics.median(tiempos)) if tiempos else None

    def asistencia_hoy(self) -> list[dict]:
        return []

    def colas_detalle(self) -> dict:
        return {'cola_picking': [], 'cola_reparto': []}

    def pedidos_por_estado(self) -> dict:
        return {}

    def alertas_tiempo_real(self) -> list[dict]:
        return []

    # =========================================================
    # BLOQUE 2 — Analítica (stubs)
    # =========================================================

    def resumen_periodo(self, desde: date, hasta: date) -> dict:
        return {}

    def metricas_pedidos(self, desde: date, hasta: date) -> dict:
        return {}

    def metricas_picking(self, desde: date, hasta: date) -> dict:
        return {}

    def metricas_reparto(self, desde: date, hasta: date) -> dict:
        return {}

    def rendimiento_empleados(self, desde: date, hasta: date, rol: str | None = None) -> list:
        return []

    def ficha_empleado(self, empleado_id: int, desde: date, hasta: date) -> dict:
        return {}

    def comparativa_empleados(self, desde: date, hasta: date, rol: str) -> dict:
        return {}

    def asistencia_periodo(self, desde: date, hasta: date) -> dict:
        return {}

    def metricas_incidencias(self, desde: date, hasta: date) -> dict:
        return {}

    # =========================================================
    # HELPERS PRIVADOS
    # =========================================================

    def _horas_trabajadas(self, empleado_id: int, desde: date, hasta: date) -> float:
        from models import CheckIn
        s = self.session
        checkins = (
            s.query(CheckIn)
            .filter(
                CheckIn.empleado_id == empleado_id,
                CheckIn.fecha >= desde,
                CheckIn.fecha <= hasta,
                CheckIn.fin.isnot(None)
            )
            .all()
        )
        total_min = sum(
            (c.fin - c.inicio).total_seconds() / 60
            for c in checkins
            if c.fin and c.inicio
        )
        return round(total_min / 60, 2)

    def _tiempo_entre_estados(self, pedido_id: int, estado_a: str, estado_b: str) -> int | None:
        from models import HistorialEstadoPedido
        s = self.session
        registros = (
            s.query(HistorialEstadoPedido)
            .filter(
                HistorialEstadoPedido.pedido_id == pedido_id,
                HistorialEstadoPedido.estado.in_([estado_a, estado_b])
            )
            .order_by(HistorialEstadoPedido.cambiado_en)
            .all()
        )
        mapa = {r.estado: r.cambiado_en for r in registros}
        if estado_a not in mapa or estado_b not in mapa:
            return None
        delta = mapa[estado_b] - mapa[estado_a]
        return max(0, round(delta.total_seconds() / 60))

    def _operaciones_empleado(self, empleado_id: int, rol: str, desde: date, hasta: date) -> list:
        from models import PickingPedido, Reparto
        s = self.session
        if rol == 'picker':
            return (
                s.query(PickingPedido)
                .filter(
                    PickingPedido.empleado_id == empleado_id,
                    PickingPedido.estado == 'completado',
                    PickingPedido.updated_at >= datetime.combine(desde, datetime.min.time()),
                    PickingPedido.updated_at <= datetime.combine(hasta, datetime.max.time()),
                )
                .all()
            )
        else:  # repartidor
            return (
                s.query(Reparto)
                .filter(
                    Reparto.empleado_id == empleado_id,
                    Reparto.estado == 'entregado',
                    Reparto.updated_at >= datetime.combine(desde, datetime.min.time()),
                    Reparto.updated_at <= datetime.combine(hasta, datetime.max.time()),
                )
                .all()
            )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/siemprearmando/proyectos/panchi-bot && source venv/bin/activate && python -m pytest tests/test_gestor_metricas.py::TestResumenOperacion -v
```
Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add managers/gestor_metricas.py tests/test_gestor_metricas.py
git commit -m "feat: add GestorMetricas scaffold with resumen_operacion"
```

---

## Task 2: `asistencia_hoy` + `colas_detalle` + `pedidos_por_estado`

**Files:**
- Modify: `managers/gestor_metricas.py`
- Modify: `tests/test_gestor_metricas.py`

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/test_gestor_metricas.py

class TestAsistenciaHoy:
    def test_devuelve_lista(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        # Simular JOIN: query devuelve tuplas (Turno, CheckIn|None, Empleado)
        turno_mock = MagicMock()
        turno_mock.inicio = datetime(2026, 3, 22, 9, 0)
        turno_mock.fin = datetime(2026, 3, 22, 17, 0)
        empleado_mock = MagicMock()
        empleado_mock.EmpleadoID = 7
        empleado_mock.Nombre = 'Ana García'
        empleado_mock.rol = MagicMock()
        empleado_mock.rol.nombre = 'picker'
        checkin_mock = MagicMock()
        checkin_mock.inicio = datetime(2026, 3, 22, 9, 8)
        checkin_mock.minutos_tarde = 8
        checkin_mock.fin = None
        row = (turno_mock, checkin_mock, empleado_mock)
        session_mock.query.return_value.join.return_value.outerjoin.return_value.filter.return_value.all.return_value = [row]
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.asistencia_hoy()
        assert isinstance(result, list)
        assert result[0]['empleado_id'] == 7
        assert result[0]['activo'] is True
        assert result[0]['ausente'] is False
        assert result[0]['minutos_tarde'] == 8

    def test_sin_checkin_es_ausente(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        turno_mock = MagicMock()
        turno_mock.inicio = datetime(2026, 3, 22, 9, 0)
        turno_mock.fin = datetime(2026, 3, 22, 17, 0)
        empleado_mock = MagicMock()
        empleado_mock.EmpleadoID = 9
        empleado_mock.Nombre = 'Pedro'
        empleado_mock.rol = MagicMock()
        empleado_mock.rol.nombre = 'repartidor'
        row = (turno_mock, None, empleado_mock)
        session_mock.query.return_value.join.return_value.outerjoin.return_value.filter.return_value.all.return_value = [row]
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.asistencia_hoy()
        assert result[0]['ausente'] is True
        assert result[0]['activo'] is False


class TestColasDetalle:
    def test_estructura_devuelta(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        pp_mock = MagicMock()
        pp_mock.PedidoID = 2341
        pp_mock.pedido = MagicMock()
        pp_mock.pedido.detalles = [MagicMock(), MagicMock(), MagicMock()]
        session_mock.query.return_value.filter.return_value.all.return_value = [pp_mock]
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.colas_detalle()
        assert 'cola_picking' in result
        assert 'cola_reparto' in result


class TestPedidosPorEstado:
    def test_devuelve_dict_de_conteos(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        from models import Pedido
        session_mock.query.return_value.filter.return_value.group_by.return_value.all.return_value = [
            ('en_preparacion', 4),
            ('preparado', 2),
        ]
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.pedidos_por_estado()
        assert isinstance(result, dict)
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/siemprearmando/proyectos/panchi-bot && source venv/bin/activate && python -m pytest tests/test_gestor_metricas.py::TestAsistenciaHoy tests/test_gestor_metricas.py::TestColasDetalle tests/test_gestor_metricas.py::TestPedidosPorEstado -v
```
Expected: FAILED (stubs return empty)

- [ ] **Step 3: Implement the three methods**

```python
# Replace stub asistencia_hoy in managers/gestor_metricas.py:

    def asistencia_hoy(self) -> list[dict]:
        from models import Turno, CheckIn, Empleado
        s = self.session
        hoy = date.today()
        rows = (
            s.query(Turno, CheckIn, Empleado)
            .join(Empleado, Turno.empleado_id == Empleado.EmpleadoID)
            .outerjoin(
                CheckIn,
                (CheckIn.empleado_id == Turno.empleado_id) & (CheckIn.fecha == hoy)
            )
            .filter(Turno.fecha == hoy)
            .all()
        )
        result = []
        for turno, checkin, empleado in rows:
            result.append({
                'empleado_id': empleado.EmpleadoID,
                'nombre': empleado.Nombre,
                'rol': empleado.rol.nombre if empleado.rol else None,
                'turno_inicio': turno.inicio.strftime('%H:%M') if turno.inicio else None,
                'turno_fin': turno.fin.strftime('%H:%M') if turno.fin else None,
                'hora_fichaje': checkin.inicio.strftime('%H:%M') if checkin else None,
                'minutos_tarde': checkin.minutos_tarde if checkin else None,
                'activo': checkin is not None and checkin.fin is None,
                'ausente': checkin is None,
            })
        return result

    def colas_detalle(self) -> dict:
        from models import PickingPedido, Reparto, HistorialEstadoPedido, PedidoDetalle
        from sqlalchemy import func
        s = self.session

        pickings = (
            s.query(PickingPedido)
            .filter(
                PickingPedido.estado == 'pendiente',
                PickingPedido.empleado_id.is_(None)
            )
            .all()
        )
        cola_picking = []
        for pp in pickings:
            ultimo_hist = (
                s.query(HistorialEstadoPedido)
                .filter(HistorialEstadoPedido.pedido_id == pp.PedidoID)
                .order_by(HistorialEstadoPedido.cambiado_en.desc())
                .first()
            )
            mins = None
            if ultimo_hist:
                delta = datetime.utcnow() - ultimo_hist.cambiado_en
                mins = round(delta.total_seconds() / 60)
            num_items = (
                s.query(func.count(PedidoDetalle.DetalleID))
                .filter(PedidoDetalle.PedidoID == pp.PedidoID)
                .scalar()
            ) or 0
            cola_picking.append({
                'pedido_id': pp.PedidoID,
                'minutos_esperando': mins,
                'num_items': num_items,
            })
        cola_picking.sort(key=lambda x: x['minutos_esperando'] or 0, reverse=True)

        repartos = (
            s.query(Reparto)
            .filter(Reparto.estado == 'pendiente')
            .all()
        )
        cola_reparto = []
        for r in repartos:
            ultimo_hist = (
                s.query(HistorialEstadoPedido)
                .filter(HistorialEstadoPedido.pedido_id == r.pedido_id)
                .order_by(HistorialEstadoPedido.cambiado_en.desc())
                .first()
            )
            mins = None
            if ultimo_hist:
                delta = datetime.utcnow() - ultimo_hist.cambiado_en
                mins = round(delta.total_seconds() / 60)
            num_items = (
                s.query(func.count(PedidoDetalle.DetalleID))
                .filter(PedidoDetalle.PedidoID == r.pedido_id)
                .scalar()
            ) or 0
            cola_reparto.append({
                'pedido_id': r.pedido_id,
                'minutos_esperando': mins,
                'num_items': num_items,
            })
        cola_reparto.sort(key=lambda x: x['minutos_esperando'] or 0, reverse=True)

        return {'cola_picking': cola_picking, 'cola_reparto': cola_reparto}

    def pedidos_por_estado(self) -> dict:
        from models import Pedido
        from sqlalchemy import func
        s = self.session
        rows = (
            s.query(Pedido.Estado, func.count(Pedido.PedidoID))
            .filter(Pedido.Estado.notin_(_ESTADOS_TERMINALES))
            .group_by(Pedido.Estado)
            .all()
        )
        return {estado: count for estado, count in rows}
```

- [ ] **Step 4: Run tests**

```bash
cd /home/siemprearmando/proyectos/panchi-bot && source venv/bin/activate && python -m pytest tests/test_gestor_metricas.py -v
```
Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add managers/gestor_metricas.py tests/test_gestor_metricas.py
git commit -m "feat: add asistencia_hoy, colas_detalle, pedidos_por_estado"
```

---

## Task 3: `alertas_tiempo_real`

**Files:**
- Modify: `managers/gestor_metricas.py`
- Modify: `tests/test_gestor_metricas.py`

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/test_gestor_metricas.py

class TestAlertasTiempoReal:
    def _gestor_vacio(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.all.return_value = []
        session_mock.query.return_value.filter.return_value.count.return_value = 0
        return gestor, session_mock

    def test_sin_condiciones_lista_vacia(self):
        gestor, session_mock = self._gestor_vacio()
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.alertas_tiempo_real()
        assert result == []

    def test_cola_picking_alta_genera_alerta(self):
        gestor = _make_gestor()
        session_mock = MagicMock()

        def side_effect_count(*args, **kwargs):
            mock = MagicMock()
            # cola picking ≥3 → alerta
            mock.filter.return_value.count.return_value = 3
            mock.filter.return_value.all.return_value = []
            return mock

        session_mock.query.side_effect = side_effect_count
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            # Parchamos submétodos para aislar
            with patch.object(gestor, '_alertas_ausencia', return_value=[]):
                with patch.object(gestor, '_alertas_pedidos_bloqueados', return_value=[]):
                    with patch.object(gestor, '_alertas_repartidores_inactivos', return_value=[]):
                        with patch.object(gestor, '_alertas_colas', return_value=[
                            {'tipo': 'cola_picking_alta', 'severidad': 'alta',
                             'mensaje': '3 pedidos en cola', 'pedidos_afectados': []}
                        ]):
                            result = gestor.alertas_tiempo_real()
        assert any(a['tipo'] == 'cola_picking_alta' for a in result)

    def test_resultado_tiene_tipo_severidad_mensaje(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.all.return_value = []
        session_mock.query.return_value.filter.return_value.count.return_value = 0
        alerta_fake = {'tipo': 'cola_picking_alta', 'severidad': 'alta',
                       'mensaje': 'test', 'pedidos_afectados': []}
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            with patch.object(gestor, '_alertas_ausencia', return_value=[alerta_fake]):
                with patch.object(gestor, '_alertas_colas', return_value=[]):
                    with patch.object(gestor, '_alertas_pedidos_bloqueados', return_value=[]):
                        with patch.object(gestor, '_alertas_repartidores_inactivos', return_value=[]):
                            result = gestor.alertas_tiempo_real()
        assert all({'tipo', 'severidad', 'mensaje'}.issubset(a.keys()) for a in result)
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/siemprearmando/proyectos/panchi-bot && source venv/bin/activate && python -m pytest tests/test_gestor_metricas.py::TestAlertasTiempoReal -v
```

- [ ] **Step 3: Implement `alertas_tiempo_real` and its private helpers**

```python
# Replace stub alertas_tiempo_real in managers/gestor_metricas.py

    def alertas_tiempo_real(self) -> list[dict]:
        alertas = []
        alertas.extend(self._alertas_ausencia())
        alertas.extend(self._alertas_colas())
        alertas.extend(self._alertas_pedidos_bloqueados())
        alertas.extend(self._alertas_repartidores_inactivos())
        orden = {'alta': 0, 'media': 1, 'baja': 2}
        alertas.sort(key=lambda a: orden.get(a['severidad'], 99))
        return alertas

    def _alertas_ausencia(self) -> list[dict]:
        from models import Turno, CheckIn, Empleado
        s = self.session
        hoy = date.today()
        ahora = datetime.utcnow()
        turnos_hoy = (
            s.query(Turno, Empleado)
            .join(Empleado, Turno.empleado_id == Empleado.EmpleadoID)
            .filter(Turno.fecha == hoy)
            .all()
        )
        alertas = []
        for turno, empleado in turnos_hoy:
            if not turno.inicio:
                continue
            inicio_dt = datetime.combine(hoy, turno.inicio.time()) if isinstance(turno.inicio, datetime) else turno.inicio
            mins_desde_inicio = round((ahora - inicio_dt).total_seconds() / 60)
            if mins_desde_inicio < 15:
                continue
            checkin = (
                s.query(CheckIn)
                .filter(CheckIn.empleado_id == empleado.EmpleadoID, CheckIn.fecha == hoy)
                .first()
            )
            if checkin is None:
                alertas.append({
                    'tipo': 'ausencia_no_fichada',
                    'severidad': 'alta',
                    'mensaje': (
                        f'{empleado.Nombre} tiene turno desde las '
                        f'{turno.inicio.strftime("%H:%M") if hasattr(turno.inicio, "strftime") else turno.inicio} '
                        f'y no ha fichado ({mins_desde_inicio} min de retraso)'
                    ),
                    'empleado_id': empleado.EmpleadoID,
                })
        return alertas

    def _alertas_colas(self) -> list[dict]:
        from models import PickingPedido, Reparto
        s = self.session
        umbral = 3
        alertas = []

        ids_picking = [
            r.PedidoID for r in
            s.query(PickingPedido)
            .filter(PickingPedido.estado == 'pendiente', PickingPedido.empleado_id.is_(None))
            .all()
        ]
        if len(ids_picking) >= umbral:
            alertas.append({
                'tipo': 'cola_picking_alta',
                'severidad': 'alta',
                'mensaje': f'{len(ids_picking)} pedidos en cola de picking sin picker asignado',
                'pedidos_afectados': ids_picking,
            })

        ids_reparto = [
            r.pedido_id for r in
            s.query(Reparto).filter(Reparto.estado == 'pendiente').all()
        ]
        if len(ids_reparto) >= umbral:
            alertas.append({
                'tipo': 'cola_reparto_alta',
                'severidad': 'alta',
                'mensaje': f'{len(ids_reparto)} pedidos en cola de reparto sin repartidor asignado',
                'pedidos_afectados': ids_reparto,
            })
        return alertas

    def _alertas_pedidos_bloqueados(self) -> list[dict]:
        from models import HistorialEstadoPedido, Pedido
        s = self.session
        hoy = date.today()
        # Tiempo de referencia: mediana ciclo hoy o últimos 7 días
        tiempo_ref = self._tiempo_medio_ciclo_hoy(hoy)
        if tiempo_ref is None:
            desde_7d = hoy - timedelta(days=7)
            tiempo_ref = self._tiempo_medio_ciclo_periodo(desde_7d, hoy - timedelta(days=1))
        if tiempo_ref is None:
            return []

        umbral_min = tiempo_ref * 2
        ahora = datetime.utcnow()
        alertas = []

        pedidos_activos = (
            s.query(Pedido)
            .filter(Pedido.Estado.notin_(_ESTADOS_TERMINALES))
            .all()
        )
        for pedido in pedidos_activos:
            ultimo = (
                s.query(HistorialEstadoPedido)
                .filter(HistorialEstadoPedido.pedido_id == pedido.PedidoID)
                .order_by(HistorialEstadoPedido.cambiado_en.desc())
                .first()
            )
            if ultimo is None:
                continue
            mins_bloqueado = round((ahora - ultimo.cambiado_en).total_seconds() / 60)
            if mins_bloqueado > umbral_min:
                alertas.append({
                    'tipo': 'pedido_bloqueado',
                    'severidad': 'media',
                    'mensaje': (
                        f'Pedido #{pedido.PedidoID} lleva {mins_bloqueado} min '
                        f"en estado '{pedido.Estado}' sin avanzar"
                    ),
                    'pedido_id': pedido.PedidoID,
                })
        return alertas

    def _tiempo_medio_ciclo_periodo(self, desde: date, hasta: date) -> int | None:
        from models import HistorialEstadoPedido
        s = self.session
        entregados = (
            s.query(HistorialEstadoPedido.pedido_id)
            .filter(
                HistorialEstadoPedido.estado == 'entregado',
                HistorialEstadoPedido.cambiado_en >= datetime.combine(desde, datetime.min.time()),
                HistorialEstadoPedido.cambiado_en <= datetime.combine(hasta, datetime.max.time()),
            )
            .all()
        )
        ids = [r.pedido_id for r in entregados]
        if not ids:
            return None
        tiempos = [t for t in (self._tiempo_entre_estados(pid, 'en_preparacion', 'entregado') for pid in ids) if t is not None]
        return round(statistics.median(tiempos)) if tiempos else None

    def _alertas_repartidores_inactivos(self) -> list[dict]:
        from models import CheckIn, Reparto, Empleado, Rol
        s = self.session
        hoy = date.today()
        ahora = datetime.utcnow()
        umbral_min = 45

        checkins_abiertos = (
            s.query(CheckIn, Empleado)
            .join(Empleado, CheckIn.empleado_id == Empleado.EmpleadoID)
            .join(Rol, Empleado.rol_id == Rol.id)
            .filter(
                CheckIn.fecha == hoy,
                CheckIn.fin.is_(None),
                Rol.nombre == 'repartidor',
            )
            .all()
        )
        alertas = []
        for checkin, empleado in checkins_abiertos:
            reparto_activo = (
                s.query(Reparto)
                .filter(
                    Reparto.empleado_id == empleado.EmpleadoID,
                    Reparto.estado.in_(['asignado', 'en_camino']),
                )
                .first()
            )
            if reparto_activo:
                continue
            ultimo_reparto = (
                s.query(Reparto)
                .filter(Reparto.empleado_id == empleado.EmpleadoID)
                .order_by(Reparto.updated_at.desc())
                .first()
            )
            ref_time = ultimo_reparto.updated_at if ultimo_reparto else checkin.inicio
            if ref_time is None:
                continue
            mins_inactivo = round((ahora - ref_time).total_seconds() / 60)
            if mins_inactivo > umbral_min:
                alertas.append({
                    'tipo': 'repartidor_inactivo',
                    'severidad': 'media',
                    'mensaje': f'{empleado.Nombre} lleva {mins_inactivo} min sin reparto activo',
                    'empleado_id': empleado.EmpleadoID,
                })
        return alertas
```

- [ ] **Step 4: Run all manager tests so far**

```bash
cd /home/siemprearmando/proyectos/panchi-bot && source venv/bin/activate && python -m pytest tests/test_gestor_metricas.py -v
```
Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add managers/gestor_metricas.py tests/test_gestor_metricas.py
git commit -m "feat: add alertas_tiempo_real with 4 alert types"
```

---

## Task 4: Analítica — `resumen_periodo` + `metricas_pedidos`

**Files:**
- Modify: `managers/gestor_metricas.py`
- Modify: `tests/test_gestor_metricas.py`

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/test_gestor_metricas.py

class TestResumenPeriodo:
    def test_claves_esperadas(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.count.return_value = 10
        session_mock.query.return_value.filter.return_value.all.return_value = []
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            desde = date(2026, 3, 15)
            hasta = date(2026, 3, 22)
            result = gestor.resumen_periodo(desde, hasta)
        claves = {
            'pedidos_completados', 'tasa_entrega_pct', 'tiempo_medio_ciclo_min',
            'ratio_cancelacion_pct', 'pedidos_por_forma_pago', 'dias_analizados'
        }
        assert claves == set(result.keys())

    def test_dias_analizados_correcto(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.count.return_value = 0
        session_mock.query.return_value.filter.return_value.all.return_value = []
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.resumen_periodo(date(2026, 3, 15), date(2026, 3, 22))
        assert result['dias_analizados'] == 8  # inclusive

    def test_tasa_entrega_none_cuando_sin_datos(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.count.return_value = 0
        session_mock.query.return_value.filter.return_value.all.return_value = []
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.resumen_periodo(date(2026, 3, 15), date(2026, 3, 22))
        assert result['tasa_entrega_pct'] is None


class TestMetricasPedidos:
    def test_claves_esperadas(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.all.return_value = []
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.metricas_pedidos(date(2026, 3, 15), date(2026, 3, 22))
        assert 'throughput_por_dia' in result
        assert 'tiempo_medio_por_fase_min' in result
        assert 'distribucion_estado_final' in result

    def test_fases_presentes(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.all.return_value = []
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.metricas_pedidos(date(2026, 3, 15), date(2026, 3, 22))
        fases = result['tiempo_medio_por_fase_min']
        assert 'confirmacion_a_preparacion' in fases
        assert 'preparacion' in fases
        assert 'espera_repartidor' in fases
        assert 'reparto' in fases
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/siemprearmando/proyectos/panchi-bot && source venv/bin/activate && python -m pytest tests/test_gestor_metricas.py::TestResumenPeriodo tests/test_gestor_metricas.py::TestMetricasPedidos -v
```

- [ ] **Step 3: Implement `resumen_periodo` and `metricas_pedidos`**

```python
# Replace stubs in managers/gestor_metricas.py

    def resumen_periodo(self, desde: date, hasta: date) -> dict:
        from models import Pedido, Reparto
        from sqlalchemy import func
        s = self.session
        desde_dt = datetime.combine(desde, datetime.min.time())
        hasta_dt = datetime.combine(hasta, datetime.max.time())

        completados = (
            s.query(Pedido)
            .filter(
                Pedido.Estado == 'entregado',
                Pedido.FechaPedido >= desde_dt,
                Pedido.FechaPedido <= hasta_dt,
            )
            .count()
        )

        cancelados = (
            s.query(Pedido)
            .filter(
                Pedido.Estado == 'cancelado',
                Pedido.FechaPedido >= desde_dt,
                Pedido.FechaPedido <= hasta_dt,
            )
            .count()
        )

        total_pedidos = completados + cancelados

        repartos = (
            s.query(Reparto)
            .filter(
                Reparto.updated_at >= desde_dt,
                Reparto.updated_at <= hasta_dt,
                Reparto.estado.in_(['entregado', 'no_entregado']),
            )
            .all()
        )
        entregados_r = sum(1 for r in repartos if r.estado == 'entregado')
        total_r = len(repartos)
        tasa_entrega = round(entregados_r * 100 / total_r) if total_r > 0 else None

        ratio_cancelacion = round(cancelados * 100 / total_pedidos) if total_pedidos > 0 else None

        tiempo_ciclo = self._tiempo_medio_ciclo_periodo(desde, hasta)

        rows_pago = (
            s.query(Pedido.FormaPago, func.count(Pedido.PedidoID))
            .filter(
                Pedido.Estado == 'entregado',
                Pedido.FechaPedido >= desde_dt,
                Pedido.FechaPedido <= hasta_dt,
            )
            .group_by(Pedido.FormaPago)
            .all()
        )
        pedidos_por_forma_pago = {fp: cnt for fp, cnt in rows_pago if fp}

        dias = (hasta - desde).days + 1

        return {
            'pedidos_completados': completados,
            'tasa_entrega_pct': tasa_entrega,
            'tiempo_medio_ciclo_min': tiempo_ciclo,
            'ratio_cancelacion_pct': ratio_cancelacion,
            'pedidos_por_forma_pago': pedidos_por_forma_pago,
            'dias_analizados': dias,
        }

    def metricas_pedidos(self, desde: date, hasta: date) -> dict:
        from models import Pedido, HistorialEstadoPedido
        from sqlalchemy import func, cast, Date
        s = self.session
        desde_dt = datetime.combine(desde, datetime.min.time())
        hasta_dt = datetime.combine(hasta, datetime.max.time())

        # Throughput por día
        rows_dia = (
            s.query(
                func.cast(Pedido.FechaPedido, Date).label('dia'),
                Pedido.Estado,
                func.count(Pedido.PedidoID),
            )
            .filter(
                Pedido.Estado.in_(['entregado', 'cancelado']),
                Pedido.FechaPedido >= desde_dt,
                Pedido.FechaPedido <= hasta_dt,
            )
            .group_by(func.cast(Pedido.FechaPedido, Date), Pedido.Estado)
            .all()
        )
        # Consolidar por día
        dias_dict: dict = {}
        for dia, estado, cnt in rows_dia:
            key = str(dia)
            if key not in dias_dict:
                dias_dict[key] = {'fecha': key, 'completados': 0, 'cancelados': 0}
            if estado == 'entregado':
                dias_dict[key]['completados'] = cnt
            elif estado == 'cancelado':
                dias_dict[key]['cancelados'] = cnt
        throughput = sorted(dias_dict.values(), key=lambda x: x['fecha'])

        # Tiempos por fase: calcular mediana entre pares de estados
        pares_fases = [
            ('confirmacion_a_preparacion', ['pagado', 'contra_reembolso'], 'en_preparacion'),
            ('preparacion', 'en_preparacion', 'preparado'),
            ('espera_repartidor', 'preparado', 'en_reparto'),
            ('reparto', 'en_reparto', 'entregado'),
        ]
        pedidos_entregados = (
            s.query(Pedido.PedidoID)
            .filter(
                Pedido.Estado == 'entregado',
                Pedido.FechaPedido >= desde_dt,
                Pedido.FechaPedido <= hasta_dt,
            )
            .all()
        )
        ids = [r.PedidoID for r in pedidos_entregados]

        tiempos_por_fase: dict = {}
        for nombre_fase, estado_a, estado_b in pares_fases:
            tiempos = []
            for pid in ids:
                if isinstance(estado_a, list):
                    # Buscar el más temprano de los estados_a
                    registros = (
                        s.query(HistorialEstadoPedido)
                        .filter(
                            HistorialEstadoPedido.pedido_id == pid,
                            HistorialEstadoPedido.estado.in_(estado_a + [estado_b])
                        )
                        .order_by(HistorialEstadoPedido.cambiado_en)
                        .all()
                    )
                    mapa = {}
                    for r in registros:
                        if r.estado not in mapa:
                            mapa[r.estado] = r.cambiado_en
                    t_a = min((mapa[e] for e in estado_a if e in mapa), default=None)
                    t_b = mapa.get(estado_b)
                    if t_a and t_b:
                        tiempos.append(max(0, round((t_b - t_a).total_seconds() / 60)))
                else:
                    t = self._tiempo_entre_estados(pid, estado_a, estado_b)
                    if t is not None:
                        tiempos.append(t)
            tiempos_por_fase[nombre_fase] = round(statistics.median(tiempos)) if tiempos else None

        # Distribución estados finales
        dist_rows = (
            s.query(Pedido.Estado, func.count(Pedido.PedidoID))
            .filter(
                Pedido.Estado.in_(_ESTADOS_TERMINALES),
                Pedido.FechaPedido >= desde_dt,
                Pedido.FechaPedido <= hasta_dt,
            )
            .group_by(Pedido.Estado)
            .all()
        )
        distribucion = {e: c for e, c in dist_rows}

        return {
            'throughput_por_dia': throughput,
            'tiempo_medio_por_fase_min': tiempos_por_fase,
            'distribucion_estado_final': distribucion,
        }
```

- [ ] **Step 4: Run tests**

```bash
cd /home/siemprearmando/proyectos/panchi-bot && source venv/bin/activate && python -m pytest tests/test_gestor_metricas.py -v
```
Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add managers/gestor_metricas.py tests/test_gestor_metricas.py
git commit -m "feat: add resumen_periodo and metricas_pedidos"
```

---

## Task 5: `metricas_picking` + `metricas_reparto`

**Files:**
- Modify: `managers/gestor_metricas.py`
- Modify: `tests/test_gestor_metricas.py`

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/test_gestor_metricas.py

class TestMetricasPicking:
    def test_claves_esperadas(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.all.return_value = []
        session_mock.query.return_value.filter.return_value.count.return_value = 0
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.metricas_picking(date(2026, 3, 15), date(2026, 3, 22))
        claves = {
            'tiempo_medio_picking_min', 'tiempo_medio_espera_asignacion_min',
            'items_total', 'items_encontrados_pct', 'items_sin_stock_pct',
            'items_sustituidos_pct', 'top_productos_sin_stock'
        }
        assert claves == set(result.keys())

    def test_porcentajes_suman_100_cuando_hay_items(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        # 10 items: 8 encontrado, 1 sin_stock, 1 sustituido
        items = []
        for _ in range(8):
            m = MagicMock(); m.estado = 'encontrado'; items.append(m)
        m1 = MagicMock(); m1.estado = 'sin_stock'; items.append(m1)
        m2 = MagicMock(); m2.estado = 'sustituido'; items.append(m2)
        session_mock.query.return_value.filter.return_value.all.return_value = items
        session_mock.query.return_value.filter.return_value.join.return_value.filter.return_value.all.return_value = []
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            with patch.object(gestor, '_picking_tiempos', return_value=(None, None)):
                result = gestor.metricas_picking(date(2026, 3, 15), date(2026, 3, 22))
        total = (result['items_encontrados_pct'] or 0) + (result['items_sin_stock_pct'] or 0) + (result['items_sustituidos_pct'] or 0)
        assert abs(total - 100) <= 1


class TestMetricasReparto:
    def test_claves_esperadas(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.all.return_value = []
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.metricas_reparto(date(2026, 3, 15), date(2026, 3, 22))
        claves = {
            'tiempo_medio_entrega_min', 'tiempo_medio_espera_antes_salida_min',
            'tasa_entrega_exitosa_pct', 'entregas_por_repartidor'
        }
        assert claves == set(result.keys())

    def test_excluye_repartos_sin_hora_salida(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        r1 = MagicMock()
        r1.hora_salida = None  # debe excluirse
        r1.hora_entrega_real = datetime(2026, 3, 22, 14, 30)
        r1.estado = 'entregado'
        r2 = MagicMock()
        r2.hora_salida = datetime(2026, 3, 22, 14, 0)
        r2.hora_entrega_real = datetime(2026, 3, 22, 14, 30)
        r2.estado = 'entregado'
        r2.empleado_id = 4
        r2.empleado = MagicMock(); r2.empleado.Nombre = 'Luis'
        session_mock.query.return_value.filter.return_value.all.return_value = [r1, r2]
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.metricas_reparto(date(2026, 3, 15), date(2026, 3, 22))
        # Solo r2 tiene hora_salida → tiempo_medio debe calcularse sobre 1 reparto (30 min)
        assert result['tiempo_medio_entrega_min'] == 30
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/siemprearmando/proyectos/panchi-bot && source venv/bin/activate && python -m pytest tests/test_gestor_metricas.py::TestMetricasPicking tests/test_gestor_metricas.py::TestMetricasReparto -v
```

- [ ] **Step 3: Implement `metricas_picking` and `metricas_reparto`**

```python
# Replace stubs in managers/gestor_metricas.py

    def metricas_picking(self, desde: date, hasta: date) -> dict:
        from models import PickingPedido, PickingItem, Producto
        from sqlalchemy import func
        s = self.session
        desde_dt = datetime.combine(desde, datetime.min.time())
        hasta_dt = datetime.combine(hasta, datetime.max.time())

        # Items del período
        items = (
            s.query(PickingItem)
            .join(PickingPedido, PickingItem.picking_pedido_id == PickingPedido.id)
            .filter(
                PickingPedido.updated_at >= desde_dt,
                PickingPedido.updated_at <= hasta_dt,
                PickingPedido.estado == 'completado',
            )
            .all()
        )
        items_total = len(items)
        if items_total > 0:
            encontrados = sum(1 for i in items if i.estado == 'encontrado')
            sin_stock = sum(1 for i in items if i.estado == 'sin_stock')
            sustituidos = sum(1 for i in items if i.estado == 'sustituido')
            items_encontrados_pct = round(encontrados * 100 / items_total)
            items_sin_stock_pct = round(sin_stock * 100 / items_total)
            items_sustituidos_pct = round(sustituidos * 100 / items_total)
        else:
            items_encontrados_pct = items_sin_stock_pct = items_sustituidos_pct = None

        # Tiempos de picking
        tiempo_medio_picking_min, tiempo_medio_espera_asignacion_min = self._picking_tiempos(desde_dt, hasta_dt)

        # Top productos sin stock
        top_sin_stock_rows = (
            s.query(PickingItem.producto_id, Producto.Nombre, func.count(PickingItem.id).label('veces'))
            .join(Producto, PickingItem.producto_id == Producto.ProductoID)
            .join(PickingPedido, PickingItem.picking_pedido_id == PickingPedido.id)
            .filter(
                PickingItem.estado == 'sin_stock',
                PickingPedido.updated_at >= desde_dt,
                PickingPedido.updated_at <= hasta_dt,
            )
            .group_by(PickingItem.producto_id, Producto.Nombre)
            .order_by(func.count(PickingItem.id).desc())
            .limit(10)
            .all()
        )
        top_productos_sin_stock = [
            {'producto_id': pid, 'nombre': nombre, 'veces_sin_stock': veces}
            for pid, nombre, veces in top_sin_stock_rows
        ]

        return {
            'tiempo_medio_picking_min': tiempo_medio_picking_min,
            'tiempo_medio_espera_asignacion_min': tiempo_medio_espera_asignacion_min,
            'items_total': items_total,
            'items_encontrados_pct': items_encontrados_pct,
            'items_sin_stock_pct': items_sin_stock_pct,
            'items_sustituidos_pct': items_sustituidos_pct,
            'top_productos_sin_stock': top_productos_sin_stock,
        }

    def _picking_tiempos(self, desde_dt: datetime, hasta_dt: datetime):
        from models import PickingPedido, HistorialEstadoPedido
        s = self.session
        pickings_completados = (
            s.query(PickingPedido)
            .filter(
                PickingPedido.estado == 'completado',
                PickingPedido.updated_at >= desde_dt,
                PickingPedido.updated_at <= hasta_dt,
            )
            .all()
        )
        tiempos_picking = []
        tiempos_espera = []
        for pp in pickings_completados:
            if pp.created_at and pp.updated_at:
                mins = round((pp.updated_at - pp.created_at).total_seconds() / 60)
                tiempos_picking.append(mins)
            # Tiempo espera asignación: desde PAGADO hasta que se asignó picker
            t = self._tiempo_entre_estados(pp.PedidoID, 'pagado', 'en_preparacion')
            if t is not None:
                tiempos_espera.append(t)
        tiempo_medio_picking = round(statistics.mean(tiempos_picking)) if tiempos_picking else None
        tiempo_espera_asig = round(statistics.mean(tiempos_espera)) if tiempos_espera else None
        return tiempo_medio_picking, tiempo_espera_asig

    def metricas_reparto(self, desde: date, hasta: date) -> dict:
        from models import Reparto, Empleado
        from sqlalchemy import func
        s = self.session
        desde_dt = datetime.combine(desde, datetime.min.time())
        hasta_dt = datetime.combine(hasta, datetime.max.time())

        repartos = (
            s.query(Reparto)
            .filter(
                Reparto.updated_at >= desde_dt,
                Reparto.updated_at <= hasta_dt,
                Reparto.estado.in_(['entregado', 'no_entregado']),
            )
            .all()
        )

        total = len(repartos)
        entregados = [r for r in repartos if r.estado == 'entregado']
        tasa_exitosa = round(len(entregados) * 100 / total) if total > 0 else None

        # Solo con hora_salida para tiempos
        con_salida = [r for r in entregados if r.hora_salida is not None]
        tiempos_entrega = []
        for r in con_salida:
            if r.hora_entrega_real and r.hora_salida:
                mins = round((r.hora_entrega_real - r.hora_salida).total_seconds() / 60)
                tiempos_entrega.append(mins)
        tiempo_medio_entrega = round(statistics.mean(tiempos_entrega)) if tiempos_entrega else None

        # Espera antes de salida (PREPARADO → salida)
        tiempos_espera_salida = []
        for r in con_salida:
            t = self._tiempo_entre_estados(r.pedido_id, 'preparado', 'en_reparto')
            if t is not None:
                tiempos_espera_salida.append(t)
        tiempo_espera_salida = round(statistics.mean(tiempos_espera_salida)) if tiempos_espera_salida else None

        # Por repartidor
        por_empleado: dict = {}
        for r in repartos:
            eid = r.empleado_id
            if not eid:
                continue
            if eid not in por_empleado:
                por_empleado[eid] = {'entregas': 0, 'tiempos': [], 'total': 0, 'nombre': None}
            por_empleado[eid]['total'] += 1
            if r.estado == 'entregado':
                por_empleado[eid]['entregas'] += 1
                if r.hora_salida and r.hora_entrega_real:
                    mins = round((r.hora_entrega_real - r.hora_salida).total_seconds() / 60)
                    por_empleado[eid]['tiempos'].append(mins)

        entregas_por_repartidor = []
        for eid, data in por_empleado.items():
            emp = s.query(Empleado).filter(Empleado.EmpleadoID == eid).first()
            nombre = emp.Nombre if emp else f'Empleado {eid}'
            tasa = round(data['entregas'] * 100 / data['total']) if data['total'] > 0 else None
            t_medio = round(statistics.mean(data['tiempos'])) if data['tiempos'] else None
            entregas_por_repartidor.append({
                'empleado_id': eid,
                'nombre': nombre,
                'entregas': data['entregas'],
                'tiempo_medio_min': t_medio,
                'tasa_exito_pct': tasa,
            })
        entregas_por_repartidor.sort(key=lambda x: x['entregas'], reverse=True)

        return {
            'tiempo_medio_entrega_min': tiempo_medio_entrega,
            'tiempo_medio_espera_antes_salida_min': tiempo_espera_salida,
            'tasa_entrega_exitosa_pct': tasa_exitosa,
            'entregas_por_repartidor': entregas_por_repartidor,
        }
```

- [ ] **Step 4: Run tests**

```bash
cd /home/siemprearmando/proyectos/panchi-bot && source venv/bin/activate && python -m pytest tests/test_gestor_metricas.py -v
```
Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add managers/gestor_metricas.py tests/test_gestor_metricas.py
git commit -m "feat: add metricas_picking and metricas_reparto"
```

---

## Task 6: `rendimiento_empleados` + `comparativa_empleados`

**Files:**
- Modify: `managers/gestor_metricas.py`
- Modify: `tests/test_gestor_metricas.py`

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/test_gestor_metricas.py

class TestRendimientoEmpleados:
    def test_devuelve_lista(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.all.return_value = []
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.rendimiento_empleados(date(2026, 3, 15), date(2026, 3, 22))
        assert isinstance(result, list)

    def test_productividad_cero_cuando_sin_horas(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        emp = MagicMock()
        emp.EmpleadoID = 7
        emp.Nombre = 'Ana'
        emp.rol = MagicMock(); emp.rol.nombre = 'picker'
        session_mock.query.return_value.filter.return_value.all.return_value = [emp]
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            with patch.object(gestor, '_horas_trabajadas', return_value=0.0):
                with patch.object(gestor, '_operaciones_empleado', return_value=[]):
                    result = gestor.rendimiento_empleados(date(2026, 3, 15), date(2026, 3, 22))
        assert result[0]['productividad_operaciones_hora'] == 0


class TestComparativaEmpleados:
    def test_requiere_rol(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.all.return_value = []
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.comparativa_empleados(date(2026, 3, 15), date(2026, 3, 22), 'picker')
        assert 'rol' in result
        assert result['rol'] == 'picker'
        assert 'ranking' in result
        assert 'media_equipo' in result

    def test_ranking_ordenado_por_productividad(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.all.return_value = []
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            with patch.object(gestor, 'rendimiento_empleados', return_value=[
                {'empleado_id': 1, 'nombre': 'A', 'rol': 'picker',
                 'operaciones_completadas': 50, 'horas_trabajadas': 20,
                 'productividad_operaciones_hora': 2.5, 'tiempo_medio_operacion_min': 12,
                 'ratio_incidencias_pct': 3, 'puntualidad_media_min': 2},
                {'empleado_id': 2, 'nombre': 'B', 'rol': 'picker',
                 'operaciones_completadas': 80, 'horas_trabajadas': 20,
                 'productividad_operaciones_hora': 4.0, 'tiempo_medio_operacion_min': 9,
                 'ratio_incidencias_pct': 1, 'puntualidad_media_min': 0},
            ]):
                result = gestor.comparativa_empleados(date(2026, 3, 15), date(2026, 3, 22), 'picker')
        assert result['ranking'][0]['posicion'] == 1
        assert result['ranking'][0]['productividad_operaciones_hora'] == 4.0
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/siemprearmando/proyectos/panchi-bot && source venv/bin/activate && python -m pytest tests/test_gestor_metricas.py::TestRendimientoEmpleados tests/test_gestor_metricas.py::TestComparativaEmpleados -v
```

- [ ] **Step 3: Implement both methods**

```python
# Replace stubs in managers/gestor_metricas.py

    def rendimiento_empleados(self, desde: date, hasta: date, rol: str | None = None) -> list[dict]:
        from models import Empleado, CheckIn, PickingItem, PickingPedido, Reparto
        from managers.gestor_empleado import GestorEmpleado
        s = self.session
        query = s.query(Empleado).join(Empleado.rol)
        if rol:
            from models import Rol
            query = query.filter(Rol.nombre == rol)
        empleados = query.all()

        gestor_emp = GestorEmpleado()
        result = []
        for emp in empleados:
            rol_nombre = emp.rol.nombre if emp.rol else None
            horas = self._horas_trabajadas(emp.EmpleadoID, desde, hasta)
            ops = self._operaciones_empleado(emp.EmpleadoID, rol_nombre, desde, hasta)
            num_ops = len(ops)
            productividad = round(num_ops / horas, 2) if horas > 0 else 0

            # Tiempo medio por operación
            if rol_nombre == 'picker' and ops:
                tiempos = [
                    round((op.updated_at - op.created_at).total_seconds() / 60)
                    for op in ops
                    if op.created_at and op.updated_at
                ]
                tiempo_medio = round(statistics.mean(tiempos)) if tiempos else None
            elif rol_nombre == 'repartidor' and ops:
                tiempos = [
                    round((op.hora_entrega_real - op.hora_salida).total_seconds() / 60)
                    for op in ops
                    if op.hora_salida and op.hora_entrega_real
                ]
                tiempo_medio = round(statistics.mean(tiempos)) if tiempos else None
            else:
                tiempo_medio = None

            # Ratio incidencias
            if rol_nombre == 'picker':
                todos_items = (
                    s.query(PickingItem)
                    .join(PickingPedido, PickingItem.picking_pedido_id == PickingPedido.id)
                    .filter(
                        PickingPedido.empleado_id == emp.EmpleadoID,
                        PickingPedido.updated_at >= datetime.combine(desde, datetime.min.time()),
                        PickingPedido.updated_at <= datetime.combine(hasta, datetime.max.time()),
                    )
                    .all()
                )
                total_items = len(todos_items)
                inc = sum(1 for i in todos_items if i.estado in ('sin_stock', 'sustituido'))
                ratio_inc = round(inc * 100 / total_items) if total_items > 0 else 0
            else:
                todos_repartos = (
                    s.query(Reparto)
                    .filter(
                        Reparto.empleado_id == emp.EmpleadoID,
                        Reparto.estado.in_(['entregado', 'no_entregado']),
                        Reparto.updated_at >= datetime.combine(desde, datetime.min.time()),
                        Reparto.updated_at <= datetime.combine(hasta, datetime.max.time()),
                    )
                    .all()
                )
                total_rep = len(todos_repartos)
                no_ent = sum(1 for r in todos_repartos if r.estado == 'no_entregado')
                ratio_inc = round(no_ent * 100 / total_rep) if total_rep > 0 else 0

            puntualidad_data = gestor_emp.puntualidad_empleado(emp.EmpleadoID, desde, hasta)
            puntualidad_media = puntualidad_data.get('media_minutos_tarde')

            result.append({
                'empleado_id': emp.EmpleadoID,
                'nombre': emp.Nombre,
                'rol': rol_nombre,
                'operaciones_completadas': num_ops,
                'horas_trabajadas': horas,
                'productividad_operaciones_hora': productividad,
                'tiempo_medio_operacion_min': tiempo_medio,
                'ratio_incidencias_pct': ratio_inc,
                'puntualidad_media_min': puntualidad_media,
            })
        return result

    def comparativa_empleados(self, desde: date, hasta: date, rol: str) -> dict:
        empleados_data = self.rendimiento_empleados(desde, hasta, rol=rol)
        ranking = sorted(
            empleados_data,
            key=lambda x: x['productividad_operaciones_hora'],
            reverse=True
        )
        for i, emp in enumerate(ranking):
            emp['posicion'] = i + 1

        # media_equipo: solo empleados con >=1 operación
        con_ops = [e for e in empleados_data if e['operaciones_completadas'] > 0]
        if con_ops:
            media_prod = round(statistics.mean(e['productividad_operaciones_hora'] for e in con_ops), 2)
            tiempos = [e['tiempo_medio_operacion_min'] for e in con_ops if e['tiempo_medio_operacion_min'] is not None]
            media_tiempo = round(statistics.mean(tiempos)) if tiempos else None
            ratios = [e['ratio_incidencias_pct'] for e in con_ops]
            media_ratio = round(statistics.mean(ratios)) if ratios else None
        else:
            media_prod = media_tiempo = media_ratio = None

        return {
            'rol': rol,
            'periodo': {'desde': str(desde), 'hasta': str(hasta)},
            'ranking': ranking,
            'media_equipo': {
                'productividad_operaciones_hora': media_prod,
                'tiempo_medio_operacion_min': media_tiempo,
                'ratio_incidencias_pct': media_ratio,
            },
        }
```

- [ ] **Step 4: Run tests**

```bash
cd /home/siemprearmando/proyectos/panchi-bot && source venv/bin/activate && python -m pytest tests/test_gestor_metricas.py -v
```
Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add managers/gestor_metricas.py tests/test_gestor_metricas.py
git commit -m "feat: add rendimiento_empleados and comparativa_empleados"
```

---

## Task 7: `ficha_empleado` + `asistencia_periodo` + `metricas_incidencias`

**Files:**
- Modify: `managers/gestor_metricas.py`
- Modify: `tests/test_gestor_metricas.py`

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/test_gestor_metricas.py

class TestFichaEmpleado:
    def test_claves_esperadas(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        emp_mock = MagicMock()
        emp_mock.EmpleadoID = 7
        emp_mock.Nombre = 'Ana'
        emp_mock.rol = MagicMock(); emp_mock.rol.nombre = 'picker'
        session_mock.query.return_value.filter.return_value.first.return_value = emp_mock
        session_mock.query.return_value.filter.return_value.all.return_value = []
        session_mock.query.return_value.join.return_value.filter.return_value.all.return_value = []
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            with patch.object(gestor, '_horas_trabajadas', return_value=0.0):
                with patch.object(gestor, '_operaciones_empleado', return_value=[]):
                    from managers.gestor_empleado import GestorEmpleado
                    with patch.object(GestorEmpleado, 'puntualidad_empleado',
                                      return_value={'tasa_puntualidad_pct': 100, 'media_minutos_tarde': 0,
                                                    'tarde': 0, 'puntuales': 0}):
                        result = gestor.ficha_empleado(7, date(2026, 3, 15), date(2026, 3, 22))
        assert 'empleado_id' in result
        assert 'asistencia' in result
        assert 'puntualidad' in result
        assert 'rendimiento' in result
        assert 'evolucion_semanal' in result


class TestAsistenciaPeriodo:
    def test_claves_esperadas(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        session_mock.query.return_value.join.return_value.outerjoin.return_value.outerjoin.return_value.filter.return_value.all.return_value = []
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.asistencia_periodo(date(2026, 3, 15), date(2026, 3, 22))
        assert 'tasa_asistencia_global_pct' in result
        assert 'tasa_puntualidad_global_pct' in result
        assert 'por_empleado' in result


class TestMetricasIncidencias:
    def test_claves_esperadas(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.all.return_value = []
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.metricas_incidencias(date(2026, 3, 15), date(2026, 3, 22))
        assert 'total' in result
        assert 'por_tipo' in result
        assert 'por_empleado' in result
        assert 'productos_mas_afectados' in result

    def test_tipos_presentes(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.all.return_value = []
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.metricas_incidencias(date(2026, 3, 15), date(2026, 3, 22))
        assert 'sin_stock' in result['por_tipo']
        assert 'entrega_fallida' in result['por_tipo']
        assert 'sustitucion' in result['por_tipo']
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/siemprearmando/proyectos/panchi-bot && source venv/bin/activate && python -m pytest tests/test_gestor_metricas.py::TestFichaEmpleado tests/test_gestor_metricas.py::TestAsistenciaPeriodo tests/test_gestor_metricas.py::TestMetricasIncidencias -v
```

- [ ] **Step 3: Implement all three methods**

```python
# Replace stubs in managers/gestor_metricas.py

    def ficha_empleado(self, empleado_id: int, desde: date, hasta: date) -> dict:
        from models import Empleado, Turno, CheckIn, Ausencia, PickingPedido, Reparto
        from managers.gestor_empleado import GestorEmpleado
        s = self.session
        emp = s.query(Empleado).filter(Empleado.EmpleadoID == empleado_id).first()
        if not emp:
            return {}
        rol_nombre = emp.rol.nombre if emp.rol else None

        # Asistencia
        turnos = (
            s.query(Turno)
            .filter(Turno.empleado_id == empleado_id, Turno.fecha >= desde, Turno.fecha <= hasta)
            .all()
        )
        dias_planificados = len(turnos)
        checkins = (
            s.query(CheckIn)
            .filter(CheckIn.empleado_id == empleado_id, CheckIn.fecha >= desde, CheckIn.fecha <= hasta)
            .all()
        )
        dias_trabajados = len(checkins)
        ausencias = (
            s.query(Ausencia)
            .filter(Ausencia.empleado_id == empleado_id, Ausencia.fecha >= desde, Ausencia.fecha <= hasta)
            .count()
        )
        tasa_asistencia = round(dias_trabajados * 100 / dias_planificados) if dias_planificados > 0 else None

        # Puntualidad
        gestor_emp = GestorEmpleado()
        punt_data = gestor_emp.puntualidad_empleado(empleado_id, desde, hasta)

        # Rendimiento
        horas = self._horas_trabajadas(empleado_id, desde, hasta)
        ops = self._operaciones_empleado(empleado_id, rol_nombre, desde, hasta)
        num_ops = len(ops)
        productividad = round(num_ops / horas, 2) if horas > 0 else 0
        if rol_nombre == 'picker' and ops:
            tiempos = [round((op.updated_at - op.created_at).total_seconds() / 60)
                       for op in ops if op.created_at and op.updated_at]
        elif rol_nombre == 'repartidor' and ops:
            tiempos = [round((op.hora_entrega_real - op.hora_salida).total_seconds() / 60)
                       for op in ops if op.hora_salida and op.hora_entrega_real]
        else:
            tiempos = []
        tiempo_medio = round(statistics.mean(tiempos)) if tiempos else None

        # Evolución semanal
        evolucion = self._evolucion_semanal(empleado_id, rol_nombre, desde, hasta)

        return {
            'empleado_id': empleado_id,
            'nombre': emp.Nombre,
            'rol': rol_nombre,
            'asistencia': {
                'dias_planificados': dias_planificados,
                'dias_trabajados': dias_trabajados,
                'ausencias': ausencias,
                'tasa_asistencia_pct': tasa_asistencia,
            },
            'puntualidad': punt_data,
            'rendimiento': {
                'operaciones_completadas': num_ops,
                'horas_trabajadas': horas,
                'productividad_operaciones_hora': productividad,
                'tiempo_medio_operacion_min': tiempo_medio,
            },
            'evolucion_semanal': evolucion,
        }

    def _evolucion_semanal(self, empleado_id: int, rol: str, desde: date, hasta: date) -> list[dict]:
        """Punto por semana natural (lunes-domingo) dentro del rango."""
        from models import PickingPedido, Reparto
        semanas = []
        # Hallar el lunes de la semana que contiene 'desde'
        lunes = desde - timedelta(days=desde.weekday())
        while lunes <= hasta:
            fin_semana = lunes + timedelta(days=6)
            ops = self._operaciones_empleado(empleado_id, rol, lunes, fin_semana)
            if ops:
                if rol == 'picker':
                    tiempos = [round((op.updated_at - op.created_at).total_seconds() / 60)
                               for op in ops if op.created_at and op.updated_at]
                else:
                    tiempos = [round((op.hora_entrega_real - op.hora_salida).total_seconds() / 60)
                               for op in ops if op.hora_salida and op.hora_entrega_real]
                tiempo_medio = round(statistics.mean(tiempos)) if tiempos else None
            else:
                tiempo_medio = None
            semanas.append({
                'semana_inicio': str(lunes),
                'operaciones': len(ops),
                'tiempo_medio_min': tiempo_medio,
            })
            lunes += timedelta(weeks=1)
        return semanas

    def asistencia_periodo(self, desde: date, hasta: date) -> dict:
        from models import Turno, CheckIn, Ausencia, Empleado
        s = self.session
        rows = (
            s.query(Turno, CheckIn, Empleado)
            .join(Empleado, Turno.empleado_id == Empleado.EmpleadoID)
            .outerjoin(
                CheckIn,
                (CheckIn.empleado_id == Turno.empleado_id) & (CheckIn.fecha == Turno.fecha)
            )
            .outerjoin(
                Ausencia,
                (Ausencia.empleado_id == Turno.empleado_id) & (Ausencia.fecha == Turno.fecha)
            )
            .filter(Turno.fecha >= desde, Turno.fecha <= hasta)
            .all()
        )

        # Acumular por empleado
        por_emp: dict = {}
        for turno, checkin, empleado in rows:
            eid = empleado.EmpleadoID
            if eid not in por_emp:
                por_emp[eid] = {
                    'empleado_id': eid,
                    'nombre': empleado.Nombre,
                    'dias_planificados': 0,
                    'dias_trabajados': 0,
                    'ausencias': 0,
                    'minutos_tarde': [],
                    'checkins_con_turno': 0,
                }
            por_emp[eid]['dias_planificados'] += 1
            if checkin:
                por_emp[eid]['dias_trabajados'] += 1
                if checkin.minutos_tarde is not None:
                    por_emp[eid]['minutos_tarde'].append(checkin.minutos_tarde)
                    por_emp[eid]['checkins_con_turno'] += 1
            else:
                por_emp[eid]['ausencias'] += 1

        por_empleado_list = []
        total_planificados = total_trabajados = 0
        total_puntuales = total_check = 0
        for eid, data in por_emp.items():
            total_planificados += data['dias_planificados']
            total_trabajados += data['dias_trabajados']
            min_tarde = data['minutos_tarde']
            tasa_puntualidad = None
            media_tarde = None
            if min_tarde:
                puntuales = sum(1 for m in min_tarde if m <= 5)
                total_puntuales += puntuales
                total_check += len(min_tarde)
                tasa_puntualidad = round(puntuales * 100 / len(min_tarde))
                media_tarde = round(statistics.mean(min_tarde), 1)
            tasa_asistencia = round(data['dias_trabajados'] * 100 / data['dias_planificados']) if data['dias_planificados'] > 0 else None
            por_empleado_list.append({
                'empleado_id': eid,
                'nombre': data['nombre'],
                'dias_planificados': data['dias_planificados'],
                'dias_trabajados': data['dias_trabajados'],
                'ausencias': data['ausencias'],
                'tasa_asistencia_pct': tasa_asistencia,
                'tasa_puntualidad_pct': tasa_puntualidad,
                'media_minutos_tarde': media_tarde,
            })

        tasa_global_asistencia = round(total_trabajados * 100 / total_planificados) if total_planificados > 0 else None
        tasa_global_puntualidad = round(total_puntuales * 100 / total_check) if total_check > 0 else None

        return {
            'tasa_asistencia_global_pct': tasa_global_asistencia,
            'tasa_puntualidad_global_pct': tasa_global_puntualidad,
            'por_empleado': por_empleado_list,
        }

    def metricas_incidencias(self, desde: date, hasta: date) -> dict:
        from models import PickingItem, PickingPedido, Reparto, Empleado, Producto
        from sqlalchemy import func
        s = self.session
        desde_dt = datetime.combine(desde, datetime.min.time())
        hasta_dt = datetime.combine(hasta, datetime.max.time())

        # Picking incidencias
        items_inc = (
            s.query(PickingItem, PickingPedido)
            .join(PickingPedido, PickingItem.picking_pedido_id == PickingPedido.id)
            .filter(
                PickingItem.estado.in_(['sin_stock', 'sustituido']),
                PickingPedido.updated_at >= desde_dt,
                PickingPedido.updated_at <= hasta_dt,
            )
            .all()
        )

        # Reparto incidencias
        repartos_fallidos = (
            s.query(Reparto)
            .filter(
                Reparto.estado == 'no_entregado',
                Reparto.updated_at >= desde_dt,
                Reparto.updated_at <= hasta_dt,
            )
            .all()
        )

        sin_stock = sum(1 for item, _ in items_inc if item.estado == 'sin_stock')
        sustitucion = sum(1 for item, _ in items_inc if item.estado == 'sustituido')
        entrega_fallida = len(repartos_fallidos)
        total = sin_stock + sustitucion + entrega_fallida

        # Por empleado
        por_emp_picking: dict = {}
        for item, pp in items_inc:
            if pp.empleado_id is None:
                continue
            eid = pp.empleado_id
            por_emp_picking[eid] = por_emp_picking.get(eid, 0) + 1

        por_emp_reparto: dict = {}
        for r in repartos_fallidos:
            if r.empleado_id is None:
                continue
            por_emp_reparto[r.empleado_id] = por_emp_reparto.get(r.empleado_id, 0) + 1

        todos_eids = set(por_emp_picking) | set(por_emp_reparto)
        por_empleado_list = []
        for eid in todos_eids:
            emp = s.query(Empleado).filter(Empleado.EmpleadoID == eid).first()
            nombre = emp.Nombre if emp else f'Empleado {eid}'
            total_inc_emp = por_emp_picking.get(eid, 0) + por_emp_reparto.get(eid, 0)
            # ratio sobre operaciones del empleado
            ops = self._operaciones_empleado(eid, emp.rol.nombre if emp and emp.rol else 'picker', desde, hasta)
            ratio = round(total_inc_emp * 100 / len(ops)) if ops else None
            por_empleado_list.append({
                'empleado_id': eid,
                'nombre': nombre,
                'total_incidencias': total_inc_emp,
                'ratio_sobre_operaciones_pct': ratio,
            })
        por_empleado_list.sort(key=lambda x: x['total_incidencias'], reverse=True)

        # Top 10 productos sin stock
        top_rows = (
            s.query(PickingItem.producto_id, Producto.Nombre, func.count(PickingItem.id).label('veces'))
            .join(Producto, PickingItem.producto_id == Producto.ProductoID)
            .join(PickingPedido, PickingItem.picking_pedido_id == PickingPedido.id)
            .filter(
                PickingItem.estado == 'sin_stock',
                PickingPedido.updated_at >= desde_dt,
                PickingPedido.updated_at <= hasta_dt,
            )
            .group_by(PickingItem.producto_id, Producto.Nombre)
            .order_by(func.count(PickingItem.id).desc())
            .limit(10)
            .all()
        )
        productos_mas_afectados = [
            {'producto_id': pid, 'nombre': nombre, 'veces_sin_stock': veces}
            for pid, nombre, veces in top_rows
        ]

        return {
            'total': total,
            'por_tipo': {
                'sin_stock': sin_stock,
                'entrega_fallida': entrega_fallida,
                'sustitucion': sustitucion,
            },
            'por_empleado': por_empleado_list,
            'productos_mas_afectados': productos_mas_afectados,
        }
```

- [ ] **Step 4: Run all manager tests**

```bash
cd /home/siemprearmando/proyectos/panchi-bot && source venv/bin/activate && python -m pytest tests/test_gestor_metricas.py -v
```
Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add managers/gestor_metricas.py tests/test_gestor_metricas.py
git commit -m "feat: add ficha_empleado, asistencia_periodo, metricas_incidencias"
```

---

## Task 8: Blueprint `metricas_operacion.py` + register in `main.py`

**Files:**
- Create: `blueprints/metricas_operacion.py`
- Modify: `main.py`
- Create: `tests/test_metricas_operacion.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_metricas_operacion.py
from unittest.mock import patch, MagicMock
import pytest


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client, rol='manager'):
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = rol


class TestMetricasOperacionAuth:
    def test_sin_sesion_redirige(self, client):
        resp = client.get('/metricas/operacion/resumen')
        assert resp.status_code in (302, 401)

    def test_rol_picker_no_accede(self, client):
        _login(client, rol='picker')
        resp = client.get('/metricas/operacion/resumen')
        assert resp.status_code in (302, 403)


class TestMetricasOperacionResumen:
    def test_devuelve_200_y_ok(self, client):
        _login(client)
        datos = {
            'pedidos_activos': 5, 'empleados_en_turno': 3,
            'cola_picking_count': 1, 'cola_reparto_count': 0,
            'entregados_hoy': 10, 'tasa_entrega_hoy_pct': 90,
            'tiempo_medio_ciclo_hoy_min': 25,
        }
        with patch('blueprints.metricas_operacion.gestor_metricas.resumen_operacion', return_value=datos):
            resp = client.get('/metricas/operacion/resumen')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert 'pedidos_activos' in data['data']

    def test_estructura_respuesta(self, client):
        _login(client)
        with patch('blueprints.metricas_operacion.gestor_metricas.resumen_operacion', return_value={}):
            resp = client.get('/metricas/operacion/resumen')
        body = resp.get_json()
        assert 'ok' in body
        assert 'data' in body


class TestMetricasOperacionAsistencia:
    def test_devuelve_lista(self, client):
        _login(client)
        with patch('blueprints.metricas_operacion.gestor_metricas.asistencia_hoy', return_value=[{'empleado_id': 1}]):
            resp = client.get('/metricas/operacion/asistencia')
        assert resp.status_code == 200
        assert isinstance(resp.get_json()['data'], list)


class TestMetricasOperacionColas:
    def test_devuelve_dict_con_colas(self, client):
        _login(client)
        colas = {'cola_picking': [], 'cola_reparto': []}
        with patch('blueprints.metricas_operacion.gestor_metricas.colas_detalle', return_value=colas):
            resp = client.get('/metricas/operacion/colas')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert 'cola_picking' in data
        assert 'cola_reparto' in data


class TestMetricasOperacionPedidosEstado:
    def test_devuelve_dict(self, client):
        _login(client)
        with patch('blueprints.metricas_operacion.gestor_metricas.pedidos_por_estado',
                   return_value={'en_preparacion': 4}):
            resp = client.get('/metricas/operacion/pedidos-estado')
        assert resp.status_code == 200


class TestMetricasOperacionAlertas:
    def test_devuelve_lista(self, client):
        _login(client)
        with patch('blueprints.metricas_operacion.gestor_metricas.alertas_tiempo_real', return_value=[]):
            resp = client.get('/metricas/operacion/alertas')
        assert resp.status_code == 200
        assert isinstance(resp.get_json()['data'], list)
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/siemprearmando/proyectos/panchi-bot && source venv/bin/activate && python -m pytest tests/test_metricas_operacion.py -v 2>&1 | head -30
```
Expected: import error or 404

- [ ] **Step 3: Create the blueprint**

```python
# blueprints/metricas_operacion.py
import logging
from flask import Blueprint, jsonify

from blueprints.auth import requiere_rol
from managers.gestor_metricas import GestorMetricas

logger = logging.getLogger(__name__)
blueprint_metricas_operacion = Blueprint('metricas_operacion', __name__)
gestor_metricas = GestorMetricas()


def _ok(data):
    return jsonify({'ok': True, 'data': data})


def _err(msg, code=400):
    return jsonify({'ok': False, 'error': msg}), code


@blueprint_metricas_operacion.route('/metricas/operacion/resumen')
@requiere_rol('admin', 'manager')
def resumen():
    return _ok(gestor_metricas.resumen_operacion())


@blueprint_metricas_operacion.route('/metricas/operacion/asistencia')
@requiere_rol('admin', 'manager')
def asistencia():
    return _ok(gestor_metricas.asistencia_hoy())


@blueprint_metricas_operacion.route('/metricas/operacion/colas')
@requiere_rol('admin', 'manager')
def colas():
    return _ok(gestor_metricas.colas_detalle())


@blueprint_metricas_operacion.route('/metricas/operacion/pedidos-estado')
@requiere_rol('admin', 'manager')
def pedidos_estado():
    return _ok(gestor_metricas.pedidos_por_estado())


@blueprint_metricas_operacion.route('/metricas/operacion/alertas')
@requiere_rol('admin', 'manager')
def alertas():
    return _ok(gestor_metricas.alertas_tiempo_real())
```

- [ ] **Step 4: Register in `main.py`**

In `main.py`, inside `create_app()` after the existing blueprint imports and registrations, add:

```python
    from blueprints.metricas_operacion import blueprint_metricas_operacion
    app.register_blueprint(blueprint_metricas_operacion)
```

- [ ] **Step 5: Run blueprint tests**

```bash
cd /home/siemprearmando/proyectos/panchi-bot && source venv/bin/activate && python -m pytest tests/test_metricas_operacion.py -v
```
Expected: all PASSED

- [ ] **Step 6: Run full suite to check no regressions**

```bash
cd /home/siemprearmando/proyectos/panchi-bot && source venv/bin/activate && python -m pytest -v --tb=short 2>&1 | tail -20
```

- [ ] **Step 7: Commit**

```bash
git add blueprints/metricas_operacion.py main.py tests/test_metricas_operacion.py
git commit -m "feat: add blueprint metricas_operacion with 5 endpoints"
```

---

## Task 9: Blueprint `metricas_analitica.py` + register in `main.py`

**Files:**
- Create: `blueprints/metricas_analitica.py`
- Modify: `main.py`
- Create: `tests/test_metricas_analitica.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_metricas_analitica.py
from datetime import date, timedelta
from unittest.mock import patch
import pytest


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client, rol='manager'):
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = rol


class TestAnaliticaAuth:
    def test_sin_sesion_redirige(self, client):
        resp = client.get('/metricas/analitica/resumen')
        assert resp.status_code in (302, 401)


class TestAnaliticaFechasDefault:
    def test_sin_params_usa_7_dias(self, client):
        _login(client)
        with patch('blueprints.metricas_analitica.gestor_metricas.resumen_periodo',
                   return_value={}) as mock_rp:
            client.get('/metricas/analitica/resumen')
        args = mock_rp.call_args[0]
        desde, hasta = args[0], args[1]
        assert hasta == date.today()
        assert (hasta - desde).days == 6  # 7 días inclusive


class TestAnaliticaResumen:
    def test_devuelve_200_y_ok(self, client):
        _login(client)
        with patch('blueprints.metricas_analitica.gestor_metricas.resumen_periodo', return_value={'dias_analizados': 7}):
            resp = client.get('/metricas/analitica/resumen')
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True


class TestAnaliticaComparativaRolRequerido:
    def test_sin_rol_devuelve_400(self, client):
        _login(client)
        with patch('blueprints.metricas_analitica.gestor_metricas.comparativa_empleados', return_value={}):
            resp = client.get('/metricas/analitica/comparativa')
        assert resp.status_code == 400

    def test_con_rol_devuelve_200(self, client):
        _login(client)
        with patch('blueprints.metricas_analitica.gestor_metricas.comparativa_empleados',
                   return_value={'rol': 'picker', 'ranking': [], 'media_equipo': {}}):
            resp = client.get('/metricas/analitica/comparativa?rol=picker')
        assert resp.status_code == 200


class TestAnaliticaEmpleadoFicha:
    def test_devuelve_200_con_id(self, client):
        _login(client)
        with patch('blueprints.metricas_analitica.gestor_metricas.ficha_empleado',
                   return_value={'empleado_id': 7}):
            resp = client.get('/metricas/analitica/empleado/7')
        assert resp.status_code == 200


class TestAnaliticaEmpleadosRolOpcional:
    def test_sin_rol_llama_con_none(self, client):
        _login(client)
        with patch('blueprints.metricas_analitica.gestor_metricas.rendimiento_empleados',
                   return_value=[]) as mock_re:
            client.get('/metricas/analitica/empleados')
        _, kwargs = mock_re.call_args
        assert kwargs.get('rol') is None

    def test_con_rol_lo_pasa(self, client):
        _login(client)
        with patch('blueprints.metricas_analitica.gestor_metricas.rendimiento_empleados',
                   return_value=[]) as mock_re:
            client.get('/metricas/analitica/empleados?rol=picker')
        _, kwargs = mock_re.call_args
        assert kwargs.get('rol') == 'picker'
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/siemprearmando/proyectos/panchi-bot && source venv/bin/activate && python -m pytest tests/test_metricas_analitica.py -v 2>&1 | head -30
```

- [ ] **Step 3: Create the blueprint**

```python
# blueprints/metricas_analitica.py
import logging
from datetime import date, timedelta

from flask import Blueprint, jsonify, request

from blueprints.auth import requiere_rol
from managers.gestor_metricas import GestorMetricas

logger = logging.getLogger(__name__)
blueprint_metricas_analitica = Blueprint('metricas_analitica', __name__)
gestor_metricas = GestorMetricas()


def _ok(data):
    return jsonify({'ok': True, 'data': data})


def _err(msg, code=400):
    return jsonify({'ok': False, 'error': msg}), code


def _parse_rango():
    """Parse ?desde=&hasta= query params. Default: last 7 days."""
    hasta_str = request.args.get('hasta')
    desde_str = request.args.get('desde')
    hasta = date.fromisoformat(hasta_str) if hasta_str else date.today()
    desde = date.fromisoformat(desde_str) if desde_str else hasta - timedelta(days=6)
    return desde, hasta


@blueprint_metricas_analitica.route('/metricas/analitica/resumen')
@requiere_rol('admin', 'manager')
def resumen():
    desde, hasta = _parse_rango()
    return _ok(gestor_metricas.resumen_periodo(desde, hasta))


@blueprint_metricas_analitica.route('/metricas/analitica/pedidos')
@requiere_rol('admin', 'manager')
def pedidos():
    desde, hasta = _parse_rango()
    return _ok(gestor_metricas.metricas_pedidos(desde, hasta))


@blueprint_metricas_analitica.route('/metricas/analitica/picking')
@requiere_rol('admin', 'manager')
def picking():
    desde, hasta = _parse_rango()
    return _ok(gestor_metricas.metricas_picking(desde, hasta))


@blueprint_metricas_analitica.route('/metricas/analitica/reparto')
@requiere_rol('admin', 'manager')
def reparto():
    desde, hasta = _parse_rango()
    return _ok(gestor_metricas.metricas_reparto(desde, hasta))


@blueprint_metricas_analitica.route('/metricas/analitica/empleados')
@requiere_rol('admin', 'manager')
def empleados():
    desde, hasta = _parse_rango()
    rol = request.args.get('rol') or None
    return _ok(gestor_metricas.rendimiento_empleados(desde, hasta, rol=rol))


@blueprint_metricas_analitica.route('/metricas/analitica/empleado/<int:empleado_id>')
@requiere_rol('admin', 'manager')
def ficha_empleado(empleado_id: int):
    desde, hasta = _parse_rango()
    return _ok(gestor_metricas.ficha_empleado(empleado_id, desde, hasta))


@blueprint_metricas_analitica.route('/metricas/analitica/comparativa')
@requiere_rol('admin', 'manager')
def comparativa():
    rol = request.args.get('rol')
    if not rol or rol not in ('picker', 'repartidor'):
        return _err("Parámetro 'rol' requerido: picker | repartidor")
    desde, hasta = _parse_rango()
    return _ok(gestor_metricas.comparativa_empleados(desde, hasta, rol))


@blueprint_metricas_analitica.route('/metricas/analitica/asistencia')
@requiere_rol('admin', 'manager')
def asistencia():
    desde, hasta = _parse_rango()
    return _ok(gestor_metricas.asistencia_periodo(desde, hasta))


@blueprint_metricas_analitica.route('/metricas/analitica/incidencias')
@requiere_rol('admin', 'manager')
def incidencias():
    desde, hasta = _parse_rango()
    return _ok(gestor_metricas.metricas_incidencias(desde, hasta))
```

- [ ] **Step 4: Register in `main.py`**

After the `metricas_operacion` import/register block added in Task 8:

```python
    from blueprints.metricas_analitica import blueprint_metricas_analitica
    app.register_blueprint(blueprint_metricas_analitica)
```

- [ ] **Step 5: Run blueprint tests**

```bash
cd /home/siemprearmando/proyectos/panchi-bot && source venv/bin/activate && python -m pytest tests/test_metricas_analitica.py -v
```
Expected: all PASSED

- [ ] **Step 6: Run full suite**

```bash
cd /home/siemprearmando/proyectos/panchi-bot && source venv/bin/activate && python -m pytest -v --tb=short 2>&1 | tail -25
```
Expected: only the 3 pre-existing `TestWebhookMonei` failures

- [ ] **Step 7: Commit**

```bash
git add blueprints/metricas_analitica.py main.py tests/test_metricas_analitica.py
git commit -m "feat: add blueprint metricas_analitica with 9 endpoints"
```

---

## Final verification

- [ ] Run full test suite and confirm only pre-existing failures remain:

```bash
cd /home/siemprearmando/proyectos/panchi-bot && source venv/bin/activate && python -m pytest -v --tb=short 2>&1 | grep -E "PASSED|FAILED|ERROR"
```

- [ ] Confirm new files exist:

```bash
ls -la managers/gestor_metricas.py blueprints/metricas_operacion.py blueprints/metricas_analitica.py tests/test_gestor_metricas.py tests/test_metricas_operacion.py tests/test_metricas_analitica.py
```
