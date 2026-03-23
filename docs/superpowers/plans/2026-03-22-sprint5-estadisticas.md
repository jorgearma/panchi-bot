# Sprint 5 — Estadísticas e Histórico Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `/dashboard/estadisticas` — a period-selectable statistics page with 6 KPI cards and 4 Chart.js charts (line: pedidos+ingresos dual-axis, horizontal bar: estado distribution, donut: payment method, line: operation times).

**Architecture:** Same three-layer pattern as previous sprints. One new `GestorDashboard` method queries `Pedido` + `HistorialEstadoPedido` directly (no pre-computed cache needed). The template uses a single Alpine.js component `estadisticasApp()` with four Chart.js instances destroyed and recreated on each data load.

**Tech Stack:** Flask, SQLAlchemy, Alpine.js 3.x, Tailwind CSS CDN, Chart.js 4.x CDN (already loaded in rendimiento.html — same pattern).

---

## Data Model Reference

| Model | Key fields used |
|-------|----------------|
| `Pedido` | `PedidoID`, `FechaCreacion (DateTime)`, `Estado (String)`, `Total (DECIMAL)`, `forma_pago (String)` |
| `HistorialEstadoPedido` | `pedido_id`, `estado_nuevo (String)`, `cambiado_en (DateTime)` |

State values from `states.py`:
- `EstadoPedido.EN_PREPARACION.value` → `'en_preparacion'`
- `EstadoPedido.PREPARADO.value` → `'preparado'`
- `EstadoPedido.EN_REPARTO.value` → `'en_reparto'`
- `EstadoPedido.ENTREGADO.value` → `'entregado'`
- `EstadoPedido.CANCELADO.value` → `'cancelado'`
- `EstadoPedido.REEMBOLSADO.value` → `'reembolsado'`

---

## File Map

| Action | File | What changes |
|--------|------|-------------|
| Modify | `managers/gestor_dashboard.py` | Add `estadisticas()` method (append to class) |
| Modify | `blueprints/dashboard.py` | Add 2 routes before the `# Write endpoints` block |
| Create | `templates/dashboard/estadisticas.html` | Full page with 4 Chart.js charts |
| Create | `tests/test_dashboard_sprint5.py` | New test file |

---

### Task 1: GestorDashboard — estadisticas()

**Files:**
- Modify: `managers/gestor_dashboard.py`
- Test: `tests/test_dashboard_sprint5.py` (create)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_dashboard_sprint5.py
from unittest.mock import patch, PropertyMock, MagicMock


# ── Task 1: Manager ──────────────────────────────────────────────────────────

def test_estadisticas_devuelve_claves_esperadas(app):
    """estadisticas() devuelve todas las claves requeridas."""
    from services import gestor_dashboard
    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            mock_q = mock_session.return_value.query.return_value
            mock_q.filter.return_value = mock_q
            mock_q.all.return_value = []

            result = gestor_dashboard.estadisticas()

            assert 'kpis' in result
            assert 'serie_pedidos_ingresos' in result
            assert 'distribucion_estados' in result
            assert 'forma_pago' in result
            assert 'serie_tiempos' in result


def test_estadisticas_kpis_tienen_campos_requeridos(app):
    """estadisticas() kpis contiene todos los campos esperados."""
    from services import gestor_dashboard
    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            mock_q = mock_session.return_value.query.return_value
            mock_q.filter.return_value = mock_q
            mock_q.all.return_value = []

            result = gestor_dashboard.estadisticas()
            kpis = result['kpis']

            assert 'ingresos' in kpis
            assert 'pedidos' in kpis
            assert 'entregados' in kpis
            assert 'cancelados' in kpis
            assert 'tasa_cancelacion_pct' in kpis
            assert 't_prep_min' in kpis
            assert 't_entrega_min' in kpis


def test_estadisticas_serie_vacia_si_no_hay_pedidos(app):
    """estadisticas() devuelve series con 0s cuando no hay pedidos."""
    from services import gestor_dashboard
    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            mock_q = mock_session.return_value.query.return_value
            mock_q.filter.return_value = mock_q
            mock_q.all.return_value = []

            result = gestor_dashboard.estadisticas()

            assert isinstance(result['serie_pedidos_ingresos'], list)
            assert isinstance(result['serie_tiempos'], list)
            # With default 7-day range, serie should have 7 entries
            assert len(result['serie_pedidos_ingresos']) == 7
            assert all(e['pedidos'] == 0 for e in result['serie_pedidos_ingresos'])


def test_estadisticas_acepta_granularidad_semana(app):
    """estadisticas() acepta granularidad='semana' sin error."""
    from services import gestor_dashboard
    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            mock_q = mock_session.return_value.query.return_value
            mock_q.filter.return_value = mock_q
            mock_q.all.return_value = []

            result = gestor_dashboard.estadisticas(
                desde='2026-01-01', hasta='2026-01-21', granularidad='semana'
            )
            assert 'serie_pedidos_ingresos' in result
            # 2026-01-01 (W01) → 2026-01-21 (W04) spans 4 ISO weeks
            assert len(result['serie_pedidos_ingresos']) == 4
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_dashboard_sprint5.py -v
```
Expected: `FAILED` — `AttributeError: ... estadisticas` or similar.

- [ ] **Step 3: Implement estadisticas() in GestorDashboard**

Append this method to the `GestorDashboard` class in `managers/gestor_dashboard.py` (after `rendimiento_empleado`):

```python
    def estadisticas(self, desde: str = None, hasta: str = None, granularidad: str = 'dia') -> dict:
        """Estadísticas de ventas y operación para el período dado.

        Args:
            desde:        Fecha ISO YYYY-MM-DD (default: hace 6 días)
            hasta:        Fecha ISO YYYY-MM-DD (default: hoy)
            granularidad: 'dia' | 'semana'

        Returns:
            {
              kpis: {ingresos, pedidos, entregados, cancelados,
                     tasa_cancelacion_pct, t_prep_min, t_entrega_min},
              serie_pedidos_ingresos: [{fecha, pedidos, ingresos}],
              distribucion_estados:   {estado: count, ...},
              forma_pago:             {online, efectivo, tarjeta},
              serie_tiempos:          [{fecha, t_prep, t_entrega}],
            }
        """
        hoy = datetime.utcnow().date()
        fecha_desde = datetime.strptime(desde, '%Y-%m-%d').date() if desde else hoy - timedelta(days=6)
        fecha_hasta = datetime.strptime(hasta, '%Y-%m-%d').date() if hasta else hoy

        # Clamp granularidad
        if granularidad not in ('dia', 'semana'):
            granularidad = 'dia'

        dt_desde = datetime.combine(fecha_desde, datetime.min.time())
        dt_hasta = datetime.combine(fecha_hasta, datetime.max.time())

        s = self.session
        pedidos = (
            s.query(Pedido)
            .filter(Pedido.FechaCreacion >= dt_desde, Pedido.FechaCreacion <= dt_hasta)
            .all()
        )

        # ── KPIs ─────────────────────────────────────────────────────────────
        total_pedidos = len(pedidos)
        entregados   = [p for p in pedidos if p.Estado == EstadoPedido.ENTREGADO.value]
        cancelados   = [p for p in pedidos if p.Estado in (
            EstadoPedido.CANCELADO.value, EstadoPedido.REEMBOLSADO.value
        )]
        ingresos      = sum(float(p.Total or 0) for p in entregados)
        tasa_cancelacion = (
            round(len(cancelados) / total_pedidos * 100, 1) if total_pedidos > 0 else None
        )

        # ── Tiempos via HistorialEstadoPedido ─────────────────────────────────
        pedido_ids = [p.PedidoID for p in pedidos]
        t_prep_sum = t_prep_cnt = t_entrega_sum = t_entrega_cnt = 0
        # day-level bucket: date_iso -> {prep_sum, prep_cnt, entrega_sum, entrega_cnt}
        tiempos_por_dia: dict[str, dict] = {}

        if pedido_ids:
            historial = (
                s.query(HistorialEstadoPedido)
                .filter(
                    HistorialEstadoPedido.pedido_id.in_(pedido_ids),
                    HistorialEstadoPedido.estado_nuevo.in_([
                        EstadoPedido.EN_PREPARACION.value,
                        EstadoPedido.PREPARADO.value,
                        EstadoPedido.EN_REPARTO.value,
                        EstadoPedido.ENTREGADO.value,
                    ])
                )
                .all()
            )
            # Group by pedido, keep earliest timestamp per state
            hist_by_pedido: dict[int, dict] = {}
            for h in sorted(historial, key=lambda x: x.cambiado_en):
                ts = hist_by_pedido.setdefault(h.pedido_id, {})
                ts.setdefault(h.estado_nuevo, h.cambiado_en)

            EN_PREP = EstadoPedido.EN_PREPARACION.value
            PREP    = EstadoPedido.PREPARADO.value
            EN_REP  = EstadoPedido.EN_REPARTO.value
            ENTR    = EstadoPedido.ENTREGADO.value

            for ts in hist_by_pedido.values():
                if EN_PREP in ts and PREP in ts:
                    mins = (ts[PREP] - ts[EN_PREP]).total_seconds() / 60
                    if mins >= 0:
                        t_prep_sum += mins
                        t_prep_cnt += 1
                        dk = ts[PREP].date().isoformat()
                        b = tiempos_por_dia.setdefault(dk, {'ps': 0, 'pc': 0, 'es': 0, 'ec': 0})
                        b['ps'] += mins
                        b['pc'] += 1
                if EN_REP in ts and ENTR in ts:
                    mins = (ts[ENTR] - ts[EN_REP]).total_seconds() / 60
                    if mins >= 0:
                        t_entrega_sum += mins
                        t_entrega_cnt += 1
                        dk = ts[ENTR].date().isoformat()
                        b = tiempos_por_dia.setdefault(dk, {'ps': 0, 'pc': 0, 'es': 0, 'ec': 0})
                        b['es'] += mins
                        b['ec'] += 1

        t_prep_min    = round(t_prep_sum    / t_prep_cnt,    1) if t_prep_cnt    > 0 else None
        t_entrega_min = round(t_entrega_sum / t_entrega_cnt, 1) if t_entrega_cnt > 0 else None

        # ── Distribución estados ──────────────────────────────────────────────
        _ESTADOS_DIST = [
            EstadoPedido.EN_PREPARACION.value, EstadoPedido.PREPARADO.value,
            EstadoPedido.EN_REPARTO.value,     EstadoPedido.ENTREGADO.value,
            EstadoPedido.CANCELADO.value,      EstadoPedido.REEMBOLSADO.value,
        ]
        distribucion_estados = {e: 0 for e in _ESTADOS_DIST}
        for p in pedidos:
            if p.Estado in distribucion_estados:
                distribucion_estados[p.Estado] += 1

        # ── Forma de pago ─────────────────────────────────────────────────────
        forma_pago = {'online': 0, 'efectivo': 0, 'tarjeta': 0}
        for p in pedidos:
            if p.forma_pago in forma_pago:
                forma_pago[p.forma_pago] += 1

        # ── Pedidos por fecha para series (day-level) ─────────────────────────
        pedidos_por_dia: dict[str, dict] = {}
        for p in pedidos:
            if p.FechaCreacion:
                dk = p.FechaCreacion.date().isoformat()
                b = pedidos_por_dia.setdefault(dk, {'pedidos': 0, 'ingresos': 0.0})
                b['pedidos'] += 1
                if p.Estado == EstadoPedido.ENTREGADO.value:
                    b['ingresos'] += float(p.Total or 0)

        # ── Build output series (apply granularidad) ──────────────────────────
        def _gen_keys():
            """Generate ordered unique series keys (always advances by 1 day)."""
            seen: set = set()
            d = fecha_desde
            while d <= fecha_hasta:
                if granularidad == 'semana':
                    iso = d.isocalendar()
                    key = f"{iso[0]}-W{iso[1]:02d}"
                    if key not in seen:
                        seen.add(key)
                        yield key
                else:
                    yield d.isoformat()
                d += timedelta(days=1)

        def _dias_in_key(key: str):
            """Return day ISOs that belong to a series key."""
            d = fecha_desde
            result = []
            while d <= fecha_hasta:
                if granularidad == 'semana':
                    iso = d.isocalendar()
                    if f"{iso[0]}-W{iso[1]:02d}" == key:
                        result.append(d.isoformat())
                    d += timedelta(days=1)
                else:
                    if d.isoformat() == key:
                        result.append(d.isoformat())
                    d += timedelta(days=1)
            return result

        serie_pedidos_ingresos = []
        serie_tiempos = []
        for key in _gen_keys():
            dias = _dias_in_key(key)
            p_total  = sum(pedidos_por_dia.get(dk, {}).get('pedidos',   0)   for dk in dias)
            i_total  = sum(pedidos_por_dia.get(dk, {}).get('ingresos',  0.0) for dk in dias)
            ps = sum(tiempos_por_dia.get(dk, {}).get('ps', 0) for dk in dias)
            pc = sum(tiempos_por_dia.get(dk, {}).get('pc', 0) for dk in dias)
            es = sum(tiempos_por_dia.get(dk, {}).get('es', 0) for dk in dias)
            ec = sum(tiempos_por_dia.get(dk, {}).get('ec', 0) for dk in dias)
            serie_pedidos_ingresos.append({
                'fecha':    key,
                'pedidos':  p_total,
                'ingresos': round(i_total, 2),
            })
            serie_tiempos.append({
                'fecha':      key,
                't_prep':     round(ps / pc, 1) if pc > 0 else None,
                't_entrega':  round(es / ec, 1) if ec > 0 else None,
            })

        return {
            'kpis': {
                'ingresos':             round(ingresos, 2),
                'pedidos':              total_pedidos,
                'entregados':           len(entregados),
                'cancelados':           len(cancelados),
                'tasa_cancelacion_pct': tasa_cancelacion,
                't_prep_min':           t_prep_min,
                't_entrega_min':        t_entrega_min,
            },
            'serie_pedidos_ingresos': serie_pedidos_ingresos,
            'distribucion_estados':   distribucion_estados,
            'forma_pago':             forma_pago,
            'serie_tiempos':          serie_tiempos,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_dashboard_sprint5.py::test_estadisticas_devuelve_claves_esperadas tests/test_dashboard_sprint5.py::test_estadisticas_kpis_tienen_campos_requeridos tests/test_dashboard_sprint5.py::test_estadisticas_serie_vacia_si_no_hay_pedidos tests/test_dashboard_sprint5.py::test_estadisticas_acepta_granularidad_semana -v
```
Expected: 4 PASSED.

- [ ] **Step 5: Run full test suite to check no regressions**

```bash
pytest -v --tb=short 2>&1 | tail -20
```
Expected: previous pass count + 4 new, 1 pre-existing failure unchanged.

- [ ] **Step 6: Commit (user runs this)**

```bash
git add managers/gestor_dashboard.py tests/test_dashboard_sprint5.py
git commit -m "feat: add estadisticas() to GestorDashboard with KPIs and date series"
```

---

### Task 2: Blueprint Routes

**Files:**
- Modify: `blueprints/dashboard.py` (insert before `# Write endpoints` block at line ~276)
- Test: `tests/test_dashboard_sprint5.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_dashboard_sprint5.py`:

```python
# ── Task 2: Routes ────────────────────────────────────────────────────────────

def test_estadisticas_html_devuelve_200(client):
    """GET /dashboard/estadisticas devuelve 200 para admin autenticado."""
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'
    resp = client.get('/dashboard/estadisticas')
    assert resp.status_code == 200
    assert b'estadistica' in resp.data.lower()


def test_estadisticas_html_requiere_auth(client):
    """GET /dashboard/estadisticas redirige sin sesión."""
    resp = client.get('/dashboard/estadisticas')
    assert resp.status_code in (302, 401)


def test_estadisticas_datos_json_devuelve_estructura(client):
    """GET /dashboard/estadisticas-datos devuelve estructura completa."""
    from unittest.mock import patch
    from services import gestor_dashboard

    fake = {
        'kpis': {
            'ingresos': 100.0, 'pedidos': 5, 'entregados': 4,
            'cancelados': 1, 'tasa_cancelacion_pct': 20.0,
            't_prep_min': 12.0, 't_entrega_min': 25.0,
        },
        'serie_pedidos_ingresos': [],
        'distribucion_estados': {},
        'forma_pago': {'online': 3, 'efectivo': 1, 'tarjeta': 1},
        'serie_tiempos': [],
    }

    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    with patch.object(gestor_dashboard, 'estadisticas', return_value=fake):
        resp = client.get('/dashboard/estadisticas-datos')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'kpis' in data
        assert 'serie_pedidos_ingresos' in data
        assert 'forma_pago' in data


def test_estadisticas_datos_pasa_parametros(client):
    """GET /dashboard/estadisticas-datos pasa desde, hasta y granularidad al manager."""
    from unittest.mock import patch
    from services import gestor_dashboard

    fake = {
        'kpis': {'ingresos': 0, 'pedidos': 0, 'entregados': 0,
                 'cancelados': 0, 'tasa_cancelacion_pct': None,
                 't_prep_min': None, 't_entrega_min': None},
        'serie_pedidos_ingresos': [], 'distribucion_estados': {},
        'forma_pago': {}, 'serie_tiempos': [],
    }

    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    with patch.object(
        gestor_dashboard, 'estadisticas', return_value=fake
    ) as mock_est:
        client.get('/dashboard/estadisticas-datos?desde=2026-01-01&hasta=2026-01-31&granularidad=semana')
        mock_est.assert_called_once_with(
            desde='2026-01-01', hasta='2026-01-31', granularidad='semana'
        )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_dashboard_sprint5.py -k "Task2 or html or json or datos" -v
```
Expected: FAILED — `404 Not Found` for `/dashboard/estadisticas`.

- [ ] **Step 3: Add routes to blueprints/dashboard.py**

Insert before the `# ---------------------------------------------------------------------------\n# Write endpoints` block (around line 276):

```python
# ---------------------------------------------------------------------------
# Estadísticas e Histórico
# ---------------------------------------------------------------------------

@blueprint_dashboard.route("/dashboard/estadisticas")
@requiere_rol('manager', 'admin')
def estadisticas():
    return render_template("dashboard/estadisticas.html")


@blueprint_dashboard.route("/dashboard/estadisticas-datos")
@requiere_rol('manager', 'admin')
def estadisticas_datos():
    desde       = request.args.get('desde') or None
    hasta       = request.args.get('hasta') or None
    granularidad = request.args.get('granularidad', 'dia')
    try:
        return _ok(gestor_dashboard.estadisticas(desde=desde, hasta=hasta, granularidad=granularidad))
    except Exception as e:
        logger.error("Error en /dashboard/estadisticas-datos: %s", e)
        return _err("Error interno", 500)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_dashboard_sprint5.py -k "estadisticas_html or estadisticas_datos" -v
```
Expected: 4 PASSED.

- [ ] **Step 5: Run full suite**

```bash
pytest -v --tb=short 2>&1 | tail -5
```

- [ ] **Step 6: Commit (user runs this)**

```bash
git add blueprints/dashboard.py tests/test_dashboard_sprint5.py
git commit -m "feat: add /dashboard/estadisticas routes and JSON API"
```

---

### Task 3: Template estadisticas.html

**Files:**
- Create: `templates/dashboard/estadisticas.html`
- Test: `tests/test_dashboard_sprint5.py` (append)

**Context:**
- Self-contained HTML (no base template), same `glass-panel` CSS variables as other dashboard templates.
- Chart.js 4.x via CDN: `https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js`
- Alpine.js 3.x via CDN: same URL as rendimiento.html
- Macros: `{% from 'macros/ui.html' import error_banner, loading_skeleton, empty_state %}`
- `error_banner` requires parent component to have `error` (string|null) and `cargar()`.
- Nav links needed: `/dashboard`, `/dashboard/monitor`, `/dashboard/historial`, `/dashboard/turnos`, `/dashboard/rendimiento`, `/dashboard/estadisticas`.

**Alpine component `estadisticasApp()`:**
```
periodo: 'semana'        // 'semana'|'mes'|'3meses'|'custom'
customDesde: ''          // YYYY-MM-DD string
customHasta: ''          // YYYY-MM-DD string
granularidad: 'dia'      // 'dia'|'semana'
cargando: false
error: null
kpis: null               // object or null until loaded
serieVolumen: []         // serie_pedidos_ingresos
distribEstados: {}       // distribucion_estados
formaPago: {}            // forma_pago
serieTiempos: []         // serie_tiempos
_charts: {}              // {volumen, estados, pago, tiempos} Chart instances
```

**Period → date computation in JS:**
```javascript
_fechas() {
  const hoy = new Date();
  const fmt = d => d.toISOString().slice(0, 10);
  const ago = n => { const d = new Date(hoy); d.setDate(d.getDate() - n); return d; };
  if (this.periodo === 'semana')  return { desde: fmt(ago(6)),  hasta: fmt(hoy), gran: 'dia' };
  if (this.periodo === 'mes')     return { desde: fmt(ago(29)), hasta: fmt(hoy), gran: 'dia' };
  if (this.periodo === '3meses')  return { desde: fmt(ago(89)), hasta: fmt(hoy), gran: 'semana' };
  return { desde: this.customDesde, hasta: this.customHasta, gran: this.granularidad };
},
```

**Chart colors (CSS variable–based inline hex, consistent with design system):**
```javascript
const BRAND   = '#6366f1';   // --brand
const SUCCESS = '#10b981';   // --success
const WARNING = '#f59e0b';   // --warning
const DANGER  = '#ef4444';   // --danger
const MUTED   = '#94a3b8';
```

**Chart rendering pattern** (same as rendimiento.html):
```javascript
async cargar() {
  this.cargando = true; this.error = null;
  try {
    const { desde, hasta, gran } = this._fechas();
    const url = `/dashboard/estadisticas-datos?desde=${desde}&hasta=${hasta}&granularidad=${gran}`;
    const r = await fetch(url);
    if (!r.ok) throw new Error(r.status);
    const d = await r.json();
    this.kpis          = d.kpis;
    this.serieVolumen  = d.serie_pedidos_ingresos;
    this.distribEstados = d.distribucion_estados;
    this.formaPago     = d.forma_pago;
    this.serieTiempos  = d.serie_tiempos;
    await this.$nextTick();
    this._renderCharts();
  } catch (e) {
    this.error = 'Error al cargar estadísticas. ¿Reintentar?';
  } finally {
    this.cargando = false;
  }
},
_renderCharts() {
  this._destroyCharts();
  this._chartVolumen();
  this._chartEstados();
  this._chartPago();
  this._chartTiempos();
},
_destroyCharts() {
  Object.values(this._charts).forEach(c => c && c.destroy());
  this._charts = {};
},
```

**Chart 1 — Línea: Pedidos + Ingresos (dual axis)**
```javascript
_chartVolumen() {
  const ctx = document.getElementById('chartVolumen');
  if (!ctx) return;
  const labels = this.serieVolumen.map(e => e.fecha);
  this._charts.volumen = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Pedidos', yAxisID: 'yPedidos',
          data: this.serieVolumen.map(e => e.pedidos),
          borderColor: BRAND, backgroundColor: BRAND + '22',
          tension: 0.3, fill: true,
        },
        {
          label: 'Ingresos €', yAxisID: 'yIngresos',
          data: this.serieVolumen.map(e => e.ingresos),
          borderColor: SUCCESS, backgroundColor: SUCCESS + '22',
          tension: 0.3, fill: false,
        },
      ],
    },
    options: {
      animation: { duration: 300 },
      plugins: { legend: { position: 'top' }, tooltip: { mode: 'index' } },
      scales: {
        yPedidos:  { type: 'linear', position: 'left',  title: { display: true, text: 'Pedidos' } },
        yIngresos: { type: 'linear', position: 'right', title: { display: true, text: 'Ingresos €' },
                     grid: { drawOnChartArea: false } },
      },
    },
  });
},
```

**Chart 2 — Barras horizontales: Distribución de estados**
```javascript
_chartEstados() {
  const ctx = document.getElementById('chartEstados');
  if (!ctx) return;
  const COLORES = {
    entregado: SUCCESS, en_reparto: '#f97316', preparado: '#6366f1',
    en_preparacion: '#3b82f6', cancelado: DANGER, reembolsado: '#8b5cf6',
  };
  const labels = Object.keys(this.distribEstados);
  this._charts.estados = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Pedidos',
        data: labels.map(k => this.distribEstados[k]),
        backgroundColor: labels.map(k => COLORES[k] || MUTED),
      }],
    },
    options: {
      indexAxis: 'y',
      animation: { duration: 300 },
      plugins: { legend: { display: false } },
      scales: { x: { beginAtZero: true, ticks: { precision: 0 } } },
    },
  });
},
```

**Chart 3 — Dona: Forma de pago**
```javascript
_chartPago() {
  const ctx = document.getElementById('chartPago');
  if (!ctx) return;
  this._charts.pago = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['Online', 'Efectivo', 'Tarjeta'],
      datasets: [{
        data: [
          this.formaPago.online   || 0,
          this.formaPago.efectivo || 0,
          this.formaPago.tarjeta  || 0,
        ],
        backgroundColor: [BRAND, SUCCESS, WARNING],
      }],
    },
    options: {
      animation: { duration: 300 },
      plugins: {
        legend: { position: 'bottom' },
        tooltip: { callbacks: {
          label: ctx => ` ${ctx.label}: ${ctx.raw} pedidos`
        }},
      },
    },
  });
},
```

**Chart 4 — Líneas: Tiempos medios (preparación + entrega)**
```javascript
_chartTiempos() {
  const ctx = document.getElementById('chartTiempos');
  if (!ctx) return;
  const labels = this.serieTiempos.map(e => e.fecha);
  this._charts.tiempos = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Preparación (min)',
          data: this.serieTiempos.map(e => e.t_prep),
          borderColor: BRAND, tension: 0.3, spanGaps: true,
        },
        {
          label: 'Entrega (min)',
          data: this.serieTiempos.map(e => e.t_entrega),
          borderColor: WARNING, tension: 0.3, spanGaps: true,
        },
      ],
    },
    options: {
      animation: { duration: 300 },
      plugins: { legend: { position: 'top' } },
      scales: { y: { beginAtZero: true, title: { display: true, text: 'Minutos' } } },
    },
  });
},
```

**KPI card format (6 cards in `grid-cols-2 sm:grid-cols-3`):**
```
ingresos         → "€ X.XX"
pedidos          → "X"
entregados       → "X"
cancelados       → "X  (tasa_cancelacion_pct%)"
t_prep_min       → "X min  (preparación)"
t_entrega_min    → "X min  (entrega)"
```

Null KPI values display as `—`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_dashboard_sprint5.py`:

```python
# ── Task 3: Template ──────────────────────────────────────────────────────────

def test_estadisticas_template_cargable_en_jinja2(app):
    """estadisticas.html se puede cargar en Jinja2 sin errores."""
    with app.app_context():
        template = app.jinja_env.get_template('dashboard/estadisticas.html')
        assert template is not None


def test_estadisticas_html_contiene_nav_links(client):
    """GET /dashboard/estadisticas incluye links de navegación."""
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'
    resp = client.get('/dashboard/estadisticas')
    assert resp.status_code == 200
    html = resp.data.decode()
    for ruta in ['/dashboard', '/dashboard/monitor', '/dashboard/historial',
                 '/dashboard/turnos', '/dashboard/rendimiento', '/dashboard/estadisticas']:
        assert ruta in html, f"Link {ruta} no encontrado en estadisticas.html"


def test_estadisticas_html_contiene_alpine_app(client):
    """GET /dashboard/estadisticas incluye x-data estadisticasApp()."""
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'
    resp = client.get('/dashboard/estadisticas')
    assert resp.status_code == 200
    assert b'estadisticasApp' in resp.data
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_dashboard_sprint5.py -k "template or nav_links or alpine" -v
```
Expected: FAILED — template not found.

- [ ] **Step 3: Create templates/dashboard/estadisticas.html**

Create the file. Follow this structure exactly:

```html
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Estadísticas — Panchi Ops</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <script src="https://cdn.tailwindcss.com"></script>
  <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
  {% from 'macros/ui.html' import error_banner, loading_skeleton, empty_state %}
  <style>
    :root {
      --bg: #f1f5f9; --panel: #ffffff; --panel-strong: #f8fafc;
      --line: #e2e8f0; --ink: #1e293b; --muted: #64748b;
      --brand: #6366f1; --brand-soft: #eef2ff;
      --warning: #f59e0b; --danger: #ef4444; --success: #10b981;
    }
    body { font-family: 'Manrope', sans-serif; background: var(--bg); color: var(--ink); }
    .glass-panel { background: var(--panel); border: 1px solid var(--line); border-radius: 1rem; }
    [x-cloak] { display: none !important; }
  </style>
</head>
<body x-data="estadisticasApp()" x-init="init()" x-cloak>

  <!-- ── Header nav ─────────────────────────────────────────────────────── -->
  <header class="bg-white border-b border-slate-200 sticky top-0 z-30">
    <div class="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
      <span class="font-extrabold text-lg tracking-tight text-indigo-600">PANCHI OPS</span>
      <nav class="flex flex-wrap gap-1 text-sm font-medium">
        <a href="/dashboard"              class="px-3 py-1.5 rounded-lg hover:bg-slate-100">Hoy</a>
        <a href="/dashboard/monitor"      class="px-3 py-1.5 rounded-lg hover:bg-slate-100">Monitor</a>
        <a href="/dashboard/historial"    class="px-3 py-1.5 rounded-lg hover:bg-slate-100">Historial</a>
        <a href="/dashboard/turnos"       class="px-3 py-1.5 rounded-lg hover:bg-slate-100">Turnos</a>
        <a href="/dashboard/rendimiento"  class="px-3 py-1.5 rounded-lg hover:bg-slate-100">Rendimiento</a>
        <a href="/dashboard/estadisticas" class="px-3 py-1.5 rounded-lg bg-indigo-50 text-indigo-700 font-semibold">Estadísticas</a>
      </nav>
    </div>
  </header>

  <main class="max-w-7xl mx-auto px-4 py-6 space-y-6">

    <!-- ── Title + period selector ──────────────────────────────────────── -->
    <div class="flex flex-wrap items-center justify-between gap-4">
      <h1 class="text-2xl font-bold">Estadísticas</h1>
      <div class="flex flex-wrap gap-2 items-center">
        <div class="flex rounded-lg border border-slate-200 overflow-hidden text-sm font-medium">
          <template x-for="p in [{k:'semana',l:'7 días'},{k:'mes',l:'30 días'},{k:'3meses',l:'3 meses'},{k:'custom',l:'Personalizado'}]" :key="p.k">
            <button
              @click="periodo = p.k; if(p.k !== 'custom') cargar()"
              :class="periodo === p.k ? 'bg-indigo-600 text-white' : 'bg-white text-slate-600 hover:bg-slate-50'"
              class="px-3 py-1.5 transition-colors"
              x-text="p.l"
            ></button>
          </template>
        </div>
        <!-- Custom date range -->
        <template x-if="periodo === 'custom'">
          <div class="flex items-center gap-2 text-sm">
            <input type="date" x-model="customDesde" class="border border-slate-200 rounded-lg px-2 py-1.5 text-sm">
            <span class="text-slate-400">→</span>
            <input type="date" x-model="customHasta" class="border border-slate-200 rounded-lg px-2 py-1.5 text-sm">
            <select x-model="granularidad" class="border border-slate-200 rounded-lg px-2 py-1.5 text-sm">
              <option value="dia">Por día</option>
              <option value="semana">Por semana</option>
            </select>
            <button @click="cargar()" class="px-3 py-1.5 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700">
              Aplicar
            </button>
          </div>
        </template>
      </div>
    </div>

    <!-- ── Error banner ──────────────────────────────────────────────────── -->
    {{ error_banner() }}

    <!-- ── Loading skeleton ─────────────────────────────────────────────── -->
    <template x-if="cargando && !kpis">
      {{ loading_skeleton(rows=3) }}
    </template>

    <!-- ── KPI grid ─────────────────────────────────────────────────────── -->
    <template x-if="kpis">
      <div class="grid grid-cols-2 sm:grid-cols-3 gap-4">
        <!-- Ingresos -->
        <div class="glass-panel p-4">
          <p class="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Ingresos</p>
          <p class="text-2xl font-extrabold" x-text="kpis.ingresos != null ? '€ ' + kpis.ingresos.toFixed(2) : '—'"></p>
        </div>
        <!-- Pedidos -->
        <div class="glass-panel p-4">
          <p class="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Pedidos</p>
          <p class="text-2xl font-extrabold" x-text="kpis.pedidos ?? '—'"></p>
        </div>
        <!-- Entregados -->
        <div class="glass-panel p-4">
          <p class="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Entregados</p>
          <p class="text-2xl font-extrabold text-emerald-600" x-text="kpis.entregados ?? '—'"></p>
        </div>
        <!-- Cancelados -->
        <div class="glass-panel p-4">
          <p class="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Cancelados</p>
          <p class="text-2xl font-extrabold text-red-500">
            <span x-text="kpis.cancelados ?? '—'"></span>
            <span x-show="kpis.tasa_cancelacion_pct != null" class="text-sm font-medium text-slate-400 ml-1">
              (<span x-text="kpis.tasa_cancelacion_pct"></span>%)
            </span>
          </p>
        </div>
        <!-- T. Preparación -->
        <div class="glass-panel p-4">
          <p class="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">T. Preparación</p>
          <p class="text-2xl font-extrabold">
            <span x-text="kpis.t_prep_min != null ? kpis.t_prep_min + ' min' : '—'"></span>
          </p>
        </div>
        <!-- T. Entrega -->
        <div class="glass-panel p-4">
          <p class="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">T. Entrega</p>
          <p class="text-2xl font-extrabold">
            <span x-text="kpis.t_entrega_min != null ? kpis.t_entrega_min + ' min' : '—'"></span>
          </p>
        </div>
      </div>
    </template>

    <!-- ── Chart row 1: Volumen ──────────────────────────────────────────── -->
    <div class="glass-panel p-4">
      <h2 class="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-4">Pedidos e Ingresos</h2>
      <div class="relative h-64">
        <canvas id="chartVolumen"></canvas>
        <template x-if="!cargando && serieVolumen.length === 0">
          {{ empty_state('📊', 'Sin datos', 'No hay datos para este período.') }}
        </template>
      </div>
    </div>

    <!-- ── Chart row 2: Estados + Pago ──────────────────────────────────── -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      <div class="glass-panel p-4">
        <h2 class="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-4">Distribución por Estado</h2>
        <div class="relative h-56">
          <canvas id="chartEstados"></canvas>
        </div>
      </div>
      <div class="glass-panel p-4">
        <h2 class="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-4">Forma de Pago</h2>
        <div class="relative h-56 flex items-center justify-center">
          <canvas id="chartPago" class="max-w-xs"></canvas>
        </div>
      </div>
    </div>

    <!-- ── Chart row 3: Tiempos ──────────────────────────────────────────── -->
    <div class="glass-panel p-4">
      <h2 class="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-4">Tiempos Medios de Operación</h2>
      <div class="relative h-64">
        <canvas id="chartTiempos"></canvas>
      </div>
    </div>

  </main>

  <script>
    function estadisticasApp() {
      const BRAND   = '#6366f1';
      const SUCCESS = '#10b981';
      const WARNING = '#f59e0b';
      const DANGER  = '#ef4444';
      const MUTED   = '#94a3b8';

      return {
        periodo:       'semana',
        customDesde:   '',
        customHasta:   '',
        granularidad:  'dia',
        cargando:      false,
        error:         null,
        kpis:          null,
        serieVolumen:  [],
        distribEstados: {},
        formaPago:     {},
        serieTiempos:  [],
        _charts:       {},

        init() {
          this.cargar();
        },

        _fechas() {
          const hoy = new Date();
          const fmt = d => d.toISOString().slice(0, 10);
          const ago = n => { const d = new Date(hoy); d.setDate(d.getDate() - n); return d; };
          if (this.periodo === 'semana')  return { desde: fmt(ago(6)),  hasta: fmt(hoy), gran: 'dia' };
          if (this.periodo === 'mes')     return { desde: fmt(ago(29)), hasta: fmt(hoy), gran: 'dia' };
          if (this.periodo === '3meses')  return { desde: fmt(ago(89)), hasta: fmt(hoy), gran: 'semana' };
          return { desde: this.customDesde, hasta: this.customHasta, gran: this.granularidad };
        },

        async cargar() {
          this.cargando = true;
          this.error = null;
          try {
            const { desde, hasta, gran } = this._fechas();
            if (!desde || !hasta) { this.error = 'Selecciona un rango de fechas válido.'; return; }
            const r = await fetch(`/dashboard/estadisticas-datos?desde=${desde}&hasta=${hasta}&granularidad=${gran}`);
            if (!r.ok) throw new Error(r.status);
            const d = await r.json();
            this.kpis           = d.kpis;
            this.serieVolumen   = d.serie_pedidos_ingresos;
            this.distribEstados = d.distribucion_estados;
            this.formaPago      = d.forma_pago;
            this.serieTiempos   = d.serie_tiempos;
            await this.$nextTick();
            this._renderCharts();
          } catch (e) {
            this.error = 'Error al cargar estadísticas. ¿Reintentar?';
          } finally {
            this.cargando = false;
          }
        },

        _renderCharts() {
          this._destroyCharts();
          this._chartVolumen();
          this._chartEstados();
          this._chartPago();
          this._chartTiempos();
        },

        _destroyCharts() {
          Object.values(this._charts).forEach(c => c && c.destroy());
          this._charts = {};
        },

        _chartVolumen() {
          const ctx = document.getElementById('chartVolumen');
          if (!ctx || !this.serieVolumen.length) return;
          this._charts.volumen = new Chart(ctx, {
            type: 'line',
            data: {
              labels: this.serieVolumen.map(e => e.fecha),
              datasets: [
                {
                  label: 'Pedidos', yAxisID: 'yPedidos',
                  data: this.serieVolumen.map(e => e.pedidos),
                  borderColor: BRAND, backgroundColor: BRAND + '22',
                  tension: 0.3, fill: true,
                },
                {
                  label: 'Ingresos €', yAxisID: 'yIngresos',
                  data: this.serieVolumen.map(e => e.ingresos),
                  borderColor: SUCCESS, backgroundColor: SUCCESS + '22',
                  tension: 0.3, fill: false,
                },
              ],
            },
            options: {
              animation: { duration: 300 },
              plugins: { legend: { position: 'top' }, tooltip: { mode: 'index', intersect: false } },
              scales: {
                yPedidos:  { type: 'linear', position: 'left',  title: { display: true, text: 'Pedidos' }, ticks: { precision: 0 } },
                yIngresos: { type: 'linear', position: 'right', title: { display: true, text: 'Ingresos €' },
                             grid: { drawOnChartArea: false } },
              },
            },
          });
        },

        _chartEstados() {
          const ctx = document.getElementById('chartEstados');
          if (!ctx) return;
          const COLORES = {
            entregado: SUCCESS, en_reparto: '#f97316', preparado: '#6366f1',
            en_preparacion: '#3b82f6', cancelado: DANGER, reembolsado: '#8b5cf6',
          };
          const labels = Object.keys(this.distribEstados);
          this._charts.estados = new Chart(ctx, {
            type: 'bar',
            data: {
              labels,
              datasets: [{
                label: 'Pedidos',
                data: labels.map(k => this.distribEstados[k]),
                backgroundColor: labels.map(k => COLORES[k] || MUTED),
              }],
            },
            options: {
              indexAxis: 'y',
              animation: { duration: 300 },
              plugins: { legend: { display: false } },
              scales: { x: { beginAtZero: true, ticks: { precision: 0 } } },
            },
          });
        },

        _chartPago() {
          const ctx = document.getElementById('chartPago');
          if (!ctx) return;
          this._charts.pago = new Chart(ctx, {
            type: 'doughnut',
            data: {
              labels: ['Online', 'Efectivo', 'Tarjeta'],
              datasets: [{
                data: [
                  this.formaPago.online   || 0,
                  this.formaPago.efectivo || 0,
                  this.formaPago.tarjeta  || 0,
                ],
                backgroundColor: [BRAND, SUCCESS, WARNING],
              }],
            },
            options: {
              animation: { duration: 300 },
              plugins: {
                legend: { position: 'bottom' },
                tooltip: { callbacks: { label: ctx => ` ${ctx.label}: ${ctx.raw} pedidos` } },
              },
            },
          });
        },

        _chartTiempos() {
          const ctx = document.getElementById('chartTiempos');
          if (!ctx || !this.serieTiempos.length) return;
          this._charts.tiempos = new Chart(ctx, {
            type: 'line',
            data: {
              labels: this.serieTiempos.map(e => e.fecha),
              datasets: [
                {
                  label: 'Preparación (min)',
                  data: this.serieTiempos.map(e => e.t_prep),
                  borderColor: BRAND, tension: 0.3, spanGaps: true,
                },
                {
                  label: 'Entrega (min)',
                  data: this.serieTiempos.map(e => e.t_entrega),
                  borderColor: WARNING, tension: 0.3, spanGaps: true,
                },
              ],
            },
            options: {
              animation: { duration: 300 },
              plugins: { legend: { position: 'top' } },
              scales: { y: { beginAtZero: true, title: { display: true, text: 'Minutos' } } },
            },
          });
        },
      };
    }
  </script>
</body>
</html>
```

- [ ] **Step 4: Run template tests**

```bash
pytest tests/test_dashboard_sprint5.py -k "template or nav_links or alpine" -v
```
Expected: 3 PASSED.

- [ ] **Step 5: Run full test suite**

```bash
pytest -v --tb=short 2>&1 | tail -5
```
Expected: all 11 new Sprint 5 tests pass (4 Task 1 + 4 Task 2 + 3 Task 3), 1 pre-existing failure unchanged.

- [ ] **Step 6: Commit (user runs this)**

```bash
git add templates/dashboard/estadisticas.html tests/test_dashboard_sprint5.py
git commit -m "feat: add /dashboard/estadisticas page with 4 Chart.js charts"
```

---

## Reviewer Checklist

After all three tasks pass tests:

**Spec compliance:**
- [ ] `/dashboard/estadisticas` renders 200 for manager/admin, 302 for unauthenticated
- [ ] `/dashboard/estadisticas-datos` returns `{kpis, serie_pedidos_ingresos, distribucion_estados, forma_pago, serie_tiempos}`
- [ ] KPIs: ingresos, pedidos, entregados, cancelados, tasa_cancelacion_pct, t_prep_min, t_entrega_min
- [ ] 4 Chart.js charts rendered: line (volumen), bar horizontal (estados), donut (pago), line (tiempos)
- [ ] Period selector: 7 días / 30 días / 3 meses / Personalizado
- [ ] Serie is 0-filled for missing dates (default 7 entries for semana)
- [ ] granularidad='semana' groups 3-week range into 3 entries

**Code quality:**
- [ ] Manager method uses `self.session` (not `db.session`)
- [ ] No f-strings in logger calls
- [ ] Charts destroyed before recreating (`_destroyCharts()`)
- [ ] Alpine `init()` calls `cargar()` (not `x-init` on element)
- [ ] Navigation links include all 6 dashboard pages
