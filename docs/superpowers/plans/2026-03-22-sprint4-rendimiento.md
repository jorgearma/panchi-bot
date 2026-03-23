# Sprint 4 — Rendimiento por Empleado Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `/dashboard/rendimiento` — a two-view performance page: a ranking table of all employees with period selector, and an individual detail view with KPIs + Chart.js bar chart.

**Architecture:** Same three-layer pattern. Two new `GestorDashboard` methods aggregate `MetricaDiariaEmpleado` (a pre-computed daily cache table). The template uses two Alpine.js "views" — list and individual — toggled client-side. Chart.js renders the bar chart in the individual view.

**Tech Stack:** Flask, SQLAlchemy (aggregation with `func.sum`/`func.avg`), Alpine.js 3.x, Tailwind CSS CDN, Chart.js CDN (new), existing macros.

---

## Data Model Reference

| Model | Key fields |
|-------|-----------|
| `MetricaDiariaEmpleado` | `empleado_id`, `fecha (Date)`, `rol`, `pedidos_completados`, `tiempo_medio_operacion_min`, `incidencias` |
| `Empleado` | `EmpleadoID`, `Nombre`, `Apellido`, `rol_id → Rol.nombre` |
| `PickingPedido` | `empleado_id`, `estado`, `completado_en`, `pedido_id` |
| `Reparto` | `repartidor_id`, `estado`, `hora_entrega_real`, `pedido_id` |
| `CheckIn` | `empleado_id`, `fecha`, `inicio`, `fin` |

---

## File Map

| Action | File | What changes |
|--------|------|-------------|
| Modify | `managers/gestor_dashboard.py` | Add `rendimiento_resumen()` + `rendimiento_empleado()` |
| Modify | `blueprints/dashboard.py` | Add 3 routes (1 HTML + 2 JSON) |
| Create | `templates/dashboard/rendimiento.html` | Full page with Chart.js |
| Create | `tests/test_dashboard_sprint4.py` | New test file |

---

### Task 1: GestorDashboard — rendimiento_resumen() + rendimiento_empleado()

**Files:**
- Modify: `managers/gestor_dashboard.py`
- Test: `tests/test_dashboard_sprint4.py` (create)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_dashboard_sprint4.py
from unittest.mock import patch, PropertyMock, MagicMock


# ── Task 1: Manager ──────────────────────────────────────────────────────────

def test_rendimiento_resumen_devuelve_claves_esperadas(app):
    """rendimiento_resumen() devuelve dict con empleados list."""
    from services import gestor_dashboard
    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            mock_q = mock_session.return_value.query.return_value
            mock_q.filter.return_value = mock_q
            mock_q.group_by.return_value = mock_q
            mock_q.all.return_value = []

            result = gestor_dashboard.rendimiento_resumen()

            assert 'empleados' in result
            assert isinstance(result['empleados'], list)


def test_rendimiento_resumen_acepta_filtro_rol(app):
    """rendimiento_resumen() acepta filtro por rol sin error."""
    from services import gestor_dashboard
    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            mock_q = mock_session.return_value.query.return_value
            mock_q.filter.return_value = mock_q
            mock_q.group_by.return_value = mock_q
            mock_q.all.return_value = []

            result = gestor_dashboard.rendimiento_resumen(rol='picker')
            assert 'empleados' in result

            result = gestor_dashboard.rendimiento_resumen(periodo='semana', rol='repartidor')
            assert 'empleados' in result


def test_rendimiento_empleado_devuelve_none_si_no_existe(app):
    """rendimiento_empleado() devuelve None si el empleado no existe."""
    from services import gestor_dashboard
    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            mock_session.return_value.query.return_value.filter_by.return_value.first.return_value = None

            result = gestor_dashboard.rendimiento_empleado(99999)
            assert result is None


def test_rendimiento_empleado_devuelve_claves_esperadas(app):
    """rendimiento_empleado() devuelve kpis, pedidos_por_dia, turnos_recientes, ultimos_pedidos."""
    from services import gestor_dashboard
    with app.app_context():
        emp_mock = MagicMock()
        emp_mock.EmpleadoID = 1
        emp_mock.Nombre = 'Ana'
        emp_mock.Apellido = 'García'
        emp_mock.rol = MagicMock()
        emp_mock.rol.nombre = 'picker'

        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            # Empleado lookup
            mock_session.return_value.query.return_value.filter_by.return_value.first.return_value = emp_mock
            # MetricaDiariaEmpleado queries
            mock_q = mock_session.return_value.query.return_value
            mock_q.filter.return_value = mock_q
            mock_q.group_by.return_value = mock_q
            mock_q.order_by.return_value = mock_q
            mock_q.limit.return_value = mock_q
            mock_q.all.return_value = []
            mock_q.scalar.return_value = None

            result = gestor_dashboard.rendimiento_empleado(1)

            assert result is not None
            assert 'kpis' in result
            assert 'pedidos_por_dia' in result
            assert 'turnos_recientes' in result
            assert 'ultimos_pedidos' in result
            assert 'nombre' in result
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
venv/bin/pytest tests/test_dashboard_sprint4.py -v
```
Expected: 4 failures.

- [ ] **Step 3: Implement rendimiento_resumen() in GestorDashboard**

Append to `managers/gestor_dashboard.py` inside `GestorDashboard` (after `turnos_historial`):

```python
    def rendimiento_resumen(self, periodo: str = 'hoy', rol: str = None) -> dict:
        """Ranking de rendimiento de empleados para el período dado.

        Agrega MetricaDiariaEmpleado por (empleado_id, rol).
        Una empleada polivalente (picker + repartidora) aparece en dos filas
        si no se filtra por rol.

        Args:
            periodo: 'hoy' | 'semana' | 'mes'
            rol:     'picker' | 'repartidor' | None (todos)

        Returns:
            { empleados: [{ id, nombre, rol_sistema, rol_operativo,
                            pedidos, tiempo_medio_min, incidencias, tasa_pct }] }
        """
        from math import ceil
        from sqlalchemy import func
        from models import MetricaDiariaEmpleado

        hoy = datetime.utcnow().date()
        if periodo == 'semana':
            desde = hoy - timedelta(days=6)
        elif periodo == 'mes':
            desde = hoy - timedelta(days=29)
        else:
            desde = hoy

        s = self.session

        query = (
            s.query(
                MetricaDiariaEmpleado.empleado_id,
                MetricaDiariaEmpleado.rol,
                func.sum(MetricaDiariaEmpleado.pedidos_completados).label('pedidos'),
                func.avg(MetricaDiariaEmpleado.tiempo_medio_operacion_min).label('tiempo_medio'),
                func.sum(MetricaDiariaEmpleado.incidencias).label('incidencias'),
            )
            .filter(MetricaDiariaEmpleado.fecha >= desde)
            .group_by(MetricaDiariaEmpleado.empleado_id, MetricaDiariaEmpleado.rol)
        )

        if rol:
            query = query.filter(MetricaDiariaEmpleado.rol == rol)

        rows = query.all()

        # Build empleado name cache
        ids = list({r.empleado_id for r in rows})
        empleados_map = {}
        if ids:
            for emp in s.query(Empleado).filter(Empleado.EmpleadoID.in_(ids)).all():
                empleados_map[emp.EmpleadoID] = emp

        resultado = []
        for r in rows:
            pedidos = int(r.pedidos or 0)
            incidencias = int(r.incidencias or 0)
            tasa = round(pedidos / (pedidos + incidencias) * 100) if (pedidos + incidencias) > 0 else None
            emp = empleados_map.get(r.empleado_id)
            resultado.append({
                'id':               r.empleado_id,
                'nombre':           f'{emp.Nombre} {emp.Apellido}' if emp else f'#{r.empleado_id}',
                'rol_sistema':      emp.rol.nombre if emp and emp.rol else None,
                'rol_operativo':    r.rol,
                'pedidos':          pedidos,
                'tiempo_medio_min': round(r.tiempo_medio) if r.tiempo_medio else None,
                'incidencias':      incidencias,
                'tasa_pct':         tasa,
            })

        resultado.sort(key=lambda e: e['pedidos'], reverse=True)
        return {'empleados': resultado}
```

- [ ] **Step 4: Implement rendimiento_empleado() in GestorDashboard**

Append immediately after `rendimiento_resumen`:

```python
    def rendimiento_empleado(self, empleado_id: int, periodo: str = 'semana') -> dict | None:
        """Detalle de rendimiento individual para el slide-in view.

        Args:
            empleado_id: ID del empleado.
            periodo:     'hoy' | 'semana' | 'mes'

        Returns None si el empleado no existe.

        Returns:
            {
                nombre, rol_sistema,
                kpis: { pedidos, tiempo_medio_min, mejor_tiempo_min, incidencias },
                pedidos_por_dia: [{ fecha, pedidos }],   # últimos 7 días siempre
                turnos_recientes: [{ fecha, inicio, fin, horas }],
                ultimos_pedidos: [{ tipo, pedido_id, fecha, duracion_min }],
            }
        """
        from models import MetricaDiariaEmpleado, CheckIn, PickingPedido, Reparto
        from sqlalchemy import func

        s = self.session
        emp = s.query(Empleado).filter_by(EmpleadoID=empleado_id).first()
        if not emp:
            return None

        hoy = datetime.utcnow().date()
        if periodo == 'semana':
            desde = hoy - timedelta(days=6)
        elif periodo == 'mes':
            desde = hoy - timedelta(days=29)
        else:
            desde = hoy

        # ── KPIs — aggregate from MetricaDiariaEmpleado for the period ──
        agg = (
            s.query(
                func.sum(MetricaDiariaEmpleado.pedidos_completados),
                func.avg(MetricaDiariaEmpleado.tiempo_medio_operacion_min),
                func.min(MetricaDiariaEmpleado.tiempo_medio_operacion_min),
                func.sum(MetricaDiariaEmpleado.incidencias),
            )
            .filter(
                MetricaDiariaEmpleado.empleado_id == empleado_id,
                MetricaDiariaEmpleado.fecha >= desde,
            )
            .first()
        )
        pedidos_total      = int(agg[0] or 0)
        tiempo_medio_avg   = round(agg[1]) if agg[1] else None
        mejor_tiempo       = round(agg[2]) if agg[2] else None
        incidencias_total  = int(agg[3] or 0)

        # ── pedidos_por_dia — always last 7 days for the bar chart ──
        siete_dias = hoy - timedelta(days=6)
        filas_dia = (
            s.query(
                MetricaDiariaEmpleado.fecha,
                func.sum(MetricaDiariaEmpleado.pedidos_completados).label('pedidos'),
            )
            .filter(
                MetricaDiariaEmpleado.empleado_id == empleado_id,
                MetricaDiariaEmpleado.fecha >= siete_dias,
            )
            .group_by(MetricaDiariaEmpleado.fecha)
            .all()
        )
        datos_dia = {r.fecha: int(r.pedidos) for r in filas_dia}
        pedidos_por_dia = []
        for i in range(7):
            dia = siete_dias + timedelta(days=i)
            pedidos_por_dia.append({
                'fecha': dia.isoformat(),
                'pedidos': datos_dia.get(dia, 0),
            })

        # ── turnos_recientes — last 5 check-ins ──
        checkins = (
            s.query(CheckIn)
            .filter_by(empleado_id=empleado_id)
            .order_by(CheckIn.fecha.desc(), CheckIn.inicio.desc())
            .limit(5)
            .all()
        )
        turnos_recientes = []
        for ci in checkins:
            horas = None
            if ci.inicio and ci.fin:
                horas = round((ci.fin - ci.inicio).total_seconds() / 3600, 1)
            turnos_recientes.append({
                'fecha':  ci.fecha.isoformat() if ci.fecha else None,
                'inicio': _iso(ci.inicio),
                'fin':    _iso(ci.fin),
                'horas':  horas,
            })

        # ── ultimos_pedidos — last 10 pickings + repartos in period ──
        desde_dt = datetime(desde.year, desde.month, desde.day)
        pickings = (
            s.query(PickingPedido)
            .filter(
                PickingPedido.empleado_id == empleado_id,
                PickingPedido.estado == 'completado',
                PickingPedido.completado_en >= desde_dt,
            )
            .order_by(PickingPedido.completado_en.desc())
            .limit(10)
            .all()
        )
        repartos = (
            s.query(Reparto)
            .filter(
                Reparto.repartidor_id == empleado_id,
                Reparto.estado == 'entregado',
                Reparto.hora_entrega_real >= desde_dt,
            )
            .order_by(Reparto.hora_entrega_real.desc())
            .limit(10)
            .all()
        )

        ultimos_pedidos = []
        for pk in pickings:
            dur = None
            if pk.iniciado_en and pk.completado_en:
                dur = int((pk.completado_en - pk.iniciado_en).total_seconds() / 60)
            ultimos_pedidos.append({
                'tipo': 'picking',
                'pedido_id': pk.pedido_id,
                'fecha': _iso(pk.completado_en),
                'duracion_min': dur,
            })
        for rp in repartos:
            dur = None
            if rp.hora_salida and rp.hora_entrega_real:
                dur = int((rp.hora_entrega_real - rp.hora_salida).total_seconds() / 60)
            ultimos_pedidos.append({
                'tipo': 'reparto',
                'pedido_id': rp.pedido_id,
                'fecha': _iso(rp.hora_entrega_real),
                'duracion_min': dur,
            })

        # Sort by fecha desc, take last 10
        ultimos_pedidos.sort(key=lambda x: x['fecha'] or '', reverse=True)
        ultimos_pedidos = ultimos_pedidos[:10]

        return {
            'nombre':      f'{emp.Nombre} {emp.Apellido}',
            'rol_sistema': emp.rol.nombre if emp.rol else None,
            'kpis': {
                'pedidos':          pedidos_total,
                'tiempo_medio_min': tiempo_medio_avg,
                'mejor_tiempo_min': mejor_tiempo,
                'incidencias':      incidencias_total,
            },
            'pedidos_por_dia':  pedidos_por_dia,
            'turnos_recientes': turnos_recientes,
            'ultimos_pedidos':  ultimos_pedidos,
        }
```

- [ ] **Step 5: Run Task 1 tests**

```bash
venv/bin/pytest tests/test_dashboard_sprint4.py -v
```
Expected: 4 PASSED.

- [ ] **Step 6: Run full suite**

```bash
venv/bin/pytest -q --tb=short
```

- [ ] **Step 7: Commit**

```bash
git add managers/gestor_dashboard.py tests/test_dashboard_sprint4.py
git commit -m "feat: add rendimiento_resumen() and rendimiento_empleado() to GestorDashboard"
```

---

### Task 2: Flask Routes

**Files:**
- Modify: `blueprints/dashboard.py`
- Test: `tests/test_dashboard_sprint4.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_dashboard_sprint4.py`:

```python
# ── Task 2: Routes ───────────────────────────────────────────────────────────

def test_rendimiento_html_devuelve_200(client):
    """GET /dashboard/rendimiento devuelve 200 para admin autenticado."""
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'
    resp = client.get('/dashboard/rendimiento')
    assert resp.status_code == 200
    assert b'rendimiento' in resp.data.lower()


def test_rendimiento_html_requiere_auth(client):
    """GET /dashboard/rendimiento redirige sin sesión."""
    resp = client.get('/dashboard/rendimiento')
    assert resp.status_code in (302, 401)


def test_rendimiento_resumen_json_devuelve_estructura(client):
    """GET /dashboard/rendimiento-datos devuelve {empleados}."""
    from unittest.mock import patch
    from services import gestor_dashboard

    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    with patch.object(gestor_dashboard, 'rendimiento_resumen', return_value={'empleados': []}):
        resp = client.get('/dashboard/rendimiento-datos')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'empleados' in data


def test_rendimiento_resumen_json_pasa_filtros(client):
    """GET /dashboard/rendimiento-datos pasa periodo y rol al manager."""
    from unittest.mock import patch
    from services import gestor_dashboard

    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    with patch.object(
        gestor_dashboard, 'rendimiento_resumen', return_value={'empleados': []}
    ) as mock_res:
        client.get('/dashboard/rendimiento-datos?periodo=semana&rol=picker')
        mock_res.assert_called_once_with(periodo='semana', rol='picker')


def test_rendimiento_empleado_json_devuelve_404_si_no_existe(client):
    """GET /dashboard/rendimiento/<id> devuelve 404 si el empleado no existe."""
    from unittest.mock import patch
    from services import gestor_dashboard

    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    with patch.object(gestor_dashboard, 'rendimiento_empleado', return_value=None):
        resp = client.get('/dashboard/rendimiento/99999')
        assert resp.status_code == 404


def test_rendimiento_empleado_json_devuelve_datos(client):
    """GET /dashboard/rendimiento/<id> devuelve los datos del empleado."""
    from unittest.mock import patch
    from services import gestor_dashboard

    fake = {
        'nombre': 'Ana García',
        'rol_sistema': 'picker',
        'kpis': {'pedidos': 5, 'tiempo_medio_min': 12, 'mejor_tiempo_min': 8, 'incidencias': 1},
        'pedidos_por_dia': [],
        'turnos_recientes': [],
        'ultimos_pedidos': [],
    }

    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    with patch.object(gestor_dashboard, 'rendimiento_empleado', return_value=fake):
        resp = client.get('/dashboard/rendimiento/1')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['nombre'] == 'Ana García'
        assert 'kpis' in data
```

- [ ] **Step 2: Run new tests to verify they fail**

```bash
venv/bin/pytest tests/test_dashboard_sprint4.py::test_rendimiento_resumen_json_devuelve_estructura tests/test_dashboard_sprint4.py::test_rendimiento_empleado_json_devuelve_404_si_no_existe -v
```
Expected: fail — routes not registered.

- [ ] **Step 3: Add routes to blueprints/dashboard.py**

Append after `turnos_historial` route (before the Write endpoints section):

```python
@blueprint_dashboard.route("/dashboard/rendimiento")
@requiere_rol('manager', 'admin')
def rendimiento():
    return render_template("dashboard/rendimiento.html")


@blueprint_dashboard.route("/dashboard/rendimiento-datos")
@requiere_rol('manager', 'admin')
def rendimiento_datos():
    try:
        periodo = request.args.get("periodo", "hoy")
        rol     = request.args.get("rol") or None
        return _ok(gestor_dashboard.rendimiento_resumen(periodo=periodo, rol=rol))
    except Exception as e:
        logger.error("Error en /dashboard/rendimiento-datos: %s", e)
        return _err("Error interno", 500)


@blueprint_dashboard.route("/dashboard/rendimiento/<int:empleado_id>")
@requiere_rol('manager', 'admin')
def rendimiento_empleado(empleado_id):
    try:
        periodo = request.args.get("periodo", "semana")
        data = gestor_dashboard.rendimiento_empleado(empleado_id, periodo=periodo)
        if data is None:
            return _err("Empleado no encontrado", 404)
        return _ok(data)
    except Exception as e:
        logger.error("Error en /dashboard/rendimiento/%s: %s", empleado_id, e)
        return _err("Error interno", 500)
```

- [ ] **Step 4: Run Task 2 tests (skip HTML template test)**

```bash
venv/bin/pytest tests/test_dashboard_sprint4.py -v -k "not test_rendimiento_html_devuelve_200"
```
Expected: 9 pass.

- [ ] **Step 5: Full suite**

```bash
venv/bin/pytest -q --tb=short
```

- [ ] **Step 6: Commit**

```bash
git add blueprints/dashboard.py tests/test_dashboard_sprint4.py
git commit -m "feat: add /dashboard/rendimiento routes and JSON API endpoints"
```

---

### Task 3: Template — templates/dashboard/rendimiento.html

**Files:**
- Create: `templates/dashboard/rendimiento.html`
- Test: append to `tests/test_dashboard_sprint4.py`

#### Design

```
┌──────────────────────────────────────────────────────┐
│  [Hoy] [Semana] [Mes]    Rol: [Todos ▾]             │  ← period + rol filters
├──────────────────────────────────────────────────────┤
│  Empleado      Rol       Pedidos  T.medio  Incid. %  │  ← ranking table
│  Ana García    Picker    14       11min    2      87  │
│  Luis López    Repart.   9        22min    1      90  │
│  …                                                    │
└──────────────────────────────────────────────────────┘

→ Click on row → individual view slides in:

┌──────────────────────────────────────────────────────┐
│  ← Volver    Ana García — Picker                     │
├────────────┬────────────┬────────────┬───────────────┤
│ 14 pedidos │ 11min med  │ 7min mejor │ 2 incidencias │  ← KPIs
├──────────────────────────────────────────────────────┤
│  [Chart.js bar chart — pedidos por día, 7 barras]    │
├──────────────────────────────────────────────────────┤
│  Últimos pedidos  |  Turnos recientes                │
└──────────────────────────────────────────────────────┘
```

- [ ] **Step 1: Verify test_rendimiento_html_devuelve_200 fails**

```bash
venv/bin/pytest tests/test_dashboard_sprint4.py::test_rendimiento_html_devuelve_200 -v
```
Expected: FAIL.

- [ ] **Step 2: Create the template**

Create `templates/dashboard/rendimiento.html`:

```html
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Rendimiento — Panchi Ops</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
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

{% from 'macros/ui.html' import empty_state, loading_skeleton, error_banner %}

<!-- ── HEADER ─────────────────────────────────────────────────────────────── -->
<header class="sticky top-0 z-30 px-4 pt-4 pb-2">
  <div class="mx-auto max-w-7xl glass-panel rounded-2xl px-5 py-3 flex items-center justify-between gap-4">
    <div class="flex items-center gap-3">
      <span class="text-xl">🍕</span>
      <span class="font-extrabold text-lg tracking-tight" style="color:var(--brand)">Panchi Ops</span>
      <span class="hidden sm:inline text-slate-300">|</span>
      <span class="hidden sm:inline text-sm font-semibold text-slate-500">Rendimiento</span>
    </div>
    {% include 'dashboard/_nav.html' %}
  </div>
</header>

<!-- ── MAIN ───────────────────────────────────────────────────────────────── -->
<main
  class="mx-auto max-w-7xl px-4 py-6"
  x-data="rendimientoApp()"
>

  <!-- ── VISTA LISTA ──────────────────────────────────────────────────────── -->
  <div x-show="vista === 'lista'">

    <!-- Filters -->
    <div class="glass-panel rounded-2xl px-5 py-4 mb-5 flex flex-wrap gap-4 items-center">

      <!-- Período -->
      <div class="flex items-center gap-1 bg-slate-100 rounded-xl p-1">
        <template x-for="p in ['hoy','semana','mes']" :key="p">
          <button
            @click="periodo = p; cargar()"
            :class="periodo === p
              ? 'bg-white shadow-sm text-slate-800 font-semibold'
              : 'text-slate-500 hover:text-slate-700'"
            class="px-3 py-1.5 rounded-lg text-sm capitalize transition"
            x-text="p"
          ></button>
        </template>
      </div>

      <!-- Rol filter -->
      <select
        x-model="rolFiltro"
        @change="cargar()"
        class="rounded-xl border border-slate-200 bg-white/80 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40"
      >
        <option value="">Todos los roles</option>
        <option value="picker">Picker</option>
        <option value="repartidor">Repartidor</option>
      </select>

      <div class="ml-auto text-xs text-slate-400" x-show="!cargando">
        <span x-text="empleados.length"></span> empleados
      </div>
    </div>

    <!-- Error banner -->
    {{ error_banner() }}

    <!-- Loading skeleton -->
    <div x-show="cargando" x-cloak>
      {{ loading_skeleton(rows=6, cols=5) }}
    </div>

    <!-- Empty state -->
    <div x-show="!cargando && empleados.length === 0" x-cloak>
      {{ empty_state('📊', 'Sin datos', 'No hay métricas registradas para este período y rol.') }}
    </div>

    <!-- Ranking table -->
    <div x-show="!cargando && empleados.length > 0" x-cloak class="glass-panel rounded-2xl overflow-hidden">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-slate-100 bg-slate-50/60">
            <th class="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wide">#</th>
            <th class="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wide">Empleado</th>
            <th class="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wide">Rol op.</th>
            <th
              @click="ordenarPor('pedidos')"
              class="px-4 py-3 text-right text-xs font-semibold text-slate-400 uppercase tracking-wide cursor-pointer hover:text-slate-600 select-none"
            >
              Pedidos <span x-show="ordenCol === 'pedidos'" x-text="ordenDir === 'desc' ? '↓' : '↑'"></span>
            </th>
            <th
              @click="ordenarPor('tiempo_medio_min')"
              class="px-4 py-3 text-right text-xs font-semibold text-slate-400 uppercase tracking-wide cursor-pointer hover:text-slate-600 select-none"
            >
              T. medio <span x-show="ordenCol === 'tiempo_medio_min'" x-text="ordenDir === 'desc' ? '↓' : '↑'"></span>
            </th>
            <th
              @click="ordenarPor('incidencias')"
              class="px-4 py-3 text-right text-xs font-semibold text-slate-400 uppercase tracking-wide cursor-pointer hover:text-slate-600 select-none"
            >
              Incid. <span x-show="ordenCol === 'incidencias'" x-text="ordenDir === 'desc' ? '↓' : '↑'"></span>
            </th>
            <th class="px-4 py-3 text-right text-xs font-semibold text-slate-400 uppercase tracking-wide">Tasa</th>
            <th class="px-4 py-3"></th>
          </tr>
        </thead>
        <tbody>
          <template x-for="(emp, idx) in empleadosOrdenados" :key="emp.id + '-' + emp.rol_operativo">
            <tr
              class="border-b border-slate-100 hover:bg-blue-50/40 transition-colors cursor-pointer fade-in"
              @click="abrirDetalle(emp)"
            >
              <td class="px-4 py-3 text-slate-400 text-xs font-mono" x-text="idx + 1"></td>
              <td class="px-4 py-3">
                <div class="flex items-center gap-2">
                  <div
                    class="w-7 h-7 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-xs font-bold flex-shrink-0"
                    x-text="emp.nombre.charAt(0)"
                  ></div>
                  <span class="font-semibold text-slate-800" x-text="emp.nombre"></span>
                </div>
              </td>
              <td class="px-4 py-3 text-slate-500 capitalize text-xs" x-text="emp.rol_operativo"></td>
              <td class="px-4 py-3 text-right font-bold text-slate-800" x-text="emp.pedidos"></td>
              <td class="px-4 py-3 text-right text-slate-600"
                  x-text="emp.tiempo_medio_min !== null ? emp.tiempo_medio_min + 'min' : '—'"></td>
              <td class="px-4 py-3 text-right"
                  :class="emp.incidencias > 0 ? 'text-amber-600 font-semibold' : 'text-slate-400'"
                  x-text="emp.incidencias"></td>
              <td class="px-4 py-3 text-right">
                <span
                  x-show="emp.tasa_pct !== null"
                  class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold"
                  :class="emp.tasa_pct >= 90 ? 'bg-emerald-100 text-emerald-700' : emp.tasa_pct >= 75 ? 'bg-yellow-100 text-yellow-700' : 'bg-red-100 text-red-700'"
                  x-text="emp.tasa_pct + '%'"
                ></span>
                <span x-show="emp.tasa_pct === null" class="text-slate-400 text-xs">—</span>
              </td>
              <td class="px-4 py-3 text-right">
                <span class="text-blue-500 font-semibold text-xs hover:underline">Ver →</span>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>

  </div><!-- /vista lista -->

  <!-- ── VISTA INDIVIDUAL ──────────────────────────────────────────────────── -->
  <div x-show="vista === 'detalle'" x-cloak>

    <!-- Back button + title -->
    <div class="flex items-center gap-3 mb-5">
      <button
        @click="vista = 'lista'; detalle = null"
        class="flex items-center gap-1 text-sm font-semibold text-slate-500 hover:text-slate-800 transition"
      >
        ← Volver
      </button>
      <div class="flex items-center gap-2" x-show="detalle">
        <div class="w-9 h-9 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center font-bold"
          x-text="detalle ? detalle.nombre.charAt(0) : ''"></div>
        <div>
          <p class="font-extrabold text-slate-800" x-text="detalle ? detalle.nombre : ''"></p>
          <p class="text-xs text-slate-400 capitalize" x-text="detalle ? (detalle.rol_sistema || '—') : ''"></p>
        </div>
      </div>
    </div>

    <!-- Loading state -->
    <div x-show="cargandoDetalle" x-cloak>
      {{ loading_skeleton(rows=4, cols=4) }}
    </div>

    <!-- Detail content -->
    <div x-show="!cargandoDetalle && detalle" x-cloak class="space-y-5">

      <!-- KPI cards -->
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div class="glass-panel rounded-2xl px-4 py-4 text-center fade-in">
          <p class="text-3xl font-extrabold text-slate-800" x-text="detalle ? detalle.kpis.pedidos : '—'"></p>
          <p class="text-xs text-slate-400 mt-1 font-semibold uppercase tracking-wide">Pedidos</p>
        </div>
        <div class="glass-panel rounded-2xl px-4 py-4 text-center fade-in">
          <p class="text-3xl font-extrabold text-slate-800"
             x-text="detalle && detalle.kpis.tiempo_medio_min !== null ? detalle.kpis.tiempo_medio_min + 'min' : '—'"></p>
          <p class="text-xs text-slate-400 mt-1 font-semibold uppercase tracking-wide">T. medio</p>
        </div>
        <div class="glass-panel rounded-2xl px-4 py-4 text-center fade-in">
          <p class="text-3xl font-extrabold text-emerald-600"
             x-text="detalle && detalle.kpis.mejor_tiempo_min !== null ? detalle.kpis.mejor_tiempo_min + 'min' : '—'"></p>
          <p class="text-xs text-slate-400 mt-1 font-semibold uppercase tracking-wide">Mejor tiempo</p>
        </div>
        <div class="glass-panel rounded-2xl px-4 py-4 text-center fade-in">
          <p class="text-3xl font-extrabold"
             :class="detalle && detalle.kpis.incidencias > 0 ? 'text-amber-600' : 'text-slate-800'"
             x-text="detalle ? detalle.kpis.incidencias : '—'"></p>
          <p class="text-xs text-slate-400 mt-1 font-semibold uppercase tracking-wide">Incidencias</p>
        </div>
      </div>

      <!-- Bar chart -->
      <div class="glass-panel rounded-2xl px-5 py-5 fade-in">
        <p class="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-4">Pedidos por día (últimos 7 días)</p>
        <div style="height:180px">
          <canvas id="chartPedidosDia"></canvas>
        </div>
      </div>

      <!-- Últimos pedidos + Turnos recientes -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-5">

        <!-- Últimos pedidos -->
        <div class="glass-panel rounded-2xl px-5 py-4 fade-in">
          <p class="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">Últimos pedidos</p>
          <template x-if="detalle && detalle.ultimos_pedidos.length === 0">
            <p class="text-sm text-slate-400 italic">Sin pedidos en el período.</p>
          </template>
          <div class="space-y-2">
            <template x-for="(p, idx) in (detalle ? detalle.ultimos_pedidos : [])" :key="idx">
              <div class="flex items-center justify-between py-1.5 border-b border-slate-100 last:border-0">
                <div class="flex items-center gap-2">
                  <span
                    class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold"
                    :class="p.tipo === 'picking' ? 'bg-blue-100 text-blue-700' : 'bg-orange-100 text-orange-700'"
                    x-text="p.tipo === 'picking' ? 'Pick' : 'Rep'"
                  ></span>
                  <span class="text-sm font-semibold text-slate-700" x-text="'#' + p.pedido_id"></span>
                </div>
                <div class="text-right">
                  <span class="text-xs text-slate-500" x-text="p.duracion_min !== null ? p.duracion_min + 'min' : '—'"></span>
                  <span class="text-xs text-slate-400 ml-2" x-text="formatFecha(p.fecha)"></span>
                </div>
              </div>
            </template>
          </div>
        </div>

        <!-- Turnos recientes -->
        <div class="glass-panel rounded-2xl px-5 py-4 fade-in">
          <p class="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">Turnos recientes</p>
          <template x-if="detalle && detalle.turnos_recientes.length === 0">
            <p class="text-sm text-slate-400 italic">Sin turnos registrados.</p>
          </template>
          <div class="space-y-2">
            <template x-for="(t, idx) in (detalle ? detalle.turnos_recientes : [])" :key="idx">
              <div class="flex items-center justify-between py-1.5 border-b border-slate-100 last:border-0">
                <span class="text-sm text-slate-600 font-mono" x-text="t.fecha"></span>
                <div class="text-right text-xs text-slate-500">
                  <span x-text="formatHora(t.inicio)"></span>
                  <template x-if="t.fin">
                    <span> → <span x-text="formatHora(t.fin)"></span></span>
                  </template>
                  <template x-if="!t.fin">
                    <span class="text-emerald-600 font-semibold"> activo</span>
                  </template>
                  <template x-if="t.horas !== null">
                    <span class="ml-1 font-semibold text-slate-700" x-text="'(' + t.horas + 'h)'"></span>
                  </template>
                </div>
              </div>
            </template>
          </div>
        </div>

      </div><!-- /grid -->

    </div><!-- /detail content -->

  </div><!-- /vista detalle -->

</main>

<script>
function rendimientoApp() {
  return {
    vista: 'lista',
    periodo: 'hoy',
    rolFiltro: '',
    empleados: [],
    cargando: false,
    error: null,
    ordenCol: 'pedidos',
    ordenDir: 'desc',

    // Individual view
    detalle: null,
    cargandoDetalle: false,
    _chart: null,

    init() {
      this.cargar();
    },

    async cargar() {
      this.cargando = true;
      this.error = null;
      try {
        const params = new URLSearchParams({ periodo: this.periodo });
        if (this.rolFiltro) params.set('rol', this.rolFiltro);
        const resp = await fetch('/dashboard/rendimiento-datos?' + params.toString());
        if (!resp.ok) throw new Error('Error ' + resp.status);
        const data = await resp.json();
        this.empleados = data.empleados;
      } catch (e) {
        this.error = 'No se pudo cargar el ranking. ' + e.message;
      } finally {
        this.cargando = false;
      }
    },

    async abrirDetalle(emp) {
      this.vista = 'detalle';
      this.detalle = null;
      this.cargandoDetalle = true;
      try {
        const resp = await fetch(`/dashboard/rendimiento/${emp.id}?periodo=${this.periodo}`);
        if (!resp.ok) throw new Error('Error ' + resp.status);
        this.detalle = await resp.json();
        // Render chart after DOM update
        this.$nextTick(() => this._renderChart());
      } catch (e) {
        this.error = 'No se pudo cargar el detalle. ' + e.message;
        this.vista = 'lista';
      } finally {
        this.cargandoDetalle = false;
      }
    },

    _renderChart() {
      const canvas = document.getElementById('chartPedidosDia');
      if (!canvas || !this.detalle) return;
      if (this._chart) {
        this._chart.destroy();
        this._chart = null;
      }
      const labels = this.detalle.pedidos_por_dia.map(d => {
        const parts = d.fecha.split('-');
        return `${parts[2]}/${parts[1]}`;
      });
      const data = this.detalle.pedidos_por_dia.map(d => d.pedidos);
      this._chart = new Chart(canvas, {
        type: 'bar',
        data: {
          labels,
          datasets: [{
            label: 'Pedidos',
            data,
            backgroundColor: 'rgba(59,130,246,0.6)',
            borderColor: 'rgba(59,130,246,0.9)',
            borderWidth: 1,
            borderRadius: 6,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            y: {
              beginAtZero: true,
              ticks: { stepSize: 1, font: { size: 11 } },
              grid: { color: 'rgba(148,163,184,0.15)' },
            },
            x: {
              ticks: { font: { size: 11 } },
              grid: { display: false },
            },
          },
        },
      });
    },

    ordenarPor(col) {
      if (this.ordenCol === col) {
        this.ordenDir = this.ordenDir === 'desc' ? 'asc' : 'desc';
      } else {
        this.ordenCol = col;
        this.ordenDir = 'desc';
      }
    },

    get empleadosOrdenados() {
      const col = this.ordenCol;
      const dir = this.ordenDir === 'desc' ? -1 : 1;
      return [...this.empleados].sort((a, b) => {
        const av = a[col] ?? -1;
        const bv = b[col] ?? -1;
        return (av - bv) * dir;
      });
    },

    formatFecha(iso) {
      if (!iso) return '—';
      const d = new Date(iso);
      return d.toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit' });
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

- [ ] **Step 3: Run test_rendimiento_html_devuelve_200**

```bash
venv/bin/pytest tests/test_dashboard_sprint4.py::test_rendimiento_html_devuelve_200 -v
```
Expected: PASS.

- [ ] **Step 4: Append 3 template tests**

```python
# ── Task 3: Template ─────────────────────────────────────────────────────────

def test_rendimiento_template_cargable_en_jinja2(app):
    """rendimiento.html se puede cargar en Jinja2 sin errores."""
    with app.app_context():
        template = app.jinja_env.get_template('dashboard/rendimiento.html')
        assert template is not None


def test_rendimiento_html_contiene_nav_links(client):
    """GET /dashboard/rendimiento incluye los links de navegación."""
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'
    resp = client.get('/dashboard/rendimiento')
    assert resp.status_code == 200
    html = resp.data.decode()
    for ruta in ['/dashboard', '/dashboard/monitor', '/dashboard/historial',
                 '/dashboard/turnos', '/dashboard/estadisticas']:
        assert ruta in html, f"Link {ruta} no encontrado en rendimiento.html"


def test_rendimiento_html_contiene_alpine_app(client):
    """GET /dashboard/rendimiento incluye x-data rendimientoApp()."""
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'
    resp = client.get('/dashboard/rendimiento')
    assert resp.status_code == 200
    assert b'rendimientoApp' in resp.data
```

- [ ] **Step 5: Run all Sprint 4 tests**

```bash
venv/bin/pytest tests/test_dashboard_sprint4.py -v
```
Expected: all 13 tests PASS.

- [ ] **Step 6: Full suite**

```bash
venv/bin/pytest -q --tb=short
```

- [ ] **Step 7: Commit**

```bash
git add templates/dashboard/rendimiento.html tests/test_dashboard_sprint4.py
git commit -m "feat: add /dashboard/rendimiento page with ranking table and Chart.js detail view"
```

---

## Summary

| Endpoint | Type | Auth |
|----------|------|------|
| `GET /dashboard/rendimiento` | HTML | manager/admin |
| `GET /dashboard/rendimiento-datos` | JSON | manager/admin |
| `GET /dashboard/rendimiento/<id>` | JSON | manager/admin |

New methods on `GestorDashboard`: `rendimiento_resumen()`, `rendimiento_empleado()`

New template: `templates/dashboard/rendimiento.html` — two-view design (lista → detalle), sortable ranking table, Chart.js bar chart, KPI cards

New tests: 13 in `tests/test_dashboard_sprint4.py`

**Note:** The ranking uses `MetricaDiariaEmpleado` — a pre-computed daily cache table populated by `GestorEmpleado.registrar_metrica_diaria()`. If the table is empty (no metrics computed yet), the ranking will show no results. This is expected behaviour.
