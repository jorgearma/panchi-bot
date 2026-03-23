# Sprint 3 — Turnos y Asistencia Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `/dashboard/turnos` — a two-tab view of employee shifts: "Hoy" (live cards with active-time counter) and "Historial" (paginated table of past check-ins with filters).

**Architecture:** Same three-layer pattern as Sprint 2: two new methods on `GestorDashboard`, two JSON routes + one HTML route in `blueprints/dashboard.py`, and a self-contained Jinja2+Alpine.js template. The "Hoy" tab uses polling every 30s to keep operational states and active-time counters fresh without requiring WebSockets.

**Tech Stack:** Flask, SQLAlchemy, Alpine.js 3.x, Tailwind CSS CDN, existing Jinja2 macros from `macros/ui.html`.

---

## Data Model Reference

| Model | Key fields used |
|-------|----------------|
| `Empleado` | `EmpleadoID`, `Nombre`, `Apellido`, `rol_id → Rol.nombre`, `estado_operativo`, `rol_activo`, `activo` |
| `Rol` | `id`, `nombre` |
| `CheckIn` | `id`, `empleado_id`, `fecha`, `inicio`, `fin`, `turno_id`, `minutos_tarde` |
| `TramoTurno` | `check_in_id`, `rol`, `inicio`, `fin` |
| `Turno` | `id`, `empleado_id`, `fecha`, `hora_inicio`, `hora_fin`, `tipo` |

---

## File Map

| Action | File | What changes |
|--------|------|-------------|
| Modify | `managers/gestor_dashboard.py` | Add `turnos_hoy()` + `turnos_historial()` |
| Modify | `blueprints/dashboard.py` | Add 3 routes (1 HTML + 2 JSON) |
| Create | `templates/dashboard/turnos.html` | Full page template |
| Create | `tests/test_dashboard_sprint3.py` | New test file |

---

### Task 1: GestorDashboard — turnos_hoy() + turnos_historial()

**Files:**
- Modify: `managers/gestor_dashboard.py` (append two methods to `GestorDashboard` class)
- Test: `tests/test_dashboard_sprint3.py` (create)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_dashboard_sprint3.py
from unittest.mock import patch, PropertyMock, MagicMock


# ── Task 1: Manager ──────────────────────────────────────────────────────────

def test_turnos_hoy_devuelve_claves_esperadas(app):
    """turnos_hoy() devuelve dict con empleados y resumen."""
    from services import gestor_dashboard
    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            # Empleados query
            mock_session.return_value.query.return_value.filter_by.return_value.order_by.return_value.all.return_value = []
            # CheckIns query
            mock_session.return_value.query.return_value.filter.return_value.all.return_value = []

            result = gestor_dashboard.turnos_hoy()

            assert 'empleados' in result
            assert 'resumen' in result
            assert isinstance(result['empleados'], list)
            assert 'con_checkin' in result['resumen']
            assert 'en_pausa' in result['resumen']
            assert 'desconectados' in result['resumen']
            assert 'total' in result['resumen']


def test_turnos_hoy_resumen_sin_empleados(app):
    """turnos_hoy() con lista vacía de empleados da resumen a cero."""
    from services import gestor_dashboard
    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            mock_session.return_value.query.return_value.filter_by.return_value.order_by.return_value.all.return_value = []
            mock_session.return_value.query.return_value.filter.return_value.all.return_value = []

            result = gestor_dashboard.turnos_hoy()

            assert result['resumen']['total'] == 0
            assert result['resumen']['con_checkin'] == 0


def test_turnos_historial_devuelve_claves_esperadas(app):
    """turnos_historial() devuelve dict con turnos, total, page, pages."""
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

            result = gestor_dashboard.turnos_historial()

            assert 'turnos' in result
            assert 'total' in result
            assert 'page' in result
            assert 'pages' in result
            assert result['turnos'] == []
            assert result['total'] == 0


def test_turnos_historial_paginacion_por_defecto(app):
    """turnos_historial() usa page=1 y per_page=25 por defecto."""
    from services import gestor_dashboard
    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            mock_q = mock_session.return_value.query.return_value
            mock_q.join.return_value = mock_q
            mock_q.filter.return_value = mock_q
            mock_q.order_by.return_value = mock_q
            mock_q.count.return_value = 50
            mock_q.offset.return_value = mock_q
            mock_q.limit.return_value = mock_q
            mock_q.all.return_value = []

            result = gestor_dashboard.turnos_historial()

            assert result['page'] == 1
            assert result['pages'] == 2   # ceil(50/25)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
venv/bin/pytest tests/test_dashboard_sprint3.py -v
```
Expected: 4 failures — methods not defined yet.

- [ ] **Step 3: Implement turnos_hoy() in GestorDashboard**

Append after `detalle_pedido` (end of `GestorDashboard` class) in `managers/gestor_dashboard.py`:

```python
    def turnos_hoy(self) -> dict:
        """Estado de asistencia del día actual.

        Devuelve todos los empleados activos con su check-in de hoy (si lo hay),
        el tiempo acumulado, y el estado operativo actual.

        Returns:
            {
                empleados: [{
                    id, nombre, rol, rol_activo, estado_operativo,
                    check_in_inicio, check_in_fin, minutos_activo,
                    activo (bool: check-in abierto ahora mismo),
                    minutos_tarde,
                }],
                resumen: { con_checkin, en_pausa, desconectados, total }
            }
        """
        from models import CheckIn

        hoy = datetime.utcnow().date()
        ahora = datetime.utcnow()
        s = self.session

        empleados = (
            s.query(Empleado)
            .filter_by(activo=True)
            .order_by(Empleado.Nombre)
            .all()
        )

        # Build a dict empleado_id → checkin (most recent of the day)
        checkins_hoy = {}
        for ci in s.query(CheckIn).filter(CheckIn.fecha == hoy).all():
            # Keep the open one if exists, otherwise the most recent
            prev = checkins_hoy.get(ci.empleado_id)
            if prev is None or (ci.fin is None and prev.fin is not None):
                checkins_hoy[ci.empleado_id] = ci
            elif ci.fin is None and prev.fin is None:
                # Two open check-ins (shouldn't happen) — keep later one
                if ci.inicio > prev.inicio:
                    checkins_hoy[ci.empleado_id] = ci
            elif prev.fin is not None and ci.fin is not None and ci.inicio > prev.inicio:
                checkins_hoy[ci.empleado_id] = ci

        resultado = []
        for emp in empleados:
            ci = checkins_hoy.get(emp.EmpleadoID)
            minutos_activo = None
            if ci:
                fin_efectivo = ci.fin or ahora
                minutos_activo = int((fin_efectivo - ci.inicio).total_seconds() / 60)

            resultado.append({
                'id':                emp.EmpleadoID,
                'nombre':            f'{emp.Nombre} {emp.Apellido}',
                'rol':               emp.rol.nombre if emp.rol else None,
                'rol_activo':        emp.rol_activo,
                'estado_operativo':  emp.estado_operativo,
                'check_in_inicio':   _iso(ci.inicio) if ci else None,
                'check_in_fin':      _iso(ci.fin) if ci else None,
                'minutos_activo':    minutos_activo,
                'activo':            ci is not None and ci.fin is None,
                'minutos_tarde':     ci.minutos_tarde if ci else None,
            })

        n_con_checkin   = sum(1 for e in resultado if e['activo'])
        n_pausa         = sum(1 for e in resultado if e['estado_operativo'] == 'en_pausa')
        n_desconectados = sum(1 for e in resultado if e['estado_operativo'] == 'desconectado')

        return {
            'empleados': resultado,
            'resumen': {
                'con_checkin':   n_con_checkin,
                'en_pausa':      n_pausa,
                'desconectados': n_desconectados,
                'total':         len(resultado),
            },
        }
```

- [ ] **Step 4: Implement turnos_historial() in GestorDashboard**

Append immediately after `turnos_hoy`:

```python
    def turnos_historial(
        self,
        desde: str = None,
        hasta: str = None,
        empleado_id: int = None,
        rol: str = None,
        page: int = 1,
        per_page: int = 25,
    ) -> dict:
        """Historial paginado de check-ins con filtros.

        Args:
            desde:       fecha ISO 'YYYY-MM-DD' (inclusive)
            hasta:       fecha ISO 'YYYY-MM-DD' (inclusive)
            empleado_id: filtrar por empleado concreto
            rol:         filtrar por nombre de rol (Rol.nombre)
            page:        página 1-based
            per_page:    resultados por página (máx 100)

        Returns:
            { turnos: list[dict], total: int, page: int, pages: int }
        """
        from math import ceil
        from models import CheckIn, Rol as RolModel

        per_page = min(per_page, 100)
        s = self.session

        query = (
            s.query(CheckIn)
            .join(Empleado, CheckIn.empleado_id == Empleado.EmpleadoID)
        )

        if desde:
            try:
                query = query.filter(CheckIn.fecha >= datetime.strptime(desde, '%Y-%m-%d').date())
            except ValueError:
                pass

        if hasta:
            try:
                query = query.filter(CheckIn.fecha <= datetime.strptime(hasta, '%Y-%m-%d').date())
            except ValueError:
                pass

        if empleado_id:
            query = query.filter(CheckIn.empleado_id == empleado_id)

        if rol:
            query = (
                query
                .join(RolModel, Empleado.rol_id == RolModel.id)
                .filter(RolModel.nombre == rol)
            )

        total = query.count()
        pages = ceil(total / per_page) if total else 1

        checkins = (
            query
            .order_by(CheckIn.fecha.desc(), CheckIn.inicio.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        resultado = []
        for ci in checkins:
            emp = ci.empleado
            horas_trabajadas = None
            if ci.inicio and ci.fin:
                horas_trabajadas = round((ci.fin - ci.inicio).total_seconds() / 3600, 1)

            resultado.append({
                'check_in_id':      ci.id,
                'empleado_id':      emp.EmpleadoID,
                'empleado_nombre':  f'{emp.Nombre} {emp.Apellido}',
                'rol':              emp.rol.nombre if emp.rol else None,
                'fecha':            ci.fecha.isoformat() if ci.fecha else None,
                'inicio':           _iso(ci.inicio),
                'fin':              _iso(ci.fin),
                'horas_trabajadas': horas_trabajadas,
                'minutos_tarde':    ci.minutos_tarde,
                'activo':           ci.fin is None,
            })

        return {'turnos': resultado, 'total': total, 'page': page, 'pages': pages}
```

- [ ] **Step 5: Run Task 1 tests**

```bash
venv/bin/pytest tests/test_dashboard_sprint3.py -v
```
Expected: 4 PASSED.

- [ ] **Step 6: Run full suite**

```bash
venv/bin/pytest -q --tb=short
```
Expected: no new failures beyond pre-existing `test_con_sesion_picker_ok`.

- [ ] **Step 7: Commit**

```bash
git add managers/gestor_dashboard.py tests/test_dashboard_sprint3.py
git commit -m "feat: add turnos_hoy() and turnos_historial() to GestorDashboard"
```

---

### Task 2: Flask Routes — /dashboard/turnos + JSON endpoints

**Files:**
- Modify: `blueprints/dashboard.py`
- Test: `tests/test_dashboard_sprint3.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_dashboard_sprint3.py`:

```python
# ── Task 2: Routes ───────────────────────────────────────────────────────────

def test_turnos_html_devuelve_200(client):
    """GET /dashboard/turnos devuelve 200 para admin autenticado."""
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'
    resp = client.get('/dashboard/turnos')
    assert resp.status_code == 200
    assert b'turno' in resp.data.lower()


def test_turnos_html_requiere_auth(client):
    """GET /dashboard/turnos redirige sin sesión."""
    resp = client.get('/dashboard/turnos')
    assert resp.status_code in (302, 401)


def test_turnos_hoy_json_devuelve_estructura(client):
    """GET /dashboard/turnos/hoy devuelve {empleados, resumen}."""
    from unittest.mock import patch
    from services import gestor_dashboard

    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    with patch.object(
        gestor_dashboard, 'turnos_hoy',
        return_value={'empleados': [], 'resumen': {'con_checkin': 0, 'en_pausa': 0, 'desconectados': 0, 'total': 0}}
    ):
        resp = client.get('/dashboard/turnos/hoy')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'empleados' in data
        assert 'resumen' in data


def test_turnos_historial_json_devuelve_estructura(client):
    """GET /dashboard/turnos/historial devuelve {turnos, total, page, pages}."""
    from unittest.mock import patch
    from services import gestor_dashboard

    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    with patch.object(
        gestor_dashboard, 'turnos_historial',
        return_value={'turnos': [], 'total': 0, 'page': 1, 'pages': 1}
    ):
        resp = client.get('/dashboard/turnos/historial')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'turnos' in data
        assert 'total' in data


def test_turnos_historial_json_pasa_filtros(client):
    """GET /dashboard/turnos/historial pasa params al manager."""
    from unittest.mock import patch
    from services import gestor_dashboard

    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    with patch.object(
        gestor_dashboard, 'turnos_historial',
        return_value={'turnos': [], 'total': 0, 'page': 1, 'pages': 1}
    ) as mock_hist:
        client.get('/dashboard/turnos/historial?rol=picker&page=2')
        mock_hist.assert_called_once_with(
            desde=None, hasta=None, empleado_id=None,
            rol='picker', page=2, per_page=25
        )
```

- [ ] **Step 2: Run new tests to verify they fail**

```bash
venv/bin/pytest tests/test_dashboard_sprint3.py::test_turnos_hoy_json_devuelve_estructura tests/test_dashboard_sprint3.py::test_turnos_historial_json_devuelve_estructura -v
```
Expected: fail — routes not registered.

- [ ] **Step 3: Add routes to blueprints/dashboard.py**

Append after the `detalle_pedido` route (end of Read endpoints, before Write endpoints comment):

```python
@blueprint_dashboard.route("/dashboard/turnos")
@requiere_rol('manager', 'admin')
def turnos():
    return render_template("dashboard/turnos.html")


@blueprint_dashboard.route("/dashboard/turnos/hoy")
@requiere_rol('manager', 'admin')
def turnos_hoy():
    try:
        return _ok(gestor_dashboard.turnos_hoy())
    except Exception as e:
        logger.error("Error en /dashboard/turnos/hoy: %s", e)
        return _err("Error interno", 500)


@blueprint_dashboard.route("/dashboard/turnos/historial")
@requiere_rol('manager', 'admin')
def turnos_historial():
    try:
        desde       = request.args.get("desde")
        hasta       = request.args.get("hasta")
        empleado_id = request.args.get("empleado_id", type=int)
        rol         = request.args.get("rol")
        page        = max(int(request.args.get("page", 1)), 1)
        per_page    = int(request.args.get("per_page", 25))
        return _ok(gestor_dashboard.turnos_historial(
            desde=desde, hasta=hasta, empleado_id=empleado_id,
            rol=rol, page=page, per_page=per_page,
        ))
    except Exception as e:
        logger.error("Error en /dashboard/turnos/historial: %s", e)
        return _err("Error interno", 500)
```

- [ ] **Step 4: Run all Task 2 tests (skip html template test)**

```bash
venv/bin/pytest tests/test_dashboard_sprint3.py -v -k "not test_turnos_html_devuelve_200"
```
Expected: 8 pass. `test_turnos_html_devuelve_200` allowed to fail (template pending).

- [ ] **Step 5: Run full suite**

```bash
venv/bin/pytest -q --tb=short
```

- [ ] **Step 6: Commit**

```bash
git add blueprints/dashboard.py tests/test_dashboard_sprint3.py
git commit -m "feat: add /dashboard/turnos routes and JSON API endpoints"
```

---

### Task 3: Template — templates/dashboard/turnos.html

**Files:**
- Create: `templates/dashboard/turnos.html`
- Test: append to `tests/test_dashboard_sprint3.py`

#### Design of the "Hoy" tab

```
┌─────────────────────────────────────────────────────┐
│  ● 3 activos   ⏸ 1 en pausa   ○ 2 desconectados    │  ← summary bar
├─────────────────────────────────────────────────────┤
│  ┌───────────┐  ┌───────────┐  ┌───────────┐        │
│  │ M.García  │  │ J.López   │  │ A.Pérez   │        │
│  │ Picker    │  │ Repart.   │  │ Manager   │        │
│  │ ● disponible│ │ ● disponible│ │ ○ desc.  │        │
│  │ 2h 14m    │  │ 1h 03m    │  │ —         │        │
│  │ 08:02     │  │ 09:15     │  │ Sin turno │        │
│  └───────────┘  └───────────┘  └───────────┘        │
└─────────────────────────────────────────────────────┘
```

The active-time counter uses `setInterval` in Alpine.js, incrementing a local counter each second for employees with an open check-in. The polling endpoint (`/dashboard/turnos/hoy`) refreshes every 30s to update operational states and pick up new check-ins.

- [ ] **Step 1: Verify test_turnos_html_devuelve_200 fails**

```bash
venv/bin/pytest tests/test_dashboard_sprint3.py::test_turnos_html_devuelve_200 -v
```
Expected: FAIL (template not found).

- [ ] **Step 2: Create the template**

Create `templates/dashboard/turnos.html`:

```html
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Turnos y Asistencia — Panchi Ops</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@500;600;700;800&display=swap" rel="stylesheet">
  <style>
    [x-cloak] { display: none !important; }
    :root {
      --bg: #edf2f7;
      --panel: rgba(255, 255, 255, 0.86);
      --panel-strong: #ffffff;
      --line: rgba(148, 163, 184, 0.22);
      --ink: #0f172a;
      --muted: #64748b;
      --brand: #0f4c81;
      --brand-soft: #dbeafe;
    }
    body {
      font-family: "Manrope", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(14, 116, 144, 0.10), transparent 28%),
        radial-gradient(circle at top right, rgba(59, 130, 246, 0.08), transparent 24%),
        linear-gradient(180deg, #f8fafc 0%, var(--bg) 100%);
      color: var(--ink);
    }
    .glass-panel {
      background: var(--panel);
      backdrop-filter: blur(16px);
      border: 1px solid var(--line);
      box-shadow: 0 18px 40px rgba(15, 23, 42, 0.08);
    }
    .fade-in { animation: fadeIn .25s ease-in; }
    @keyframes fadeIn { from{opacity:0;transform:translateY(-4px)} to{opacity:1;transform:translateY(0)} }
  </style>
</head>
<body class="min-h-screen">

{% from 'macros/ui.html' import status_badge, empty_state, loading_skeleton, error_banner %}

<!-- ── HEADER ─────────────────────────────────────────────────────────────── -->
<header class="sticky top-0 z-30 px-4 pt-4 pb-2">
  <div class="mx-auto max-w-7xl glass-panel rounded-2xl px-5 py-3 flex items-center justify-between gap-4">
    <div class="flex items-center gap-3">
      <span class="text-xl">🍕</span>
      <span class="font-extrabold text-lg tracking-tight" style="color:var(--brand)">Panchi Ops</span>
      <span class="hidden sm:inline text-slate-300">|</span>
      <span class="hidden sm:inline text-sm font-semibold text-slate-500">Turnos y Asistencia</span>
    </div>
    {% include 'dashboard/_nav.html' %}
  </div>
</header>

<!-- ── MAIN ───────────────────────────────────────────────────────────────── -->
<main
  class="mx-auto max-w-7xl px-4 py-6"
  x-data="turnosApp()"
>

  <!-- ── TABS ──────────────────────────────────────────────────────────────── -->
  <div class="flex items-center gap-1 mb-5 border-b border-slate-200">
    <button
      @click="tab = 'hoy'"
      :class="tab === 'hoy'
        ? 'border-b-2 border-blue-600 text-blue-700 font-semibold'
        : 'text-slate-500 hover:text-slate-700'"
      class="px-4 py-2.5 text-sm transition -mb-px"
    >
      Hoy
    </button>
    <button
      @click="tab = 'historial'; if (!historialCargado) cargarHistorial()"
      :class="tab === 'historial'
        ? 'border-b-2 border-blue-600 text-blue-700 font-semibold'
        : 'text-slate-500 hover:text-slate-700'"
      class="px-4 py-2.5 text-sm transition -mb-px"
    >
      Historial
    </button>
  </div>

  <!-- ── TAB HOY ────────────────────────────────────────────────────────────── -->
  <div x-show="tab === 'hoy'">

    <!-- Error banner -->
    {{ error_banner() }}

    <!-- Summary bar -->
    <div class="glass-panel rounded-2xl px-5 py-3 mb-5 flex flex-wrap gap-5 items-center" x-show="!cargandoHoy && resumen">
      <div class="flex items-center gap-2">
        <span class="w-2.5 h-2.5 rounded-full bg-emerald-500 inline-block"></span>
        <span class="text-sm font-semibold text-slate-700">
          <span x-text="resumen ? resumen.con_checkin : 0"></span> activos
        </span>
      </div>
      <div class="flex items-center gap-2">
        <span class="w-2.5 h-2.5 rounded-full bg-yellow-400 inline-block"></span>
        <span class="text-sm font-semibold text-slate-700">
          <span x-text="resumen ? resumen.en_pausa : 0"></span> en pausa
        </span>
      </div>
      <div class="flex items-center gap-2">
        <span class="w-2.5 h-2.5 rounded-full bg-slate-300 inline-block"></span>
        <span class="text-sm font-semibold text-slate-700">
          <span x-text="resumen ? resumen.desconectados : 0"></span> desconectados
        </span>
      </div>
      <div class="ml-auto text-xs text-slate-400">
        Actualiza en <span x-text="segundosParaActualizar"></span>s
      </div>
    </div>

    <!-- Loading skeleton -->
    <div x-show="cargandoHoy" x-cloak>
      {{ loading_skeleton(rows=6, cols=4) }}
    </div>

    <!-- Empty state -->
    <div x-show="!cargandoHoy && empleados.length === 0" x-cloak>
      {{ empty_state('👥', 'Sin empleados activos', 'No hay empleados registrados en el sistema.') }}
    </div>

    <!-- Employee cards grid -->
    <div
      x-show="!cargandoHoy && empleados.length > 0"
      x-cloak
      class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4"
    >
      <template x-for="emp in empleados" :key="emp.id">
        <div class="glass-panel rounded-2xl px-4 py-4 flex flex-col gap-3 fade-in">

          <!-- Avatar + nombre -->
          <div class="flex items-center gap-3">
            <div
              class="w-10 h-10 rounded-full flex items-center justify-center text-base font-bold flex-shrink-0"
              :class="emp.activo ? 'bg-blue-100 text-blue-700' : 'bg-slate-100 text-slate-400'"
              x-text="emp.nombre.charAt(0).toUpperCase()"
            ></div>
            <div class="min-w-0">
              <p class="font-bold text-slate-800 text-sm truncate" x-text="emp.nombre"></p>
              <p class="text-xs text-slate-400 truncate" x-text="emp.rol || '—'"></p>
            </div>
          </div>

          <!-- Estado operativo badge -->
          <div class="flex items-center gap-2">
            <span
              class="w-2 h-2 rounded-full flex-shrink-0"
              :class="{
                'bg-emerald-500': emp.estado_operativo === 'disponible',
                'bg-blue-500':    emp.estado_operativo === 'ocupado',
                'bg-yellow-400':  emp.estado_operativo === 'en_pausa',
                'bg-slate-300':   emp.estado_operativo === 'desconectado',
              }"
            ></span>
            <span
              class="text-xs font-semibold capitalize"
              :class="{
                'text-emerald-700': emp.estado_operativo === 'disponible',
                'text-blue-700':    emp.estado_operativo === 'ocupado',
                'text-yellow-700':  emp.estado_operativo === 'en_pausa',
                'text-slate-400':   emp.estado_operativo === 'desconectado',
              }"
              x-text="emp.estado_operativo.replace('_', ' ')"
            ></span>
            <span x-show="emp.rol_activo" class="ml-auto text-xs bg-slate-100 text-slate-500 rounded px-1.5 py-0.5 font-medium" x-text="emp.rol_activo"></span>
          </div>

          <!-- Tiempo activo -->
          <div class="rounded-xl bg-slate-50 px-3 py-2">
            <template x-if="emp.activo">
              <div class="flex items-center justify-between">
                <span class="text-xs text-slate-400">Tiempo activo</span>
                <span
                  class="text-sm font-bold text-slate-800 font-mono"
                  x-text="formatMinutos(emp.minutos_activo + ticksSinceLoad)"
                ></span>
              </div>
            </template>
            <template x-if="!emp.activo && emp.check_in_inicio">
              <div class="flex items-center justify-between">
                <span class="text-xs text-slate-400">Trabajó</span>
                <span class="text-sm font-semibold text-slate-600" x-text="formatMinutos(emp.minutos_activo)"></span>
              </div>
            </template>
            <template x-if="!emp.activo && !emp.check_in_inicio">
              <p class="text-xs text-slate-400 italic">Sin turno hoy</p>
            </template>
          </div>

          <!-- Hora check-in -->
          <div x-show="emp.check_in_inicio" class="text-xs text-slate-400">
            Entrada: <span class="font-semibold text-slate-600" x-text="formatHora(emp.check_in_inicio)"></span>
            <template x-if="emp.minutos_tarde && emp.minutos_tarde > 0">
              <span class="ml-1 text-amber-600 font-semibold" x-text="'+' + emp.minutos_tarde + 'min'"></span>
            </template>
          </div>

        </div>
      </template>
    </div>

  </div><!-- /tab hoy -->

  <!-- ── TAB HISTORIAL ──────────────────────────────────────────────────────── -->
  <div x-show="tab === 'historial'" x-cloak>

    <!-- Filter bar -->
    <div class="glass-panel rounded-2xl px-5 py-4 mb-5">
      <div class="flex flex-wrap gap-3 items-end">

        <!-- Fecha desde -->
        <div>
          <label class="block text-xs font-semibold text-slate-500 mb-1">Desde</label>
          <input
            type="date"
            x-model="histFiltros.desde"
            @change="histPagina = 1; cargarHistorial()"
            class="rounded-xl border border-slate-200 bg-white/80 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40"
          />
        </div>

        <!-- Fecha hasta -->
        <div>
          <label class="block text-xs font-semibold text-slate-500 mb-1">Hasta</label>
          <input
            type="date"
            x-model="histFiltros.hasta"
            @change="histPagina = 1; cargarHistorial()"
            class="rounded-xl border border-slate-200 bg-white/80 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40"
          />
        </div>

        <!-- Rol -->
        <div>
          <label class="block text-xs font-semibold text-slate-500 mb-1">Rol</label>
          <select
            x-model="histFiltros.rol"
            @change="histPagina = 1; cargarHistorial()"
            class="rounded-xl border border-slate-200 bg-white/80 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40"
          >
            <option value="">Todos</option>
            <option value="picker">Picker</option>
            <option value="repartidor">Repartidor</option>
            <option value="manager">Manager</option>
            <option value="admin">Admin</option>
          </select>
        </div>

        <!-- Limpiar -->
        <button
          @click="histFiltros = {desde:'',hasta:'',rol:''}; histPagina=1; cargarHistorial()"
          class="rounded-xl border border-slate-200 bg-white/80 px-3 py-2 text-sm font-semibold text-slate-500 hover:bg-slate-100 transition"
        >
          Limpiar
        </button>

      </div>
      <div class="mt-3 text-xs text-slate-500 font-medium" x-show="!cargandoHistorial">
        <span x-text="histTotal"></span> registros encontrados
      </div>
    </div>

    <!-- Loading skeleton -->
    <div x-show="cargandoHistorial" x-cloak>
      {{ loading_skeleton(rows=8, cols=5) }}
    </div>

    <!-- Empty state -->
    <div x-show="!cargandoHistorial && turnos.length === 0" x-cloak>
      {{ empty_state('📅', 'Sin registros', 'No hay turnos para el período seleccionado.') }}
    </div>

    <!-- Table -->
    <div x-show="!cargandoHistorial && turnos.length > 0" x-cloak>
      <div class="glass-panel rounded-2xl overflow-hidden">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-slate-100 bg-slate-50/60">
              <th class="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wide">Empleado</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wide">Rol</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wide">Fecha</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wide">Entrada</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wide">Salida</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-slate-400 uppercase tracking-wide">Horas</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-slate-400 uppercase tracking-wide">Tarde</th>
            </tr>
          </thead>
          <tbody>
            <template x-for="t in turnos" :key="t.check_in_id">
              <tr class="border-b border-slate-100 hover:bg-slate-50/50 transition-colors fade-in">
                <td class="px-4 py-3 font-semibold text-slate-800" x-text="t.empleado_nombre"></td>
                <td class="px-4 py-3 text-slate-500 capitalize" x-text="t.rol || '—'"></td>
                <td class="px-4 py-3 text-slate-600 text-xs font-mono" x-text="t.fecha"></td>
                <td class="px-4 py-3 text-slate-600 text-xs font-mono" x-text="formatHora(t.inicio)"></td>
                <td class="px-4 py-3 text-xs">
                  <template x-if="t.activo">
                    <span class="inline-flex items-center gap-1 text-emerald-600 font-semibold">
                      <span class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse inline-block"></span>
                      Activo
                    </span>
                  </template>
                  <template x-if="!t.activo">
                    <span class="text-slate-600 font-mono" x-text="formatHora(t.fin)"></span>
                  </template>
                </td>
                <td class="px-4 py-3 text-right font-semibold text-slate-700"
                    x-text="t.horas_trabajadas !== null ? t.horas_trabajadas + 'h' : '—'"></td>
                <td class="px-4 py-3 text-right text-xs"
                    :class="t.minutos_tarde > 0 ? 'text-amber-600 font-semibold' : 'text-slate-400'"
                    x-text="t.minutos_tarde > 0 ? '+' + t.minutos_tarde + 'min' : '—'"></td>
              </tr>
            </template>
          </tbody>
        </table>

        <!-- Pagination -->
        <div class="flex items-center justify-between px-4 py-3 border-t border-slate-100" x-show="histPages > 1">
          <button
            @click="histPagina = histPagina - 1; cargarHistorial()"
            :disabled="histPagina <= 1"
            class="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-semibold text-slate-600 disabled:opacity-40 hover:bg-slate-50 transition"
          >
            ← Anterior
          </button>
          <span class="text-sm text-slate-500">
            Página <span class="font-semibold text-slate-800" x-text="histPagina"></span>
            de <span x-text="histPages"></span>
          </span>
          <button
            @click="histPagina = histPagina + 1; cargarHistorial()"
            :disabled="histPagina >= histPages"
            class="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-semibold text-slate-600 disabled:opacity-40 hover:bg-slate-50 transition"
          >
            Siguiente →
          </button>
        </div>
      </div>
    </div>

  </div><!-- /tab historial -->

</main>

<script>
function turnosApp() {
  return {
    tab: 'hoy',

    // ── Hoy ──
    empleados: [],
    resumen: null,
    cargandoHoy: false,
    error: null,
    segundosParaActualizar: 30,
    ticksSinceLoad: 0,   // seconds elapsed since last load (for live counter)
    _pollTimer: null,
    _tickTimer: null,

    // ── Historial ──
    turnos: [],
    histTotal: 0,
    histPagina: 1,
    histPages: 1,
    cargandoHistorial: false,
    historialCargado: false,
    histFiltros: { desde: '', hasta: '', rol: '' },

    init() {
      this.cargarHoy();
      this._pollTimer = setInterval(() => {
        this.segundosParaActualizar--;
        if (this.segundosParaActualizar <= 0) {
          this.cargarHoy();
        }
      }, 1000);
      this._tickTimer = setInterval(() => {
        this.ticksSinceLoad++;
      }, 60000);  // increment by 1 minute every minute
    },

    async cargarHoy() {
      this.cargandoHoy = true;
      this.error = null;
      try {
        const resp = await fetch('/dashboard/turnos/hoy');
        if (!resp.ok) throw new Error('Error ' + resp.status);
        const data = await resp.json();
        this.empleados = data.empleados;
        this.resumen   = data.resumen;
        this.ticksSinceLoad = 0;
        this.segundosParaActualizar = 30;
      } catch (e) {
        this.error = 'No se pudo cargar los turnos de hoy. ' + e.message;
      } finally {
        this.cargandoHoy = false;
      }
    },

    async cargarHistorial() {
      this.cargandoHistorial = true;
      try {
        const params = new URLSearchParams();
        if (this.histFiltros.desde) params.set('desde',    this.histFiltros.desde);
        if (this.histFiltros.hasta) params.set('hasta',    this.histFiltros.hasta);
        if (this.histFiltros.rol)   params.set('rol',      this.histFiltros.rol);
        params.set('page',     this.histPagina);
        params.set('per_page', 25);

        const resp = await fetch('/dashboard/turnos/historial?' + params.toString());
        if (!resp.ok) throw new Error('Error ' + resp.status);
        const data = await resp.json();
        this.turnos         = data.turnos;
        this.histTotal      = data.total;
        this.histPagina     = data.page;
        this.histPages      = data.pages;
        this.historialCargado = true;
      } catch (e) {
        this.error = 'No se pudo cargar el historial. ' + e.message;
      } finally {
        this.cargandoHistorial = false;
      }
    },

    formatMinutos(min) {
      if (min === null || min === undefined) return '—';
      const h = Math.floor(min / 60);
      const m = min % 60;
      if (h > 0) return `${h}h ${String(m).padStart(2,'0')}min`;
      return `${m}min`;
    },

    formatHora(iso) {
      if (!iso) return '—';
      const d = new Date(iso);
      return d.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
    },
  };
}
</script>

</body>
</html>
```

- [ ] **Step 3: Run test_turnos_html_devuelve_200**

```bash
venv/bin/pytest tests/test_dashboard_sprint3.py::test_turnos_html_devuelve_200 -v
```
Expected: PASS.

- [ ] **Step 4: Append 3 template tests**

Append to `tests/test_dashboard_sprint3.py`:

```python
# ── Task 3: Template ─────────────────────────────────────────────────────────

def test_turnos_template_cargable_en_jinja2(app):
    """turnos.html se puede cargar en Jinja2 sin errores de sintaxis."""
    with app.app_context():
        template = app.jinja_env.get_template('dashboard/turnos.html')
        assert template is not None


def test_turnos_html_contiene_nav_links(client):
    """GET /dashboard/turnos incluye los links de navegación."""
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'
    resp = client.get('/dashboard/turnos')
    assert resp.status_code == 200
    html = resp.data.decode()
    for ruta in ['/dashboard', '/dashboard/monitor', '/dashboard/historial',
                 '/dashboard/rendimiento', '/dashboard/estadisticas']:
        assert ruta in html, f"Link {ruta} no encontrado en turnos.html"


def test_turnos_html_contiene_alpine_app(client):
    """GET /dashboard/turnos incluye x-data turnosApp()."""
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'
    resp = client.get('/dashboard/turnos')
    assert resp.status_code == 200
    assert b'turnosApp' in resp.data
```

- [ ] **Step 5: Run all Sprint 3 tests**

```bash
venv/bin/pytest tests/test_dashboard_sprint3.py -v
```
Expected: all 12 tests PASS.

- [ ] **Step 6: Run full suite**

```bash
venv/bin/pytest -q --tb=short
```
No new regressions.

- [ ] **Step 7: Commit**

```bash
git add templates/dashboard/turnos.html tests/test_dashboard_sprint3.py
git commit -m "feat: add /dashboard/turnos page with Hoy cards and Historial table"
```

---

## Summary

After all 3 tasks:

| Endpoint | Type | Auth |
|----------|------|------|
| `GET /dashboard/turnos` | HTML | manager/admin |
| `GET /dashboard/turnos/hoy` | JSON | manager/admin |
| `GET /dashboard/turnos/historial` | JSON | manager/admin |

New methods on `GestorDashboard`: `turnos_hoy()`, `turnos_historial()`

New template: `templates/dashboard/turnos.html` — two-tab design (Hoy / Historial), live polling every 30s for the Hoy tab

New tests: 12 in `tests/test_dashboard_sprint3.py`

**Note:** The live active-time counter in employee cards increments per minute locally (`ticksSinceLoad`) and resets on each poll. The polling every 30s refreshes operational states and picks up new check-ins. This avoids WebSockets while keeping the view reasonably fresh.
