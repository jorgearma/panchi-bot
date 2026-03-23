# Sprint 6 — Planificación de Turnos

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `/dashboard/turnos` with a third tab "Planificación" that lets admins ver, crear, editar y cancelar los turnos asignados a trabajadores (pasados y futuros).

**Approach:** Three tasks following the same TDD pattern. Manager → Routes → Template. The template modifies the existing `turnos.html` (444 lines) by adding a 3rd tab, new Alpine state, and a create/edit modal.

**Tech Stack:** Same as previous sprints. No new CDN dependencies.

---

## Data Model Reference

| Model | Key fields |
|-------|-----------|
| `Turno` | `id`, `empleado_id → Empleado`, `fecha (Date)`, `hora_inicio (Time)`, `hora_fin (Time)`, `tipo (mañana\|tarde\|noche\|partido)`, `estado (planificado\|completado\|cancelado)`, `notas`, `creado_por (FK empleados)` |
| `Empleado` | `EmpleadoID`, `Nombre`, `Apellido`, `activo`, `rol_id → Rol.nombre` |

Existing helper already available: `GET /dashboard/empleados` → `[{id, nombre, rol}]` (calls `gestor_dashboard.empleados_disponibles()`).

---

## File Map

| Action | File | What changes |
|--------|------|-------------|
| Modify | `managers/gestor_dashboard.py` | Add 4 methods: `turnos_planificacion`, `crear_turno`, `editar_turno`, `cancelar_turno` |
| Modify | `blueprints/dashboard.py` | Add 4 routes (1 GET JSON + 3 POST JSON) before `# Write endpoints` block |
| Modify | `templates/dashboard/turnos.html` | Add 3rd tab + modal + Alpine state extensions |
| Create | `tests/test_dashboard_sprint6.py` | New test file |

---

### Task 1: GestorDashboard — 4 new methods

**Files:**
- Modify: `managers/gestor_dashboard.py` (append to class, after `estadisticas()`)
- Create: `tests/test_dashboard_sprint6.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_dashboard_sprint6.py
from unittest.mock import patch, PropertyMock, MagicMock
import pytest


# ── Task 1: Manager ──────────────────────────────────────────────────────────

def test_turnos_planificacion_devuelve_claves_esperadas(app):
    """turnos_planificacion() devuelve {turnos, total, page, pages}."""
    from services import gestor_dashboard
    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            mock_q = mock_session.return_value.query.return_value
            mock_q.join.return_value = mock_q
            mock_q.filter.return_value = mock_q
            mock_q.order_by.return_value = mock_q
            mock_q.count.return_value = 0
            mock_q.offset.return_value = mock_q
            mock_q.limit.return_value = mock_q
            mock_q.all.return_value = []

            result = gestor_dashboard.turnos_planificacion()

            assert 'turnos' in result
            assert 'total' in result
            assert 'page' in result
            assert 'pages' in result
            assert isinstance(result['turnos'], list)


def test_crear_turno_devuelve_ok_con_datos_validos(app):
    """crear_turno() devuelve {ok: True, turno_id} cuando el empleado existe."""
    from services import gestor_dashboard
    with app.app_context():
        emp_mock = MagicMock()
        emp_mock.EmpleadoID = 1

        turno_mock = MagicMock()
        turno_mock.id = 42

        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            s = mock_session.return_value
            s.query.return_value.filter_by.return_value.first.return_value = emp_mock
            s.add = MagicMock()
            s.flush = MagicMock()
            s.commit = MagicMock()

            # Simulate ORM populating turno.id after flush() (not after add())
            def flush_side_effect():
                # find the Turno object that was added and set its id
                for call in s.add.call_args_list:
                    obj = call[0][0]
                    obj.id = 42
            s.flush.side_effect = flush_side_effect

            result = gestor_dashboard.crear_turno(
                empleado_id=1,
                fecha='2026-04-01',
                hora_inicio='09:00',
                hora_fin='17:00',
            )

            assert result['ok'] is True
            assert 'turno_id' in result
            s.flush.assert_called_once()


def test_crear_turno_devuelve_error_si_empleado_no_existe(app):
    """crear_turno() devuelve {ok: False} si el empleado no existe."""
    from services import gestor_dashboard
    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            mock_session.return_value.query.return_value.filter_by.return_value.first.return_value = None

            result = gestor_dashboard.crear_turno(
                empleado_id=99999,
                fecha='2026-04-01',
                hora_inicio='09:00',
                hora_fin='17:00',
            )

            assert result['ok'] is False
            assert 'error' in result


def test_editar_turno_devuelve_ok_si_turno_existe(app):
    """editar_turno() devuelve {ok: True} cuando el turno existe y no está cancelado."""
    from services import gestor_dashboard
    with app.app_context():
        turno_mock = MagicMock()
        turno_mock.estado = 'planificado'

        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            s = mock_session.return_value
            s.query.return_value.filter_by.return_value.first.return_value = turno_mock
            s.commit = MagicMock()

            result = gestor_dashboard.editar_turno(
                turno_id=1,
                hora_inicio='10:00',
                hora_fin='18:00',
            )

            assert result['ok'] is True


def test_editar_turno_devuelve_error_si_no_existe(app):
    """editar_turno() devuelve {ok: False} si el turno no existe."""
    from services import gestor_dashboard
    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            mock_session.return_value.query.return_value.filter_by.return_value.first.return_value = None

            result = gestor_dashboard.editar_turno(turno_id=99999, hora_inicio='09:00')

            assert result['ok'] is False
            assert 'error' in result


def test_cancelar_turno_devuelve_ok_si_turno_existe(app):
    """cancelar_turno() devuelve {ok: True} cuando el turno existe."""
    from services import gestor_dashboard
    with app.app_context():
        turno_mock = MagicMock()
        turno_mock.estado = 'planificado'

        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            s = mock_session.return_value
            s.query.return_value.filter_by.return_value.first.return_value = turno_mock
            s.commit = MagicMock()

            result = gestor_dashboard.cancelar_turno(turno_id=1)

            assert result['ok'] is True
            assert turno_mock.estado == 'cancelado'
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_dashboard_sprint6.py -v 2>&1 | head -30
```

- [ ] **Step 3: Implement the 4 methods in gestor_dashboard.py**

Append after `estadisticas()` in the `GestorDashboard` class:

```python
    def turnos_planificacion(
        self,
        desde: str = None,
        hasta: str = None,
        empleado_id: int = None,
        rol: str = None,
        page: int = 1,
        per_page: int = 25,
    ) -> dict:
        """Lista de turnos planificados (pasados y futuros), paginada.

        Args:
            desde:       Fecha ISO YYYY-MM-DD (default: hoy)
            hasta:       Fecha ISO YYYY-MM-DD (default: hoy + 13 días)
            empleado_id: Filtrar por empleado
            rol:         Filtrar por rol (nombre)
            page:        Página (1-based)
            per_page:    Resultados por página

        Returns:
            {turnos: [...], total: N, page: N, pages: N}
        """
        from models import Turno as TurnoModel
        hoy = datetime.utcnow().date()
        fecha_desde = datetime.strptime(desde, '%Y-%m-%d').date() if desde else hoy
        fecha_hasta = datetime.strptime(hasta, '%Y-%m-%d').date() if hasta else hoy + timedelta(days=13)
        page = max(page, 1)

        s = self.session
        query = (
            s.query(TurnoModel)
            .join(Empleado, TurnoModel.empleado_id == Empleado.EmpleadoID)
            .filter(TurnoModel.fecha >= fecha_desde, TurnoModel.fecha <= fecha_hasta)
        )

        if empleado_id:
            query = query.filter(TurnoModel.empleado_id == empleado_id)
        if rol:
            query = query.join(Rol, Empleado.rol_id == Rol.id).filter(Rol.nombre == rol)

        total = query.count()
        pages = max((total + per_page - 1) // per_page, 1)
        turnos = (
            query
            .order_by(TurnoModel.fecha.asc(), TurnoModel.hora_inicio.asc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        resultado = []
        for t in turnos:
            emp = t.empleado
            resultado.append({
                'id':            t.id,
                'empleado_id':   t.empleado_id,
                'empleado':      f'{emp.Nombre} {emp.Apellido}' if emp else f'#{t.empleado_id}',
                'rol':           emp.rol.nombre if emp and emp.rol else None,
                'fecha':         t.fecha.isoformat() if t.fecha else None,
                'hora_inicio':   t.hora_inicio.strftime('%H:%M') if t.hora_inicio else None,
                'hora_fin':      t.hora_fin.strftime('%H:%M') if t.hora_fin else None,
                'tipo':          t.tipo,
                'estado':        t.estado,
                'notas':         t.notas,
            })

        return {'turnos': resultado, 'total': total, 'page': page, 'pages': pages}

    def crear_turno(
        self,
        empleado_id: int,
        fecha: str,
        hora_inicio: str,
        hora_fin: str,
        tipo: str = None,
        notas: str = None,
    ) -> dict:
        """Crea un nuevo turno para un empleado.

        Args:
            empleado_id: ID del empleado
            fecha:       Fecha ISO YYYY-MM-DD
            hora_inicio: Hora HH:MM
            hora_fin:    Hora HH:MM
            tipo:        mañana | tarde | noche | partido (opcional)
            notas:       Texto libre (opcional)

        Returns:
            {ok: True, turno_id: N} o {ok: False, error: str}
        """
        from models import Turno as TurnoModel
        from datetime import time as dtime

        s = self.session
        emp = s.query(Empleado).filter_by(EmpleadoID=empleado_id).first()
        if not emp:
            return {'ok': False, 'error': 'Empleado no encontrado'}

        try:
            fecha_dt = datetime.strptime(fecha, '%Y-%m-%d').date()
            h_ini = dtime(*[int(x) for x in hora_inicio.split(':')])
            h_fin = dtime(*[int(x) for x in hora_fin.split(':')])
        except (ValueError, AttributeError) as exc:
            return {'ok': False, 'error': f'Formato de fecha/hora inválido: {exc}'}

        turno = TurnoModel(
            empleado_id=empleado_id,
            fecha=fecha_dt,
            hora_inicio=h_ini,
            hora_fin=h_fin,
            tipo=tipo or None,
            notas=notas or None,
            estado='planificado',
        )
        try:
            s.add(turno)
            s.flush()
            turno_id = turno.id
            s.commit()
            logger.info('TURNO_CREADO empleado=%s fecha=%s', empleado_id, fecha)
            return {'ok': True, 'turno_id': turno_id}
        except Exception as exc:
            s.rollback()
            logger.error('Error creando turno para empleado %s: %s', empleado_id, exc)
            return {'ok': False, 'error': 'Error al guardar el turno'}

    def editar_turno(
        self,
        turno_id: int,
        hora_inicio: str = None,
        hora_fin: str = None,
        tipo: str = None,
        notas: str = None,
    ) -> dict:
        """Edita hora_inicio, hora_fin, tipo y/o notas de un turno planificado.

        Returns:
            {ok: True} o {ok: False, error: str}
        """
        from models import Turno as TurnoModel
        from datetime import time as dtime

        s = self.session
        turno = s.query(TurnoModel).filter_by(id=turno_id).first()
        if not turno:
            return {'ok': False, 'error': 'Turno no encontrado'}
        if turno.estado == 'cancelado':
            return {'ok': False, 'error': 'No se puede editar un turno cancelado'}

        try:
            if hora_inicio:
                turno.hora_inicio = dtime(*[int(x) for x in hora_inicio.split(':')])
            if hora_fin:
                turno.hora_fin = dtime(*[int(x) for x in hora_fin.split(':')])
            if tipo is not None and tipo != '__no_change__':
                turno.tipo = tipo or None
            if notas is not None and notas != '__no_change__':
                turno.notas = notas or None
            s.commit()
            logger.info('TURNO_EDITADO id=%s', turno_id)
            return {'ok': True}
        except Exception as exc:
            s.rollback()
            logger.error('Error editando turno %s: %s', turno_id, exc)
            return {'ok': False, 'error': 'Error al guardar los cambios'}

    def cancelar_turno(self, turno_id: int) -> dict:
        """Marca un turno como cancelado.

        Returns:
            {ok: True} o {ok: False, error: str}
        """
        from models import Turno as TurnoModel

        s = self.session
        turno = s.query(TurnoModel).filter_by(id=turno_id).first()
        if not turno:
            return {'ok': False, 'error': 'Turno no encontrado'}
        if turno.estado == 'cancelado':
            return {'ok': False, 'error': 'El turno ya está cancelado'}

        try:
            turno.estado = 'cancelado'
            s.commit()
            logger.info('TURNO_CANCELADO id=%s', turno_id)
            return {'ok': True}
        except Exception as exc:
            s.rollback()
            logger.error('Error cancelando turno %s: %s', turno_id, exc)
            return {'ok': False, 'error': 'Error al cancelar el turno'}
```

- [ ] **Step 4: Run tests — expected 6 PASSED**

```bash
pytest tests/test_dashboard_sprint6.py -v 2>&1
```

- [ ] **Step 5: Full suite for regressions**

```bash
pytest -v --tb=short 2>&1 | tail -10
```

---

### Task 2: Blueprint Routes

**Files:**
- Modify: `blueprints/dashboard.py` (insert 4 routes before `# Write endpoints` block)
- Append: `tests/test_dashboard_sprint6.py`

- [ ] **Step 1: Append 5 tests**

```python
# ── Task 2: Routes ────────────────────────────────────────────────────────────

def test_turnos_planificacion_json_devuelve_estructura(client):
    """GET /dashboard/turnos/planificacion devuelve {turnos, total, page, pages}."""
    from unittest.mock import patch
    from services import gestor_dashboard

    fake = {'turnos': [], 'total': 0, 'page': 1, 'pages': 1}

    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    with patch.object(gestor_dashboard, 'turnos_planificacion', return_value=fake):
        resp = client.get('/dashboard/turnos/planificacion')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'turnos' in data
        assert 'total' in data


def test_crear_turno_route_devuelve_ok(client):
    """POST /dashboard/turnos/crear devuelve {ok: True}."""
    from unittest.mock import patch
    from services import gestor_dashboard

    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    with patch.object(gestor_dashboard, 'crear_turno', return_value={'ok': True, 'turno_id': 10}):
        resp = client.post('/dashboard/turnos/crear', json={
            'empleado_id': 1, 'fecha': '2026-04-01',
            'hora_inicio': '09:00', 'hora_fin': '17:00',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True


def test_crear_turno_route_400_si_faltan_campos(client):
    """POST /dashboard/turnos/crear devuelve 400 si faltan campos obligatorios."""
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    resp = client.post('/dashboard/turnos/crear', json={})
    assert resp.status_code == 400


def test_editar_turno_route_devuelve_ok(client):
    """POST /dashboard/turnos/<id>/editar devuelve {ok: True}."""
    from unittest.mock import patch
    from services import gestor_dashboard

    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    with patch.object(gestor_dashboard, 'editar_turno', return_value={'ok': True}):
        resp = client.post('/dashboard/turnos/1/editar', json={'hora_inicio': '10:00'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True


def test_cancelar_turno_route_devuelve_ok(client):
    """POST /dashboard/turnos/<id>/cancelar devuelve {ok: True}."""
    from unittest.mock import patch
    from services import gestor_dashboard

    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    with patch.object(gestor_dashboard, 'cancelar_turno', return_value={'ok': True}):
        resp = client.post('/dashboard/turnos/1/cancelar')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_dashboard_sprint6.py -k "route" -v 2>&1 | tail -15
```

- [ ] **Step 3: Add 4 routes to blueprints/dashboard.py**

Insert before the `# ---------------------------------------------------------------------------\n# Write endpoints` comment:

```python
# ---------------------------------------------------------------------------
# Planificación de turnos (CRUD)
# ---------------------------------------------------------------------------

@blueprint_dashboard.route("/dashboard/turnos/planificacion")
@requiere_rol('manager', 'admin')
def turnos_planificacion():
    try:
        desde       = request.args.get('desde') or None
        hasta       = request.args.get('hasta') or None
        empleado_id = int(request.args.get('empleado_id')) if request.args.get('empleado_id') else None
        rol         = request.args.get('rol') or None
        page        = max(int(request.args.get('page', 1)), 1)
        per_page    = min(int(request.args.get('per_page', 25)), 100)
        return _ok(gestor_dashboard.turnos_planificacion(
            desde=desde, hasta=hasta, empleado_id=empleado_id,
            rol=rol, page=page, per_page=per_page,
        ))
    except Exception as e:
        logger.error("Error en /dashboard/turnos/planificacion: %s", e)
        return _err("Error interno", 500)


@blueprint_dashboard.route("/dashboard/turnos/crear", methods=["POST"])
@requiere_rol('manager', 'admin')
def crear_turno():
    data = request.get_json(silent=True) or {}
    empleado_id = data.get('empleado_id')
    fecha       = data.get('fecha')
    hora_inicio = data.get('hora_inicio')
    hora_fin    = data.get('hora_fin')
    if not all([empleado_id, fecha, hora_inicio, hora_fin]):
        return _err("Faltan campos: empleado_id, fecha, hora_inicio, hora_fin")
    try:
        result = gestor_dashboard.crear_turno(
            empleado_id=int(empleado_id),
            fecha=fecha,
            hora_inicio=hora_inicio,
            hora_fin=hora_fin,
            tipo=data.get('tipo') or None,
            notas=data.get('notas') or None,
        )
        if not result['ok']:
            return _err(result['error'])
        return _ok(result)
    except Exception as e:
        logger.error("Error en /dashboard/turnos/crear: %s", e)
        return _err("Error interno", 500)


@blueprint_dashboard.route("/dashboard/turnos/<int:turno_id>/editar", methods=["POST"])
@requiere_rol('manager', 'admin')
def editar_turno(turno_id):
    data = request.get_json(silent=True) or {}
    try:
        result = gestor_dashboard.editar_turno(
            turno_id=turno_id,
            hora_inicio=data.get('hora_inicio') or None,
            hora_fin=data.get('hora_fin') or None,
            tipo=data.get('tipo', '__no_change__'),
            notas=data.get('notas', '__no_change__'),
        )
        if not result['ok']:
            return _err(result['error'])
        return _ok(result)
    except Exception as e:
        logger.error("Error en /dashboard/turnos/%s/editar: %s", turno_id, e)
        return _err("Error interno", 500)


@blueprint_dashboard.route("/dashboard/turnos/<int:turno_id>/cancelar", methods=["POST"])
@requiere_rol('manager', 'admin')
def cancelar_turno_route(turno_id):
    try:
        result = gestor_dashboard.cancelar_turno(turno_id=turno_id)
        if not result['ok']:
            return _err(result['error'])
        return _ok(result)
    except Exception as e:
        logger.error("Error en /dashboard/turnos/%s/cancelar: %s", turno_id, e)
        return _err("Error interno", 500)
```

**Note:** `tipo` and `notas` use sentinel `'__no_change__'` to distinguish "field not sent" from "send empty string to clear". The Task 1 manager implementation already handles this — no changes needed here.

- [ ] **Step 4: Run all 11 tests — expected: 6 Task1 PASS + 5 Task2 PASS**

```bash
pytest tests/test_dashboard_sprint6.py -v 2>&1
```

- [ ] **Step 5: Full suite**

```bash
pytest -v --tb=short 2>&1 | tail -5
```

---

### Task 3: Template — extend turnos.html

**Files:**
- Modify: `templates/dashboard/turnos.html`
- Append: `tests/test_dashboard_sprint6.py`

- [ ] **Step 1: Append 3 tests**

```python
# ── Task 3: Template ──────────────────────────────────────────────────────────

def test_turnos_template_cargable_jinja2(app):
    """turnos.html se puede cargar en Jinja2 sin errores tras los cambios."""
    with app.app_context():
        template = app.jinja_env.get_template('dashboard/turnos.html')
        assert template is not None


def test_turnos_html_contiene_tab_planificacion(client):
    """GET /dashboard/turnos incluye el tab de Planificación."""
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'
    resp = client.get('/dashboard/turnos')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'Planificación' in html
    assert "tab = 'plan'" in html


def test_turnos_html_contiene_estado_alpine_planificacion(client):
    """GET /dashboard/turnos incluye estado Alpine para planificación."""
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'
    resp = client.get('/dashboard/turnos')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'planTurnos' in html
    assert 'cargarPlan' in html
    assert 'modalAbierto' in html
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_dashboard_sprint6.py -k "template or tab_plan or estado_alpine" -v 2>&1
```

- [ ] **Step 3: Modify templates/dashboard/turnos.html**

The file is 444 lines. Make these three targeted edits:

**Edit 1 — Add 3rd tab button** (after the "Historial" button, before `</div>` on line 85):

Replace the closing `</div>` of the tab bar:
```html
  </div>
```
with:
```html
    <button
      @click="tab = 'plan'; if (!planCargado) cargarPlan()"
      :class="tab === 'plan'
        ? 'border-b-2 border-blue-600 text-blue-700 font-semibold'
        : 'text-slate-500 hover:text-slate-700'"
      class="px-4 py-2.5 text-sm transition -mb-px"
    >
      Planificación
    </button>
  </div>
```

**Edit 2 — Add tab content and modal** (before `</main>`, which closes right before `<script>`):

Insert this block before the closing `</main>` tag:

```html
  <!-- ── TAB PLANIFICACIÓN ─────────────────────────────────────────────────── -->
  <div x-show="tab === 'plan'" x-cloak>

    <!-- Filter bar + New button -->
    <div class="glass-panel rounded-2xl px-5 py-4 mb-5">
      <div class="flex flex-wrap gap-3 items-end justify-between">
        <div class="flex flex-wrap gap-3 items-end">

          <div>
            <label class="block text-xs font-semibold text-slate-500 mb-1">Desde</label>
            <input type="date" x-model="planFiltros.desde"
              @change="planPage = 1; cargarPlan()"
              class="rounded-xl border border-slate-200 bg-white/80 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40" />
          </div>

          <div>
            <label class="block text-xs font-semibold text-slate-500 mb-1">Hasta</label>
            <input type="date" x-model="planFiltros.hasta"
              @change="planPage = 1; cargarPlan()"
              class="rounded-xl border border-slate-200 bg-white/80 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40" />
          </div>

          <div>
            <label class="block text-xs font-semibold text-slate-500 mb-1">Rol</label>
            <select x-model="planFiltros.rol" @change="planPage = 1; cargarPlan()"
              class="rounded-xl border border-slate-200 bg-white/80 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40">
              <option value="">Todos</option>
              <option value="picker">Picker</option>
              <option value="repartidor">Repartidor</option>
              <option value="manager">Manager</option>
            </select>
          </div>

          <button @click="planFiltros = { desde: planFiltros.desde, hasta: planFiltros.hasta, rol: '' }; planPage = 1; cargarPlan()"
            class="px-3 py-2 text-sm text-slate-500 hover:text-slate-700 rounded-xl hover:bg-slate-100 transition">
            Limpiar
          </button>

        </div>

        <button @click="abrirModalCrear()"
          class="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-xl text-sm font-semibold hover:bg-blue-700 transition">
          <span class="text-base leading-none">+</span> Nuevo turno
        </button>
      </div>
    </div>

    <!-- Loading -->
    <div x-show="planCargando" x-cloak>
      {{ loading_skeleton(rows=5, cols=5) }}
    </div>

    <!-- Empty state -->
    <div x-show="!planCargando && planTurnos.length === 0" x-cloak>
      {{ empty_state('📅', 'Sin turnos', 'No hay turnos para este período. Crea uno con el botón +.') }}
    </div>

    <!-- Table -->
    <div x-show="!planCargando && planTurnos.length > 0" x-cloak>
      <div class="glass-panel rounded-2xl overflow-hidden">
        <table class="w-full text-sm">
          <thead class="bg-slate-50/60 border-b border-slate-200">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">Fecha</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">Empleado</th>
              <th class="hidden sm:table-cell px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">Rol</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">Horario</th>
              <th class="hidden md:table-cell px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">Tipo</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">Estado</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-slate-500 uppercase tracking-wide">Acciones</th>
            </tr>
          </thead>
          <tbody>
            <template x-for="t in planTurnos" :key="t.id">
              <tr class="border-b border-slate-100 hover:bg-slate-50/60 transition">
                <td class="px-4 py-3 font-medium text-slate-800" x-text="t.fecha"></td>
                <td class="px-4 py-3 text-slate-700" x-text="t.empleado"></td>
                <td class="hidden sm:table-cell px-4 py-3 text-slate-500 capitalize" x-text="t.rol || '—'"></td>
                <td class="px-4 py-3 font-mono text-slate-700">
                  <span x-text="t.hora_inicio"></span>–<span x-text="t.hora_fin"></span>
                </td>
                <td class="hidden md:table-cell px-4 py-3 capitalize text-slate-500" x-text="t.tipo || '—'"></td>
                <td class="px-4 py-3">
                  <span
                    class="inline-block px-2 py-0.5 rounded-full text-xs font-semibold"
                    :class="{
                      'bg-blue-100 text-blue-700':   t.estado === 'planificado',
                      'bg-emerald-100 text-emerald-700': t.estado === 'completado',
                      'bg-red-100 text-red-600':     t.estado === 'cancelado',
                    }"
                    x-text="t.estado"
                  ></span>
                </td>
                <td class="px-4 py-3 text-right">
                  <template x-if="t.estado !== 'cancelado'">
                    <div class="flex items-center justify-end gap-2">
                      <button @click="abrirModalEditar(t)"
                        class="p-1.5 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition"
                        title="Editar">
                        ✏️
                      </button>
                      <button @click="confirmarCancelar(t.id)"
                        class="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition"
                        title="Cancelar turno">
                        ✕
                      </button>
                    </div>
                  </template>
                  <span x-show="t.estado === 'cancelado'" class="text-xs text-slate-300 italic">—</span>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>

      <!-- Pagination -->
      <div x-show="planPages > 1" class="flex items-center justify-between mt-4 text-sm text-slate-500">
        <span>
          <span x-text="planTotal"></span> turnos
        </span>
        <div class="flex gap-1">
          <button @click="planPage--; cargarPlan()" :disabled="planPage <= 1"
            class="px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition">
            ← Anterior
          </button>
          <span class="px-3 py-1.5 text-slate-600">
            <span x-text="planPage"></span> / <span x-text="planPages"></span>
          </span>
          <button @click="planPage++; cargarPlan()" :disabled="planPage >= planPages"
            class="px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition">
            Siguiente →
          </button>
        </div>
      </div>
    </div>

  </div><!-- end tab plan -->

  <!-- ── MODAL crear / editar turno ───────────────────────────────────────── -->
  <div
    x-show="modalAbierto"
    x-cloak
    class="fixed inset-0 z-50 flex items-center justify-center p-4"
    @keydown.escape.window="cerrarModal()"
  >
    <!-- Backdrop -->
    <div class="absolute inset-0 bg-slate-900/40 backdrop-blur-sm" @click="cerrarModal()"></div>

    <!-- Dialog -->
    <div class="relative glass-panel rounded-2xl px-6 py-6 w-full max-w-md shadow-2xl fade-in">

      <div class="flex items-center justify-between mb-5">
        <h3 class="text-base font-bold text-slate-800"
          x-text="modalModo === 'crear' ? 'Nuevo turno' : 'Editar turno'"></h3>
        <button @click="cerrarModal()" class="text-slate-400 hover:text-slate-600 text-lg leading-none">✕</button>
      </div>

      <!-- Error -->
      <div x-show="formError" class="mb-4 rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700" x-text="formError"></div>

      <form @submit.prevent="guardarTurno()" class="space-y-4">

        <!-- Empleado (solo en crear) -->
        <template x-if="modalModo === 'crear'">
          <div>
            <label class="block text-xs font-semibold text-slate-600 mb-1">Empleado *</label>
            <select x-model="form.empleado_id" required
              class="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40">
              <option value="">Selecciona un empleado</option>
              <template x-for="emp in empleadosDisponibles" :key="emp.id">
                <option :value="emp.id" x-text="emp.nombre + (emp.rol ? ' (' + emp.rol + ')' : '')"></option>
              </template>
            </select>
          </div>
        </template>

        <!-- Empleado (editar — solo lectura) -->
        <template x-if="modalModo === 'editar'">
          <div>
            <label class="block text-xs font-semibold text-slate-600 mb-1">Empleado</label>
            <p class="text-sm text-slate-700 font-medium" x-text="turnoEdicion ? turnoEdicion.empleado : '—'"></p>
          </div>
        </template>

        <!-- Fecha (solo en crear) -->
        <template x-if="modalModo === 'crear'">
          <div>
            <label class="block text-xs font-semibold text-slate-600 mb-1">Fecha *</label>
            <input type="date" x-model="form.fecha" required
              class="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40" />
          </div>
        </template>

        <!-- Fecha (editar — solo lectura) -->
        <template x-if="modalModo === 'editar'">
          <div>
            <label class="block text-xs font-semibold text-slate-600 mb-1">Fecha</label>
            <p class="text-sm text-slate-700" x-text="turnoEdicion ? turnoEdicion.fecha : '—'"></p>
          </div>
        </template>

        <!-- Horario -->
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-xs font-semibold text-slate-600 mb-1">Hora entrada *</label>
            <input type="time" x-model="form.hora_inicio" required
              class="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40" />
          </div>
          <div>
            <label class="block text-xs font-semibold text-slate-600 mb-1">Hora salida *</label>
            <input type="time" x-model="form.hora_fin" required
              class="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40" />
          </div>
        </div>

        <!-- Tipo -->
        <div>
          <label class="block text-xs font-semibold text-slate-600 mb-1">Tipo</label>
          <select x-model="form.tipo"
            class="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40">
            <option value="">Sin tipo</option>
            <option value="mañana">Mañana</option>
            <option value="tarde">Tarde</option>
            <option value="noche">Noche</option>
            <option value="partido">Partido</option>
          </select>
        </div>

        <!-- Notas -->
        <div>
          <label class="block text-xs font-semibold text-slate-600 mb-1">Notas</label>
          <textarea x-model="form.notas" rows="2" placeholder="Opcional"
            class="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40 resize-none"></textarea>
        </div>

        <!-- Buttons -->
        <div class="flex justify-end gap-3 pt-2">
          <button type="button" @click="cerrarModal()"
            class="px-4 py-2 text-sm text-slate-600 hover:text-slate-800 rounded-xl hover:bg-slate-100 transition">
            Cancelar
          </button>
          <button type="submit" :disabled="formGuardando"
            class="px-4 py-2 bg-blue-600 text-white rounded-xl text-sm font-semibold hover:bg-blue-700 disabled:opacity-50 transition">
            <span x-show="!formGuardando">Guardar</span>
            <span x-show="formGuardando">Guardando…</span>
          </button>
        </div>

      </form>
    </div>
  </div>
```

**Edit 3 — Extend the Alpine `turnosApp()` function** (in the `<script>` block):

After the `histFiltros` line in the state object, add new state properties. After the `cargarHistorial()` method, add new methods. After the `formatHora()` method (before the closing `};`), add more methods.

The complete diff to the `<script>` block:

**In the state object** — add after `histFiltros: { desde: '', hasta: '', rol: '' },`:

```javascript
    // ── Planificación ──
    planTurnos: [],
    planTotal: 0,
    planPage: 1,
    planPages: 1,
    planCargando: false,
    planCargado: false,
    planFiltros: { desde: '', hasta: '', rol: '' },

    // ── Modal ──
    modalAbierto: false,
    modalModo: 'crear',
    turnoEdicion: null,
    form: { empleado_id: '', fecha: '', hora_inicio: '', hora_fin: '', tipo: '', notas: '' },
    formError: null,
    formGuardando: false,
    empleadosDisponibles: [],
    empleadosCargados: false,
```

**In `init()`** — add after `this.cargarHoy();`:

```javascript
      const hoy = new Date().toISOString().slice(0, 10);
      const en2semanas = new Date(Date.now() + 13 * 86400000).toISOString().slice(0, 10);
      this.planFiltros.desde = hoy;
      this.planFiltros.hasta = en2semanas;
```

**Add these methods** before the closing `};` of the return object.

First, add a `cargar()` delegator so the shared `error_banner()` macro's "Reintentar" button works regardless of which tab is active:

```javascript
    cargar() {
      if (this.tab === 'hoy')       this.cargarHoy();
      else if (this.tab === 'historial') this.cargarHistorial();
      else if (this.tab === 'plan') this.cargarPlan();
    },
```

Then add the planning and modal methods:

```javascript
    async cargarPlan() {
      this.planCargando = true;
      try {
        const params = new URLSearchParams();
        if (this.planFiltros.desde) params.set('desde', this.planFiltros.desde);
        if (this.planFiltros.hasta) params.set('hasta', this.planFiltros.hasta);
        if (this.planFiltros.rol)   params.set('rol',   this.planFiltros.rol);
        params.set('page',     this.planPage);
        params.set('per_page', 25);

        const resp = await fetch('/dashboard/turnos/planificacion?' + params.toString());
        if (!resp.ok) throw new Error('Error ' + resp.status);
        const data = await resp.json();
        this.planTurnos   = data.turnos;
        this.planTotal    = data.total;
        this.planPage     = data.page;
        this.planPages    = data.pages;
        this.planCargado  = true;
      } catch (e) {
        this.error = 'No se pudo cargar la planificación. ' + e.message;
      } finally {
        this.planCargando = false;
      }
    },

    async _cargarEmpleados() {
      if (this.empleadosCargados) return;
      try {
        const resp = await fetch('/dashboard/empleados');
        if (!resp.ok) throw new Error(resp.status);
        this.empleadosDisponibles = await resp.json();
        this.empleadosCargados = true;
      } catch (e) {
        this.formError = 'No se pudo cargar la lista de empleados.';
      }
    },

    async abrirModalCrear() {
      this.modalModo    = 'crear';
      this.turnoEdicion = null;
      this.formError    = null;
      this.form = {
        empleado_id: '',
        fecha: this.planFiltros.desde || new Date().toISOString().slice(0, 10),
        hora_inicio: '',
        hora_fin: '',
        tipo: '',
        notas: '',
      };
      await this._cargarEmpleados();
      this.modalAbierto = true;
    },

    async abrirModalEditar(turno) {
      this.modalModo    = 'editar';
      this.turnoEdicion = turno;
      this.formError    = null;
      this.form = {
        empleado_id: turno.empleado_id,
        fecha:       turno.fecha,
        hora_inicio: turno.hora_inicio || '',
        hora_fin:    turno.hora_fin    || '',
        tipo:        turno.tipo        || '',
        notas:       turno.notas       || '',
      };
      await this._cargarEmpleados();
      this.modalAbierto = true;
    },

    cerrarModal() {
      this.modalAbierto = false;
      this.formError    = null;
    },

    async guardarTurno() {
      this.formError    = null;
      this.formGuardando = true;
      try {
        let url, body;
        if (this.modalModo === 'crear') {
          url  = '/dashboard/turnos/crear';
          body = {
            empleado_id: parseInt(this.form.empleado_id),
            fecha:       this.form.fecha,
            hora_inicio: this.form.hora_inicio,
            hora_fin:    this.form.hora_fin,
            tipo:        this.form.tipo || null,
            notas:       this.form.notas || null,
          };
        } else {
          url  = `/dashboard/turnos/${this.turnoEdicion.id}/editar`;
          body = {
            hora_inicio: this.form.hora_inicio,
            hora_fin:    this.form.hora_fin,
            tipo:        this.form.tipo,
            notas:       this.form.notas,
          };
        }
        const resp = await fetch(url, {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify(body),
        });
        const data = await resp.json();
        if (!data.ok) { this.formError = data.error || 'Error al guardar.'; return; }
        this.cerrarModal();
        this.cargarPlan();
      } catch (e) {
        this.formError = 'Error de red. Inténtalo de nuevo.';
      } finally {
        this.formGuardando = false;
      }
    },

    async confirmarCancelar(turnoId) {
      if (!confirm('¿Cancelar este turno? Esta acción no se puede deshacer.')) return;
      try {
        const resp = await fetch(`/dashboard/turnos/${turnoId}/cancelar`, { method: 'POST' });
        const data = await resp.json();
        if (!data.ok) { alert(data.error || 'Error al cancelar.'); return; }
        this.cargarPlan();
      } catch (e) {
        alert('Error de red al cancelar el turno.');
      }
    },
```

- [ ] **Step 4: Run all 14 tests — expected: 14 PASSED**

```bash
pytest tests/test_dashboard_sprint6.py -v 2>&1
```

- [ ] **Step 5: Full suite**

```bash
pytest -v --tb=short 2>&1 | tail -5
```
Expected: 14 new passes, same pre-existing failure count.

---

## Reviewer Checklist

**Spec compliance:**
- [ ] 3rd tab "Planificación" visible in turnos.html
- [ ] Tab is lazy-loaded (only fetches when first opened)
- [ ] Filter bar: desde/hasta dates + rol select + limpiar
- [ ] "Nuevo turno" button opens modal
- [ ] Table shows: fecha, empleado, rol, horario (HH:MM–HH:MM), tipo, estado badge, acciones
- [ ] Edit button opens pre-filled modal
- [ ] Cancel button shows `confirm()` dialog → calls `/dashboard/turnos/<id>/cancelar`
- [ ] Cancelled turnos show `—` in acciones column (no edit/cancel buttons)
- [ ] Modal form: empleado dropdown (create only), fecha (create only), hora_inicio, hora_fin, tipo, notas
- [ ] Empleado list fetched lazily from `/dashboard/empleados`
- [ ] `crear_turno()` validates empleado exists, returns `{ok: False, error}` if not
- [ ] `editar_turno()` rejects cancelled turnos
- [ ] `cancelar_turno()` rejects already-cancelled turnos

**Code quality:**
- [ ] `self.session` used throughout (not `db.session`)
- [ ] No f-strings in logger calls
- [ ] `s.rollback()` on exception in crear/editar/cancelar
- [ ] Route function for cancel named `cancelar_turno_route` (not `cancelar_turno`) to avoid name collision with manager method
- [ ] Sentinel `'__no_change__'` handled in `editar_turno` manager for tipo/notas
