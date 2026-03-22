# Sprint 2 — Historial de Pedidos Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `/dashboard/historial` — a paginated, filterable order history page with a slide-over detail panel.

**Architecture:** Three-layer addition: (1) two new methods on `GestorDashboard` for data access, (2) three new Flask routes in `blueprints/dashboard.py`, (3) a self-contained Jinja2+Alpine.js template. All data flows as JSON through the existing `_ok()/_err()` pattern. No new files — extend existing ones.

**Tech Stack:** Flask, SQLAlchemy (joins + pagination), Alpine.js 3.x, Tailwind CSS CDN, Jinja2 macros from `macros/ui.html`.

---

## File Map

| Action | File | What changes |
|--------|------|-------------|
| Modify | `managers/gestor_dashboard.py` | Add `historial_pedidos()` + `detalle_pedido()` methods |
| Modify | `blueprints/dashboard.py` | Add 3 new routes (1 HTML + 2 JSON) |
| Create | `templates/dashboard/historial.html` | Full page template |
| Modify | `tests/test_dashboard_sprint2.py` | New test file (create) |

---

### Task 1: GestorDashboard — historial_pedidos() + detalle_pedido()

**Files:**
- Modify: `managers/gestor_dashboard.py` (append two methods to `GestorDashboard` class)
- Test: `tests/test_dashboard_sprint2.py` (create)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_dashboard_sprint2.py
from unittest.mock import patch, PropertyMock


# ── Task 1: Manager ──────────────────────────────────────────────────────────

def test_historial_pedidos_devuelve_claves_esperadas(app):
    """historial_pedidos() devuelve dict con pedidos, total, page, pages."""
    from services import gestor_dashboard
    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            mock_q = mock_session.return_value.query.return_value
            mock_q.filter.return_value = mock_q
            mock_q.order_by.return_value = mock_q
            mock_q.count.return_value = 0
            mock_q.offset.return_value = mock_q
            mock_q.limit.return_value = mock_q
            mock_q.all.return_value = []

            result = gestor_dashboard.historial_pedidos()

            assert 'pedidos' in result
            assert 'total' in result
            assert 'page' in result
            assert 'pages' in result
            assert result['pedidos'] == []
            assert result['total'] == 0


def test_historial_pedidos_paginacion_por_defecto(app):
    """historial_pedidos() usa page=1 y per_page=25 por defecto."""
    from services import gestor_dashboard
    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            mock_q = mock_session.return_value.query.return_value
            mock_q.filter.return_value = mock_q
            mock_q.order_by.return_value = mock_q
            mock_q.count.return_value = 100
            mock_q.offset.return_value = mock_q
            mock_q.limit.return_value = mock_q
            mock_q.all.return_value = []

            result = gestor_dashboard.historial_pedidos()

            assert result['page'] == 1
            assert result['pages'] == 4   # ceil(100/25)


def test_detalle_pedido_devuelve_none_si_no_existe(app):
    """detalle_pedido() devuelve None cuando el pedido_id no existe."""
    from services import gestor_dashboard
    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            mock_session.return_value.query.return_value.filter_by.return_value.first.return_value = None

            result = gestor_dashboard.detalle_pedido(999999)

            assert result is None


def test_detalle_pedido_devuelve_claves_esperadas(app):
    """detalle_pedido() devuelve dict con pedido, items, historial, picking, reparto."""
    from unittest.mock import MagicMock
    from services import gestor_dashboard

    with app.app_context():
        pedido_mock = MagicMock()
        pedido_mock.PedidoID = 2001
        pedido_mock.FechaCreacion = None
        pedido_mock.FechaActualizacion = None
        pedido_mock.Estado = 'ENTREGADO'
        pedido_mock.forma_pago = 'online'
        pedido_mock.Total = None
        pedido_mock.TelefonoEntrega = '600000000'
        pedido_mock.DireccionEntrega = 'Calle Test 1'
        pedido_mock.Notas = None
        pedido_mock.cancel_reason = None
        pedido_mock.cliente = None
        pedido_mock.detalles = []
        pedido_mock.historial_estados = []
        pedido_mock.picking = None
        pedido_mock.reparto = None

        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            mock_session.return_value.query.return_value.filter_by.return_value.first.return_value = pedido_mock

            result = gestor_dashboard.detalle_pedido(2001)

            assert result is not None
            assert 'pedido' in result
            assert 'items' in result
            assert 'historial' in result
            assert 'picking' in result
            assert 'reparto' in result
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
venv/bin/pytest tests/test_dashboard_sprint2.py -v
```
Expected: 4 failures — `historial_pedidos` and `detalle_pedido` not defined yet.

- [ ] **Step 3: Implement `historial_pedidos()` in GestorDashboard**

Add after the `pedidos_activos` method (around line 279) in `managers/gestor_dashboard.py`:

```python
def historial_pedidos(
    self,
    desde: str = None,
    hasta: str = None,
    estado: str = None,
    forma_pago: str = None,
    q: str = None,
    page: int = 1,
    per_page: int = 25,
) -> dict:
    """Historial paginado de pedidos con filtros opcionales.

    Args:
        desde: fecha ISO 'YYYY-MM-DD' (inclusive, UTC 00:00)
        hasta: fecha ISO 'YYYY-MM-DD' (inclusive, UTC 23:59:59)
        estado: valor de EstadoPedido
        forma_pago: 'online' | 'efectivo' | 'tarjeta'
        q: búsqueda libre — coincide con PedidoID, nombre de cliente o teléfono
        page: página actual (1-based)
        per_page: resultados por página (máx 100)

    Returns:
        {pedidos: list[dict], total: int, page: int, pages: int}
    """
    from math import ceil
    from sqlalchemy import or_
    from models import Usuario

    per_page = min(per_page, 100)
    s = self.session

    query = s.query(Pedido)

    if desde:
        try:
            dt_desde = datetime.strptime(desde, '%Y-%m-%d')
            query = query.filter(Pedido.FechaCreacion >= dt_desde)
        except ValueError:
            pass

    if hasta:
        try:
            from datetime import timedelta
            dt_hasta = datetime.strptime(hasta, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(Pedido.FechaCreacion < dt_hasta)
        except ValueError:
            pass

    if estado:
        query = query.filter(Pedido.Estado == estado)

    if forma_pago:
        query = query.filter(Pedido.forma_pago == forma_pago)

    if q:
        q_strip = q.strip()
        # Try numeric search (pedido_id)
        if q_strip.isdigit():
            query = query.filter(Pedido.PedidoID == int(q_strip))
        else:
            # Join with Usuario for name/phone search
            query = query.outerjoin(Usuario, Pedido.ClienteID == Usuario.id).filter(
                or_(
                    Usuario.nombre.ilike(f'%{q_strip}%'),
                    Pedido.TelefonoEntrega.ilike(f'%{q_strip}%'),
                )
            )

    total = query.count()
    pages = ceil(total / per_page) if total else 1

    pedidos = (
        query
        .order_by(Pedido.FechaCreacion.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    resultado = []
    for p in pedidos:
        resultado.append({
            "pedido_id": p.PedidoID,
            "cliente_nombre": p.cliente.nombre if p.cliente else "—",
            "cliente_telefono": p.TelefonoEntrega,
            "estado": p.Estado,
            "forma_pago": p.forma_pago or "online",
            "total": float(p.Total) if p.Total else 0.0,
            "fecha_creacion": _iso(p.FechaCreacion),
            "fecha_actualizacion": _iso(p.FechaActualizacion),
            "notas": p.Notas,
            "cancel_reason": p.cancel_reason,
        })

    return {"pedidos": resultado, "total": total, "page": page, "pages": pages}
```

- [ ] **Step 4: Implement `detalle_pedido()` in GestorDashboard**

Add immediately after `historial_pedidos`:

```python
def detalle_pedido(self, pedido_id: int) -> dict | None:
    """Devuelve el detalle completo de un pedido para el slide-over panel.

    Returns None si el pedido no existe.

    Returns:
        {
            pedido: {...},
            items: [{detalle_id, nombre, cantidad, precio_unitario, subtotal}],
            historial: [{estado_anterior, estado_nuevo, cambiado_en, notas}],
            picking: {estado, picker_nombre, iniciado_en, completado_en} | None,
            reparto: {estado, repartidor_nombre, hora_salida, hora_entrega_real,
                      metodo_cobro, importe_cobrado} | None,
        }
    """
    s = self.session
    p = s.query(Pedido).filter_by(PedidoID=pedido_id).first()
    if not p:
        return None

    items = [
        {
            "detalle_id": d.DetalleID,
            "nombre": d.NombreProducto or (d.producto.Nombre if d.producto else "—"),
            "cantidad": d.Cantidad,
            "precio_unitario": float(d.PrecioUnitario) if d.PrecioUnitario else 0.0,
            "subtotal": float(d.Subtotal) if d.Subtotal else 0.0,
        }
        for d in p.detalles
    ]

    historial = [
        {
            "estado_anterior": h.estado_anterior,
            "estado_nuevo": h.estado_nuevo,
            "cambiado_en": _iso(h.cambiado_en),
            "notas": h.notas,
        }
        for h in sorted(p.historial_estados, key=lambda h: h.cambiado_en or datetime.min)
    ]

    picking = None
    if p.picking:
        pk = p.picking
        picking = {
            "estado": pk.estado,
            "picker_nombre": (
                f"{pk.empleado.Nombre} {pk.empleado.Apellido}" if pk.empleado else None
            ),
            "asignado_en": _iso(pk.created_at),
            "iniciado_en": _iso(pk.iniciado_en),
            "completado_en": _iso(pk.completado_en),
        }

    reparto = None
    if p.reparto:
        rp = p.reparto
        reparto = {
            "estado": rp.estado,
            "repartidor_nombre": (
                f"{rp.repartidor.Nombre} {rp.repartidor.Apellido}" if rp.repartidor else None
            ),
            "hora_salida": _iso(rp.hora_salida),
            "hora_entrega_real": _iso(rp.hora_entrega_real),
            "metodo_cobro": rp.metodo_cobro,
            "importe_cobrado": float(rp.importe_cobrado) if rp.importe_cobrado else None,
        }

    pedido_dict = {
        "pedido_id": p.PedidoID,
        "cliente_nombre": p.cliente.nombre if p.cliente else "—",
        "cliente_telefono": p.TelefonoEntrega,
        "direccion_entrega": p.DireccionEntrega,
        "estado": p.Estado,
        "forma_pago": p.forma_pago or "online",
        "total": float(p.Total) if p.Total else 0.0,
        "fecha_creacion": _iso(p.FechaCreacion),
        "fecha_actualizacion": _iso(p.FechaActualizacion),
        "notas": p.Notas,
        "cancel_reason": p.cancel_reason,
    }

    return {
        "pedido": pedido_dict,
        "items": items,
        "historial": historial,
        "picking": picking,
        "reparto": reparto,
    }
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
venv/bin/pytest tests/test_dashboard_sprint2.py -v
```
Expected: 4 PASSED.

- [ ] **Step 6: Run full suite to confirm no regressions**

```bash
venv/bin/pytest -v --tb=short -q
```
Expected: same count as before + 4 new passing tests.

- [ ] **Step 7: Commit**

```bash
git add managers/gestor_dashboard.py tests/test_dashboard_sprint2.py
git commit -m "feat: add historial_pedidos() and detalle_pedido() to GestorDashboard"
```

---

### Task 2: Flask Routes — /dashboard/historial + JSON endpoints

**Files:**
- Modify: `blueprints/dashboard.py`
- Test: `tests/test_dashboard_sprint2.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_dashboard_sprint2.py`:

```python
# ── Task 2: Routes ───────────────────────────────────────────────────────────

def test_historial_html_devuelve_200(client):
    """GET /dashboard/historial devuelve 200 para admin autenticado."""
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'
    resp = client.get('/dashboard/historial')
    assert resp.status_code == 200
    assert b'historial' in resp.data.lower()


def test_historial_html_requiere_auth(client):
    """GET /dashboard/historial redirige a login sin sesión."""
    resp = client.get('/dashboard/historial')
    assert resp.status_code in (302, 401)


def test_historial_pedidos_json_devuelve_estructura(client):
    """GET /dashboard/historial-pedidos devuelve {pedidos, total, page, pages}."""
    from unittest.mock import patch
    from services import gestor_dashboard

    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    with patch.object(
        gestor_dashboard, 'historial_pedidos',
        return_value={"pedidos": [], "total": 0, "page": 1, "pages": 1}
    ):
        resp = client.get('/dashboard/historial-pedidos')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'pedidos' in data
        assert 'total' in data
        assert 'page' in data
        assert 'pages' in data


def test_historial_pedidos_json_pasa_filtros(client):
    """GET /dashboard/historial-pedidos pasa query params al manager."""
    from unittest.mock import patch, call
    from services import gestor_dashboard

    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    with patch.object(
        gestor_dashboard, 'historial_pedidos',
        return_value={"pedidos": [], "total": 0, "page": 1, "pages": 1}
    ) as mock_historial:
        client.get('/dashboard/historial-pedidos?estado=ENTREGADO&page=2')
        mock_historial.assert_called_once_with(
            desde=None, hasta=None, estado='ENTREGADO',
            forma_pago=None, q=None, page=2, per_page=25
        )


def test_detalle_pedido_json_devuelve_404_si_no_existe(client):
    """GET /dashboard/pedido/<id>/detalle devuelve 404 si no existe."""
    from unittest.mock import patch
    from services import gestor_dashboard

    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    with patch.object(gestor_dashboard, 'detalle_pedido', return_value=None):
        resp = client.get('/dashboard/pedido/999999/detalle')
        assert resp.status_code == 404


def test_detalle_pedido_json_devuelve_datos(client):
    """GET /dashboard/pedido/<id>/detalle devuelve los datos del pedido."""
    from unittest.mock import patch
    from services import gestor_dashboard

    fake_detalle = {
        "pedido": {"pedido_id": 2001, "estado": "ENTREGADO"},
        "items": [],
        "historial": [],
        "picking": None,
        "reparto": None,
    }

    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    with patch.object(gestor_dashboard, 'detalle_pedido', return_value=fake_detalle):
        resp = client.get('/dashboard/pedido/2001/detalle')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['pedido']['pedido_id'] == 2001
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
venv/bin/pytest tests/test_dashboard_sprint2.py::test_historial_html_devuelve_200 tests/test_dashboard_sprint2.py::test_historial_pedidos_json_devuelve_estructura tests/test_dashboard_sprint2.py::test_detalle_pedido_json_devuelve_404_si_no_existe -v
```
Expected: 3 errors — routes not registered yet.

- [ ] **Step 3: Add routes to blueprints/dashboard.py**

Append after the existing `@blueprint_dashboard.route("/dashboard/empleados")` block (before the Write endpoints section):

```python
@blueprint_dashboard.route("/dashboard/historial")
@requiere_rol('manager', 'admin')
def historial():
    return render_template("dashboard/historial.html")


@blueprint_dashboard.route("/dashboard/historial-pedidos")
@requiere_rol('manager', 'admin')
def historial_pedidos():
    try:
        desde = request.args.get("desde")
        hasta = request.args.get("hasta")
        estado = request.args.get("estado")
        forma_pago = request.args.get("forma_pago")
        q = request.args.get("q")
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 25))
        return _ok(gestor_dashboard.historial_pedidos(
            desde=desde, hasta=hasta, estado=estado,
            forma_pago=forma_pago, q=q, page=page, per_page=per_page,
        ))
    except Exception as e:
        logger.error("Error en /dashboard/historial-pedidos: %s", e)
        return _err("Error interno", 500)


@blueprint_dashboard.route("/dashboard/pedido/<int:pedido_id>/detalle")
@requiere_rol('manager', 'admin')
def detalle_pedido(pedido_id):
    try:
        data = gestor_dashboard.detalle_pedido(pedido_id)
        if data is None:
            return _err("Pedido no encontrado", 404)
        return _ok(data)
    except Exception as e:
        logger.error("Error en /dashboard/pedido/%s/detalle: %s", pedido_id, e)
        return _err("Error interno", 500)
```

- [ ] **Step 4: Run all Task 2 tests**

```bash
venv/bin/pytest tests/test_dashboard_sprint2.py -v
```
Expected: all tests pass (both Task 1 and Task 2 tests — 10 total).

**Note on `test_historial_html_devuelve_200`:** This test will still fail until Task 3 creates the template. That's expected — this test is a contract for Task 3.

- [ ] **Step 5: Run full suite**

```bash
venv/bin/pytest -v --tb=short -q
```

- [ ] **Step 6: Commit**

```bash
git add blueprints/dashboard.py tests/test_dashboard_sprint2.py
git commit -m "feat: add /dashboard/historial routes and JSON API endpoints"
```

---

### Task 3: Template — templates/dashboard/historial.html

**Files:**
- Create: `templates/dashboard/historial.html`
- Test: existing `test_historial_html_devuelve_200` from Task 2 should now pass

- [ ] **Step 1: Check that test_historial_html_devuelve_200 still fails**

```bash
venv/bin/pytest tests/test_dashboard_sprint2.py::test_historial_html_devuelve_200 -v
```
Expected: FAIL (template not found).

- [ ] **Step 2: Create the template**

Create `templates/dashboard/historial.html` with the following content:

```html
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Historial de Pedidos — Panchi Ops</title>
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
    /* Slide-over */
    .slide-over {
      transform: translateX(100%);
      transition: transform 0.3s cubic-bezier(0.4,0,0.2,1);
    }
    .slide-over.open {
      transform: translateX(0);
    }
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
      <span class="hidden sm:inline text-sm font-semibold text-slate-500">Historial de Pedidos</span>
    </div>
    {% include 'dashboard/_nav.html' %}
  </div>
</header>

<!-- ── MAIN ───────────────────────────────────────────────────────────────── -->
<main
  class="mx-auto max-w-7xl px-4 py-6"
  x-data="historialApp()"
  x-init="cargar()"
>

  <!-- Filter Bar -->
  <div class="glass-panel rounded-2xl px-5 py-4 mb-5">
    <div class="flex flex-wrap gap-3 items-end">

      <!-- Búsqueda libre -->
      <div class="flex-1 min-w-[180px]">
        <label class="block text-xs font-semibold text-slate-500 mb-1">Buscar</label>
        <input
          type="text"
          x-model.debounce.400ms="filtros.q"
          @input="pagina = 1; cargar()"
          placeholder="# pedido, nombre, teléfono…"
          class="w-full rounded-xl border border-slate-200 bg-white/80 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40"
        />
      </div>

      <!-- Fecha desde -->
      <div>
        <label class="block text-xs font-semibold text-slate-500 mb-1">Desde</label>
        <input
          type="date"
          x-model="filtros.desde"
          @change="pagina = 1; cargar()"
          class="rounded-xl border border-slate-200 bg-white/80 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40"
        />
      </div>

      <!-- Fecha hasta -->
      <div>
        <label class="block text-xs font-semibold text-slate-500 mb-1">Hasta</label>
        <input
          type="date"
          x-model="filtros.hasta"
          @change="pagina = 1; cargar()"
          class="rounded-xl border border-slate-200 bg-white/80 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40"
        />
      </div>

      <!-- Estado -->
      <div>
        <label class="block text-xs font-semibold text-slate-500 mb-1">Estado</label>
        <select
          x-model="filtros.estado"
          @change="pagina = 1; cargar()"
          class="rounded-xl border border-slate-200 bg-white/80 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40"
        >
          <option value="">Todos</option>
          <option value="PENDIENTE">Pendiente</option>
          <option value="CONFIRMANDO_PAGO">Confirmando pago</option>
          <option value="PAGADO">Pagado</option>
          <option value="CONTRA_REEMBOLSO">Contrarrembolso</option>
          <option value="EN_PREPARACION">En preparación</option>
          <option value="PREPARADO">Preparado</option>
          <option value="EN_REPARTO">En reparto</option>
          <option value="ENTREGADO">Entregado</option>
          <option value="CANCELADO">Cancelado</option>
          <option value="REEMBOLSADO">Reembolsado</option>
        </select>
      </div>

      <!-- Forma de pago -->
      <div>
        <label class="block text-xs font-semibold text-slate-500 mb-1">Pago</label>
        <select
          x-model="filtros.forma_pago"
          @change="pagina = 1; cargar()"
          class="rounded-xl border border-slate-200 bg-white/80 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40"
        >
          <option value="">Todos</option>
          <option value="online">Online</option>
          <option value="efectivo">Efectivo</option>
          <option value="tarjeta">Tarjeta</option>
        </select>
      </div>

      <!-- Limpiar filtros -->
      <button
        @click="limpiarFiltros()"
        class="rounded-xl border border-slate-200 bg-white/80 px-3 py-2 text-sm font-semibold text-slate-500 hover:bg-slate-100 transition"
      >
        Limpiar
      </button>

    </div>

    <!-- Contador de resultados -->
    <div class="mt-3 text-xs text-slate-500 font-medium" x-show="!cargando">
      <span x-text="total"></span> pedidos encontrados
    </div>
  </div>

  <!-- Error banner -->
  {{ error_banner() }}

  <!-- Tabla -->
  <div class="glass-panel rounded-2xl overflow-hidden">

    <!-- Loading skeleton -->
    <div x-show="cargando" x-cloak>
      {{ loading_skeleton(rows=8, cols=6) }}
    </div>

    <!-- Empty state -->
    <div x-show="!cargando && pedidos.length === 0" x-cloak>
      {{ empty_state('📭', 'Sin resultados', 'Prueba a cambiar los filtros o el rango de fechas.') }}
    </div>

    <!-- Data table -->
    <div x-show="!cargando && pedidos.length > 0" x-cloak>
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-slate-100 bg-slate-50/60">
            <th class="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wide">#</th>
            <th class="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wide">Cliente</th>
            <th class="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wide">Estado</th>
            <th class="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wide">Pago</th>
            <th class="px-4 py-3 text-right text-xs font-semibold text-slate-400 uppercase tracking-wide">Total</th>
            <th class="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wide">Fecha</th>
            <th class="px-4 py-3"></th>
          </tr>
        </thead>
        <tbody>
          <template x-for="p in pedidos" :key="p.pedido_id">
            <tr
              class="border-b border-slate-100 hover:bg-blue-50/40 transition-colors cursor-pointer fade-in"
              @click="abrirDetalle(p.pedido_id)"
            >
              <td class="px-4 py-3 font-mono font-semibold text-slate-700" x-text="'#' + p.pedido_id"></td>
              <td class="px-4 py-3">
                <span class="font-semibold text-slate-800" x-text="p.cliente_nombre"></span>
                <span class="block text-xs text-slate-400" x-text="p.cliente_telefono"></span>
              </td>
              <td class="px-4 py-3">
                <!-- Status badge rendered client-side to avoid round-trip -->
                <span
                  class="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold"
                  :class="estadoClases(p.estado)"
                  x-text="estadoEtiqueta(p.estado)"
                ></span>
              </td>
              <td class="px-4 py-3 capitalize text-slate-600" x-text="p.forma_pago"></td>
              <td class="px-4 py-3 text-right font-semibold text-slate-800" x-text="'€' + p.total.toFixed(2)"></td>
              <td class="px-4 py-3 text-slate-500 text-xs" x-text="formatFecha(p.fecha_creacion)"></td>
              <td class="px-4 py-3 text-right">
                <span class="text-blue-500 font-semibold text-xs hover:underline">Ver →</span>
              </td>
            </tr>
          </template>
        </tbody>
      </table>

      <!-- Pagination -->
      <div class="flex items-center justify-between px-4 py-3 border-t border-slate-100" x-show="pages > 1">
        <button
          @click="pagina = pagina - 1; cargar()"
          :disabled="pagina <= 1"
          class="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-semibold text-slate-600 disabled:opacity-40 hover:bg-slate-50 transition"
        >
          ← Anterior
        </button>
        <span class="text-sm text-slate-500">
          Página <span class="font-semibold text-slate-800" x-text="pagina"></span>
          de <span x-text="pages"></span>
        </span>
        <button
          @click="pagina = pagina + 1; cargar()"
          :disabled="pagina >= pages"
          class="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-semibold text-slate-600 disabled:opacity-40 hover:bg-slate-50 transition"
        >
          Siguiente →
        </button>
      </div>
    </div>

  </div><!-- /glass-panel tabla -->

  <!-- ── SLIDE-OVER DETAIL PANEL ─────────────────────────────────────────── -->
  <!-- Backdrop -->
  <div
    x-show="panelAbierto"
    x-cloak
    x-transition:enter="transition ease-out duration-200"
    x-transition:enter-start="opacity-0"
    x-transition:enter-end="opacity-100"
    x-transition:leave="transition ease-in duration-150"
    x-transition:leave-start="opacity-100"
    x-transition:leave-end="opacity-0"
    @click="cerrarPanel()"
    class="fixed inset-0 z-40 bg-slate-900/30 backdrop-blur-sm"
  ></div>

  <!-- Panel -->
  <div
    x-show="panelAbierto"
    x-cloak
    x-transition:enter="transition ease-out duration-300"
    x-transition:enter-start="translate-x-full"
    x-transition:enter-end="translate-x-0"
    x-transition:leave="transition ease-in duration-200"
    x-transition:leave-start="translate-x-0"
    x-transition:leave-end="translate-x-full"
    class="fixed top-0 right-0 h-full w-full max-w-lg z-50 bg-white shadow-2xl flex flex-col overflow-hidden"
  >
    <!-- Panel header -->
    <div class="flex items-center justify-between px-6 py-4 border-b border-slate-100">
      <div>
        <p class="text-xs font-semibold text-slate-400 uppercase tracking-wide">Detalle</p>
        <h2 class="text-lg font-extrabold text-slate-800" x-text="detalle ? '#' + detalle.pedido.pedido_id : '…'"></h2>
      </div>
      <button @click="cerrarPanel()" class="rounded-full p-2 hover:bg-slate-100 transition text-slate-400 hover:text-slate-700">
        ✕
      </button>
    </div>

    <!-- Panel body -->
    <div class="flex-1 overflow-y-auto px-6 py-4 space-y-6" x-show="detalle && !cargandoDetalle">

      <!-- Estado + resumen -->
      <div class="flex items-start justify-between gap-3">
        <div>
          <span
            class="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold"
            :class="detalle ? estadoClases(detalle.pedido.estado) : ''"
            x-text="detalle ? estadoEtiqueta(detalle.pedido.estado) : ''"
          ></span>
          <p class="mt-1 text-sm text-slate-500" x-text="detalle ? formatFecha(detalle.pedido.fecha_creacion) : ''"></p>
        </div>
        <div class="text-right">
          <p class="text-2xl font-extrabold text-slate-800" x-text="detalle ? '€' + detalle.pedido.total.toFixed(2) : ''"></p>
          <p class="text-xs text-slate-400 capitalize" x-text="detalle ? detalle.pedido.forma_pago : ''"></p>
        </div>
      </div>

      <!-- Cliente + dirección -->
      <div class="rounded-xl bg-slate-50 px-4 py-3 space-y-1">
        <p class="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">Cliente</p>
        <p class="font-semibold text-slate-800" x-text="detalle ? detalle.pedido.cliente_nombre : ''"></p>
        <p class="text-sm text-slate-500" x-text="detalle ? detalle.pedido.cliente_telefono : ''"></p>
        <p class="text-sm text-slate-500" x-text="detalle ? detalle.pedido.direccion_entrega : ''"></p>
      </div>

      <!-- Items -->
      <div>
        <p class="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">Artículos</p>
        <template x-if="detalle && detalle.items.length === 0">
          <p class="text-sm text-slate-400 italic">Sin artículos registrados.</p>
        </template>
        <template x-for="item in (detalle ? detalle.items : [])" :key="item.detalle_id">
          <div class="flex items-center justify-between py-2 border-b border-slate-100 last:border-0">
            <div>
              <span class="font-semibold text-slate-700" x-text="item.nombre"></span>
              <span class="ml-1 text-slate-400 text-xs" x-text="'× ' + item.cantidad"></span>
            </div>
            <span class="font-semibold text-slate-700" x-text="'€' + item.subtotal.toFixed(2)"></span>
          </div>
        </template>
      </div>

      <!-- Historial de estados -->
      <div>
        <p class="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">Historial</p>
        <template x-if="detalle && detalle.historial.length === 0">
          <p class="text-sm text-slate-400 italic">Sin historial de estados.</p>
        </template>
        <ol class="relative border-l border-slate-200 ml-2 space-y-3">
          <template x-for="(h, idx) in (detalle ? detalle.historial : [])" :key="idx">
            <li class="ml-4">
              <div class="absolute -left-1.5 w-3 h-3 rounded-full bg-slate-300 border-2 border-white"></div>
              <p class="text-xs text-slate-400" x-text="formatFecha(h.cambiado_en)"></p>
              <p class="text-sm font-semibold text-slate-700">
                <span x-text="h.estado_anterior || '—'"></span>
                <span class="text-slate-400 mx-1">→</span>
                <span x-text="h.estado_nuevo"></span>
              </p>
              <p class="text-xs text-slate-500 italic" x-show="h.notas" x-text="h.notas"></p>
            </li>
          </template>
        </ol>
      </div>

      <!-- Picking -->
      <div x-show="detalle && detalle.picking">
        <p class="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">Picking</p>
        <div class="rounded-xl bg-slate-50 px-4 py-3 space-y-1 text-sm">
          <p><span class="text-slate-400">Picker:</span> <span class="font-semibold text-slate-700" x-text="detalle && detalle.picking ? (detalle.picking.picker_nombre || '—') : ''"></span></p>
          <p><span class="text-slate-400">Estado:</span> <span class="font-semibold text-slate-700" x-text="detalle && detalle.picking ? detalle.picking.estado : ''"></span></p>
          <p x-show="detalle && detalle.picking && detalle.picking.completado_en">
            <span class="text-slate-400">Completado:</span>
            <span x-text="detalle && detalle.picking ? formatFecha(detalle.picking.completado_en) : ''"></span>
          </p>
        </div>
      </div>

      <!-- Reparto -->
      <div x-show="detalle && detalle.reparto">
        <p class="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">Reparto</p>
        <div class="rounded-xl bg-slate-50 px-4 py-3 space-y-1 text-sm">
          <p><span class="text-slate-400">Repartidor:</span> <span class="font-semibold text-slate-700" x-text="detalle && detalle.reparto ? (detalle.reparto.repartidor_nombre || '—') : ''"></span></p>
          <p><span class="text-slate-400">Estado:</span> <span class="font-semibold text-slate-700" x-text="detalle && detalle.reparto ? detalle.reparto.estado : ''"></span></p>
          <p x-show="detalle && detalle.reparto && detalle.reparto.hora_entrega_real">
            <span class="text-slate-400">Entregado:</span>
            <span x-text="detalle && detalle.reparto ? formatFecha(detalle.reparto.hora_entrega_real) : ''"></span>
          </p>
          <p x-show="detalle && detalle.reparto && detalle.reparto.importe_cobrado">
            <span class="text-slate-400">Cobrado:</span>
            <span x-text="detalle && detalle.reparto && detalle.reparto.importe_cobrado ? '€' + detalle.reparto.importe_cobrado.toFixed(2) + ' (' + (detalle.reparto.metodo_cobro || '—') + ')' : ''"></span>
          </p>
        </div>
      </div>

      <!-- Notas / cancelación -->
      <div x-show="detalle && (detalle.pedido.notas || detalle.pedido.cancel_reason)">
        <p class="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">Notas</p>
        <p class="text-sm text-slate-600 italic" x-text="detalle ? (detalle.pedido.cancel_reason || detalle.pedido.notas) : ''"></p>
      </div>

    </div><!-- /panel body -->

    <!-- Loading state in panel -->
    <div x-show="cargandoDetalle" x-cloak class="flex-1 flex items-center justify-center">
      <div class="animate-spin w-8 h-8 rounded-full border-4 border-blue-200 border-t-blue-500"></div>
    </div>

  </div><!-- /slide-over panel -->

</main>

<script>
function historialApp() {
  return {
    pedidos: [],
    total: 0,
    pagina: 1,
    pages: 1,
    cargando: false,
    error: null,

    filtros: {
      q: '',
      desde: '',
      hasta: '',
      estado: '',
      forma_pago: '',
    },

    // Detail panel
    panelAbierto: false,
    detalle: null,
    cargandoDetalle: false,

    async cargar() {
      this.cargando = true;
      this.error = null;
      try {
        const params = new URLSearchParams();
        if (this.filtros.q)          params.set('q',          this.filtros.q);
        if (this.filtros.desde)      params.set('desde',      this.filtros.desde);
        if (this.filtros.hasta)      params.set('hasta',      this.filtros.hasta);
        if (this.filtros.estado)     params.set('estado',     this.filtros.estado);
        if (this.filtros.forma_pago) params.set('forma_pago', this.filtros.forma_pago);
        params.set('page', this.pagina);
        params.set('per_page', 25);

        const resp = await fetch('/dashboard/historial-pedidos?' + params.toString());
        if (!resp.ok) throw new Error('Error ' + resp.status);
        const data = await resp.json();

        this.pedidos = data.pedidos;
        this.total   = data.total;
        this.pagina  = data.page;
        this.pages   = data.pages;
      } catch (e) {
        this.error = 'No se pudo cargar el historial. ' + e.message;
      } finally {
        this.cargando = false;
      }
    },

    async abrirDetalle(pedidoId) {
      this.panelAbierto = true;
      this.detalle = null;
      this.cargandoDetalle = true;
      try {
        const resp = await fetch(`/dashboard/pedido/${pedidoId}/detalle`);
        if (!resp.ok) throw new Error('Error ' + resp.status);
        this.detalle = await resp.json();
      } catch (e) {
        this.error = 'No se pudo cargar el detalle. ' + e.message;
        this.panelAbierto = false;
      } finally {
        this.cargandoDetalle = false;
      }
    },

    cerrarPanel() {
      this.panelAbierto = false;
      this.detalle = null;
    },

    limpiarFiltros() {
      this.filtros = { q: '', desde: '', hasta: '', estado: '', forma_pago: '' };
      this.pagina = 1;
      this.cargar();
    },

    formatFecha(iso) {
      if (!iso) return '—';
      const d = new Date(iso);
      return d.toLocaleString('es-ES', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit',
      });
    },

    // Client-side status badge helpers (mirror of Jinja2 macro)
    _estadoConf: {
      'PENDIENTE':        ['bg-slate-100 text-slate-600',    'Pendiente'],
      'ENLACE':           ['bg-slate-100 text-slate-600',    'Enlace'],
      'ENLACE2':          ['bg-slate-100 text-slate-600',    'Enlace 2'],
      'CONFIRMANDO_PAGO': ['bg-yellow-100 text-yellow-700',  'Confirmando'],
      'PAGADO':           ['bg-emerald-100 text-emerald-700','Pagado'],
      'CONTRA_REEMBOLSO': ['bg-violet-100 text-violet-700',  'Contrarremb.'],
      'EN_PREPARACION':   ['bg-blue-100 text-blue-700',      'Preparando'],
      'PREPARADO':        ['bg-indigo-100 text-indigo-700',  'Preparado'],
      'EN_REPARTO':       ['bg-orange-100 text-orange-700',  'En reparto'],
      'ENTREGADO':        ['bg-emerald-100 text-emerald-800','Entregado'],
      'CANCELADO':        ['bg-red-100 text-red-700',        'Cancelado'],
      'REEMBOLSADO':      ['bg-slate-100 text-slate-500',    'Reembolsado'],
    },
    estadoClases(estado) {
      return (this._estadoConf[estado] || ['bg-slate-100 text-slate-500', estado])[0];
    },
    estadoEtiqueta(estado) {
      return (this._estadoConf[estado] || ['bg-slate-100 text-slate-500', estado])[1];
    },
  };
}
</script>

</body>
</html>
```

- [ ] **Step 3: Run test_historial_html_devuelve_200**

```bash
venv/bin/pytest tests/test_dashboard_sprint2.py::test_historial_html_devuelve_200 -v
```
Expected: PASS.

- [ ] **Step 4: Add template content test**

Append to `tests/test_dashboard_sprint2.py`:

```python
# ── Task 3: Template ─────────────────────────────────────────────────────────

def test_historial_template_cargable_en_jinja2(app):
    """historial.html se puede cargar en Jinja2 sin errores de sintaxis."""
    with app.app_context():
        template = app.jinja_env.get_template('dashboard/historial.html')
        assert template is not None


def test_historial_html_contiene_nav_links(client):
    """GET /dashboard/historial incluye los links de navegación del partial."""
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'
    resp = client.get('/dashboard/historial')
    assert resp.status_code == 200
    html = resp.data.decode()
    for ruta in ['/dashboard', '/dashboard/monitor', '/dashboard/turnos',
                 '/dashboard/rendimiento', '/dashboard/estadisticas']:
        assert ruta in html, f"Link {ruta} no encontrado en historial.html"


def test_historial_html_contiene_alpine_app(client):
    """GET /dashboard/historial incluye x-data historialApp()."""
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'
    resp = client.get('/dashboard/historial')
    assert resp.status_code == 200
    assert b'historialApp' in resp.data
```

- [ ] **Step 5: Run all Sprint 2 tests**

```bash
venv/bin/pytest tests/test_dashboard_sprint2.py -v
```
Expected: all 13 tests PASS.

- [ ] **Step 6: Run full suite**

```bash
venv/bin/pytest -v --tb=short -q
```
Expected: zero regressions.

- [ ] **Step 7: Commit**

```bash
git add templates/dashboard/historial.html tests/test_dashboard_sprint2.py
git commit -m "feat: add /dashboard/historial page with filters, table, and slide-over panel"
```

---

## Summary

After all 3 tasks:

| Endpoint | Type | Auth |
|----------|------|------|
| `GET /dashboard/historial` | HTML | manager/admin |
| `GET /dashboard/historial-pedidos` | JSON | manager/admin |
| `GET /dashboard/pedido/<id>/detalle` | JSON | manager/admin |

New methods on `GestorDashboard`: `historial_pedidos()`, `detalle_pedido()`

New template: `templates/dashboard/historial.html` (self-contained, Alpine.js component)

New tests: 13 in `tests/test_dashboard_sprint2.py`
