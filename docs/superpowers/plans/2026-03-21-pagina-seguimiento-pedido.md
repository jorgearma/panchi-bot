# Página de seguimiento de pedido — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reemplazar la página estática `/pago_confirmado` por un tracker en tiempo real con timeline de estados, tarjeta de repartidor con WhatsApp y auto-refresco cada 15 segundos.

**Architecture:** Nuevo endpoint `GET /api/seguimiento/<id>` en `blueprints/api.py` devuelve estado y datos del reparto desde SQL. El template `ver_comandas.html` se reescribe completamente: renderiza los items estáticamente desde Redis y actualiza solo el bloque de estado/repartidor con polling JS cada 15s. Dos variables de entorno nuevas (`STORE_PHONE`, `STORE_ADDRESS`) exponen los datos del almacén.

**Tech Stack:** Flask, SQLAlchemy, Jinja2, JavaScript (vanilla fetch + setInterval), CSS tokens existentes en `static/css/styles.css`

**Spec:** `docs/superpowers/specs/2026-03-21-pagina-seguimiento-pedido-design.md`

---

## Mapa de archivos

| Archivo | Acción | Qué hace |
|---|---|---|
| `config.py` | Modificar | Añadir `STORE_PHONE`, `STORE_ADDRESS` |
| `blueprints/api.py` | Modificar | Nuevo endpoint `GET /api/seguimiento/<id>` |
| `blueprints/menu.py` | Modificar | Pasar `store_phone`, `store_address` al template |
| `templates/ver_comandas.html` | Reescritura | Tracker completo con polling JS |
| `.env.example` | Modificar | Documentar las dos nuevas variables |
| `tests/test_seguimiento.py` | Crear | Tests del endpoint de seguimiento |

---

## Task 1: Variables de entorno del almacén

**Files:**
- Modify: `config.py`
- Modify: `.env.example`

- [ ] **Step 1: Añadir las dos variables a `config.py`**

Al final del fichero, tras la línea de `CUSTOMER_SUPPORT_PHONE`:

```python
# Almacén — se muestran al cliente en la página de seguimiento
STORE_PHONE: str = os.environ.get("STORE_PHONE", "")
STORE_ADDRESS: str = os.environ.get("STORE_ADDRESS", "")
```

- [ ] **Step 2: Documentar en `.env.example`**

Añadir al final del fichero (o junto a `CUSTOMER_SUPPORT_PHONE` si ya existe esa sección):

```bash
# Almacén (mostrado al cliente en la página de seguimiento)
STORE_PHONE=612345678
STORE_ADDRESS=C/ Ejemplo 12, Madrid
```

- [ ] **Step 3: Verificar que el módulo carga sin errores**

```bash
python -c "import config; print(config.STORE_PHONE, config.STORE_ADDRESS)"
```

Salida esperada: dos cadenas (vacías si no hay `.env` configurado, sin excepción).

- [ ] **Step 4: Commit**

```bash
git add config.py .env.example
git commit -m "feat: añadir STORE_PHONE y STORE_ADDRESS a config"
```

---

## Task 2: Endpoint `GET /api/seguimiento/<pedido_db_id>`

**Files:**
- Modify: `blueprints/api.py`
- Create: `tests/test_seguimiento.py`

### Contexto del endpoint

El endpoint consulta `Pedido` por `PedidoID` y, si existe reparto, extrae nombre/teléfono del repartidor y la hora estimada. Devuelve solo datos necesarios para el tracker — sin datos personales del cliente.

- [ ] **Step 1: Escribir los tests (fichero nuevo)**

Crear `tests/test_seguimiento.py`:

```python
"""
Tests para GET /api/seguimiento/<pedido_db_id>
"""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime


def make_pedido(estado, forma_pago="online", con_reparto=False, con_repartidor=False):
    pedido = MagicMock()
    pedido.PedidoID = 2045
    pedido.Estado = estado
    pedido.forma_pago = forma_pago
    pedido.DireccionEntrega = "Calle Mayor 5, Madrid"

    if con_reparto:
        reparto = MagicMock()
        reparto.estado = "en_camino"
        reparto.hora_salida = datetime(2026, 3, 21, 14, 52)
        reparto.hora_estimada_entrega = datetime(2026, 3, 21, 15, 5)
        if con_repartidor:
            repartidor = MagicMock()
            repartidor.Nombre = "Carlos"
            repartidor.Apellido = "Moreno"
            repartidor.Telefono = "612345678"
            reparto.repartidor = repartidor
        else:
            reparto.repartidor = None
        pedido.reparto = reparto
    else:
        pedido.reparto = None

    return pedido


class TestSeguimientoEndpoint:

    def test_pedido_no_encontrado_devuelve_404(self, client):
        with patch("blueprints.api.gestor_pedidos") as mock_gp:
            mock_gp.obtener_pedido.return_value = None
            resp = client.get("/api/seguimiento/9999")
        assert resp.status_code == 404
        assert "error" in resp.get_json()

    def test_pedido_sin_reparto(self, client):
        pedido = make_pedido("EN_PREPARACION", con_reparto=False)
        with patch("blueprints.api.gestor_pedidos") as mock_gp:
            mock_gp.obtener_pedido.return_value = pedido
            resp = client.get("/api/seguimiento/2045")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["estado"] == "EN_PREPARACION"
        assert data["reparto"] is None

    def test_pedido_en_reparto_con_repartidor(self, client):
        pedido = make_pedido("EN_REPARTO", con_reparto=True, con_repartidor=True)
        with patch("blueprints.api.gestor_pedidos") as mock_gp:
            mock_gp.obtener_pedido.return_value = pedido
            resp = client.get("/api/seguimiento/2045")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["estado"] == "EN_REPARTO"
        reparto = data["reparto"]
        assert reparto["repartidor_nombre"] == "Carlos Moreno"
        assert reparto["repartidor_telefono"] == "612345678"
        assert reparto["hora_estimada_entrega"] == "15:05"
        assert reparto["hora_salida"] == "14:52"
        assert reparto["calle_destino"] == "Calle Mayor 5, Madrid"

    def test_pedido_con_reparto_sin_repartidor_asignado(self, client):
        pedido = make_pedido("PREPARADO", con_reparto=True, con_repartidor=False)
        with patch("blueprints.api.gestor_pedidos") as mock_gp:
            mock_gp.obtener_pedido.return_value = pedido
            resp = client.get("/api/seguimiento/2045")
        assert resp.status_code == 200
        data = resp.get_json()
        reparto = data["reparto"]
        assert reparto["repartidor_nombre"] is None
        assert reparto["repartidor_telefono"] is None

    def test_pedido_entregado(self, client):
        pedido = make_pedido("ENTREGADO", con_reparto=True, con_repartidor=True)
        with patch("blueprints.api.gestor_pedidos") as mock_gp:
            mock_gp.obtener_pedido.return_value = pedido
            resp = client.get("/api/seguimiento/2045")
        assert resp.status_code == 200
        assert resp.get_json()["estado"] == "ENTREGADO"

    def test_respuesta_incluye_forma_pago(self, client):
        pedido = make_pedido("EN_PREPARACION", forma_pago="efectivo")
        with patch("blueprints.api.gestor_pedidos") as mock_gp:
            mock_gp.obtener_pedido.return_value = pedido
            resp = client.get("/api/seguimiento/2045")
        assert resp.get_json()["forma_pago"] == "efectivo"
```

- [ ] **Step 2: Ejecutar tests — verificar que FALLAN**

```bash
pytest tests/test_seguimiento.py -v
```

Salida esperada: todos fallan con `404` (ruta no existe aún).

- [ ] **Step 3: Implementar el endpoint en `blueprints/api.py`**

Añadir al final del fichero (antes del EOF, tras el último route):

```python
@blueprint_api.route('/api/seguimiento/<int:pedido_db_id>', methods=['GET'])
def seguimiento_pedido(pedido_db_id):
    pedido = gestor_pedidos.obtener_pedido(pedido_db_id)
    if not pedido:
        return jsonify({"error": "Pedido no encontrado"}), 404

    reparto_data = None
    if pedido.reparto:
        r = pedido.reparto
        repartidor_nombre = None
        repartidor_telefono = None
        if r.repartidor:
            repartidor_nombre = f"{r.repartidor.Nombre} {r.repartidor.Apellido}"
            repartidor_telefono = r.repartidor.Telefono
        reparto_data = {
            "estado": r.estado,
            "hora_salida": r.hora_salida.strftime("%H:%M") if r.hora_salida else None,
            "hora_estimada_entrega": r.hora_estimada_entrega.strftime("%H:%M") if r.hora_estimada_entrega else None,
            "repartidor_nombre": repartidor_nombre,
            "repartidor_telefono": repartidor_telefono,
            "calle_destino": pedido.DireccionEntrega,
        }

    logger.debug("Seguimiento pedido %s: estado=%s", pedido_db_id, pedido.Estado)
    return jsonify({
        "estado": pedido.Estado,
        "forma_pago": pedido.forma_pago,
        "reparto": reparto_data,
    })
```

- [ ] **Step 4: Ejecutar tests — verificar que PASAN**

```bash
pytest tests/test_seguimiento.py -v
```

Salida esperada: todos los tests en verde.

- [ ] **Step 5: Ejecutar suite completa — sin regresiones**

```bash
pytest -v --tb=short
```

Los 3 tests pre-existentes de `TestWebhookMonei` pueden fallar — son conocidos. El resto debe pasar.

- [ ] **Step 6: Commit**

```bash
git add blueprints/api.py tests/test_seguimiento.py
git commit -m "feat: añadir endpoint GET /api/seguimiento/<id>"
```

---

## Task 3: Pasar datos del almacén al template

**Files:**
- Modify: `blueprints/menu.py`

- [ ] **Step 1: Añadir `store_phone` y `store_address` al `render_template` de `/pago_confirmado`**

En `blueprints/menu.py`, localizar la función `mostrar_confirmacion_depago` (línea ~138). Añadir los dos nuevos parámetros al `render_template`:

```python
# Añadir import al inicio del fichero si no está ya:
import config

# En render_template, añadir tras public_url=...:
        store_phone=config.STORE_PHONE or "",
        store_address=config.STORE_ADDRESS or "",
```

El bloque completo queda:

```python
return render_template(
    "ver_comandas.html",
    name=pedido["name"],
    userID=pedido["userID"],
    token=pedido["token"],
    numero=pedido["numero"],
    direccion=pedido["direccion"],
    calle=_extraer_calle(pedido["direccion"]),
    total=pedido["total"],
    productos=pedido["productos"],
    pedidoID=pedido["pedidoID"],
    public_url=config.PUBLIC_URL or "",
    store_phone=config.STORE_PHONE or "",
    store_address=config.STORE_ADDRESS or "",
)
```

- [ ] **Step 2: Verificar que el módulo importa sin errores**

```bash
python -c "from blueprints.menu import blueprint_menu; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add blueprints/menu.py
git commit -m "feat: pasar store_phone y store_address al template de seguimiento"
```

---

## Task 4: Reescribir `templates/ver_comandas.html`

**Files:**
- Rewrite: `templates/ver_comandas.html`

Este es el cambio visual principal. El template usa los tokens de `static/css/styles.css` (ya incluido) y añade estilos propios en un `<style>` inline para no contaminar el CSS global.

### Lógica de estados en Jinja2

El template recibe el estado inicial en el render, y el JS actualiza el DOM cuando el polling devuelve un estado nuevo. Para el render inicial, el estado viene del JSON de Redis — que puede no tener `Estado` si es un pedido recién creado. El JS siempre consulta el endpoint para obtener el estado real de BD.

### Tabla de estados → clases CSS y textos

| `estado` JS | `data-status` | Hero icon | Hero title |
|---|---|---|---|
| `PAGADO`, `CONFIRMANDO_PAGO`, `CONTRA_REEMBOLSO` | `receiving` | 📦 | Pedido recibido, preparando… |
| `EN_PREPARACION` | `preparing` | 📦 | Preparando en almacén |
| `PREPARADO` | `ready` | 📦 | Listo, asignando repartidor |
| `EN_REPARTO` | `on_the_way` | 🏍 | ¡Tu pedido viene de camino! |
| `ENTREGADO` | `delivered` | ✅ | ¡Pedido entregado! |
| `CANCELADO` | `cancelled` | ❌ | Pedido cancelado |
| `REEMBOLSADO` | `refunded` | 💸 | Pedido reembolsado |
| (cualquier otro) | `receiving` | 📦 | Procesando tu pedido… |

- [ ] **Step 1: Reemplazar `templates/ver_comandas.html` con el nuevo template**

```html
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Seguimiento de pedido — Panchi Bot</title>
  <link rel="stylesheet" href="/static/css/styles.css">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Manrope:wght@700;800&display=swap" rel="stylesheet">
  <style>
    /* ── Status hero ── */
    .status-hero {
      background: var(--surface);
      padding: 20px 16px 16px;
      text-align: center;
      border-bottom: 1px solid var(--border);
    }
    .status-hero[data-status="delivered"] { background: #f0fdf4; border-bottom-color: #bbf7d0; }
    .status-hero[data-status="cancelled"] { background: #fef2f2; border-bottom-color: #fecaca; }
    .status-hero[data-status="refunded"]  { background: #f9fafb; border-bottom-color: var(--border); }

    #status-icon  { font-size: 40px; margin-bottom: 8px; }
    #status-title {
      font-size: 17px; font-weight: 700; color: var(--text);
      font-family: 'Manrope', sans-serif;
    }
    .status-hero[data-status="delivered"] #status-title { color: #15803d; }
    .status-hero[data-status="cancelled"] #status-title { color: var(--danger); }
    #status-sub   { font-size: 13px; color: var(--text-muted); margin-top: 4px; }
    .order-ref {
      display: inline-block; margin-top: 8px;
      background: var(--bg); border-radius: 20px;
      padding: 3px 12px; font-size: 12px; color: var(--text-muted);
      border: 1px solid var(--border);
    }

    /* ── Timeline ── */
    .tracker-section {
      background: var(--surface);
      padding: 16px 16px 4px;
      margin-top: 10px;
    }
    .tl-item { display: flex; align-items: flex-start; gap: 12px; }
    .tl-left { display: flex; flex-direction: column; align-items: center; flex-shrink: 0; }
    .tl-dot {
      width: 28px; height: 28px; border-radius: 50%;
      display: flex; align-items: center; justify-content: center;
      font-size: 12px; font-weight: 700; flex-shrink: 0;
      background: var(--border); color: var(--text-muted);
      transition: background 0.3s, box-shadow 0.3s;
    }
    .tl-dot.done    { background: var(--success); color: #fff; }
    .tl-dot.active  { background: var(--primary); color: #fff; box-shadow: 0 0 0 4px rgba(255,107,53,.18); }
    .tl-line { width: 2px; height: 26px; margin: 3px 0; background: var(--border); transition: background 0.3s; }
    .tl-line.done { background: var(--success); }
    .tl-body { padding-bottom: 18px; }
    .tl-label {
      font-size: 14px; font-weight: 600; color: var(--text-muted);
      padding-top: 4px; transition: color 0.3s;
    }
    .tl-label.active  { color: var(--primary); }
    .tl-label.done    { color: var(--text); }
    .tl-time { font-size: 12px; color: var(--text-muted); margin-top: 2px; }

    /* ── Tarjeta repartidor ── */
    .rep-card {
      margin: 10px 16px 0;
      background: var(--surface); border: 1px solid var(--border);
      border-radius: var(--radius); box-shadow: var(--shadow);
      padding: 12px 14px; display: flex; align-items: center; gap: 12px;
    }
    .rep-pending {
      margin: 10px 16px 0;
      background: #FFF8F5; border: 1px solid #FFD5C2;
      border-radius: var(--radius); padding: 12px 14px;
      font-size: 13px; color: #92400e; text-align: center;
    }
    .rep-avatar {
      width: 42px; height: 42px; border-radius: 50%;
      background: var(--primary); color: #fff;
      display: flex; align-items: center; justify-content: center;
      font-size: 18px; flex-shrink: 0;
    }
    .rep-info { flex: 1; min-width: 0; }
    .rep-name { font-size: 14px; font-weight: 700; color: var(--text); }
    .rep-role { font-size: 12px; color: var(--text-muted); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .wa-btn {
      background: #25D366; color: #fff; border: none;
      border-radius: var(--radius-sm); padding: 9px 11px;
      cursor: pointer; display: flex; align-items: center; justify-content: center;
      flex-shrink: 0; text-decoration: none;
    }
    .wa-btn svg { width: 22px; height: 22px; fill: #fff; }

    /* ── Secciones ── */
    .section-title {
      font-size: 11px; font-weight: 700; color: var(--text-muted);
      text-transform: uppercase; letter-spacing: .06em;
      padding: 14px 16px 8px;
    }

    /* ── Items pedido ── */
    .items-card {
      background: var(--surface); margin: 0 16px;
      border-radius: var(--radius); box-shadow: var(--shadow); overflow: hidden;
    }
    .item-row {
      display: flex; justify-content: space-between; align-items: center;
      padding: 11px 16px; border-bottom: 1px solid var(--border); gap: 10px;
    }
    .item-row:last-child { border-bottom: none; }
    .item-left { flex: 1; }
    .item-name { font-size: 13px; font-weight: 600; color: var(--text); }
    .item-total-row {
      display: flex; justify-content: space-between; align-items: center;
      padding: 12px 16px; background: var(--bg);
      border-top: 2px solid var(--border);
      font-weight: 700; font-size: 15px;
    }
    .item-total-val { color: var(--primary); }

    /* ── Info almacén ── */
    .store-card {
      background: var(--surface); margin: 0 16px;
      border-radius: var(--radius); box-shadow: var(--shadow); overflow: hidden;
    }
    .store-row {
      display: flex; align-items: center; gap: 10px;
      padding: 11px 16px; border-bottom: 1px solid var(--border);
      font-size: 13px; color: var(--text-muted);
    }
    .store-row:last-child { border-bottom: none; }

    /* ── Refresh bar ── */
    .refresh-bar {
      display: flex; align-items: center; justify-content: center; gap: 6px;
      padding: 12px 16px 20px; font-size: 11px; color: var(--text-muted);
    }
    .refresh-dot {
      width: 6px; height: 6px; border-radius: 50%;
      background: var(--primary); animation: pulse 1.5s infinite;
    }
    @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }

    .hidden { display: none !important; }
  </style>
</head>
<body>

  <!-- Header (idéntico al resto de la web) -->
  <header class="page-header">
    <div class="header-avatar">{{ name.split()[0] }}</div>
    <div class="header-address">
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
           fill="none" stroke="currentColor" stroke-width="2.5"
           stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/>
        <circle cx="12" cy="10" r="3"/>
      </svg>
      <span>{{ calle }}</span>
    </div>
    <span class="header-badge">Envío gratis</span>
  </header>

  <!-- Status hero (actualizado por JS) -->
  <div class="status-hero" id="status-hero" data-status="receiving">
    <div id="status-icon">📦</div>
    <div id="status-title">Pedido recibido, preparando…</div>
    <div id="status-sub" class="status-sub"></div>
    <div class="order-ref">Pedido #{{ pedidoID }}</div>
  </div>

  <!-- Timeline (actualizado por JS) -->
  <div class="tracker-section" id="tracker-section">
    <!-- Paso 1: Recibido -->
    <div class="tl-item">
      <div class="tl-left">
        <div class="tl-dot" id="dot-1">○</div>
        <div class="tl-line" id="line-1"></div>
      </div>
      <div class="tl-body">
        <div class="tl-label" id="label-1">Pedido recibido</div>
        <div class="tl-time" id="time-1"></div>
      </div>
    </div>
    <!-- Paso 2: Preparando -->
    <div class="tl-item">
      <div class="tl-left">
        <div class="tl-dot" id="dot-2">○</div>
        <div class="tl-line" id="line-2"></div>
      </div>
      <div class="tl-body">
        <div class="tl-label" id="label-2">Preparando en almacén</div>
        <div class="tl-time" id="time-2"></div>
      </div>
    </div>
    <!-- Paso 3: En camino -->
    <div class="tl-item">
      <div class="tl-left">
        <div class="tl-dot" id="dot-3">○</div>
        <div class="tl-line" id="line-3"></div>
      </div>
      <div class="tl-body">
        <div class="tl-label" id="label-3">En camino</div>
        <div class="tl-time" id="time-3"></div>
      </div>
    </div>
    <!-- Paso 4: Entregado -->
    <div class="tl-item">
      <div class="tl-left">
        <div class="tl-dot" id="dot-4">○</div>
      </div>
      <div class="tl-body">
        <div class="tl-label" id="label-4">Entregado</div>
        <div class="tl-time" id="time-4"></div>
      </div>
    </div>
  </div>

  <!-- Tarjeta repartidor (actualizada por JS) -->
  <div id="rep-pending" class="rep-pending">
    🏍 Se asignará un repartidor cuando el pedido esté listo
  </div>
  <div id="rep-card" class="rep-card hidden">
    <div class="rep-avatar">👤</div>
    <div class="rep-info">
      <div class="rep-name" id="rep-name"></div>
      <div class="rep-role" id="rep-role"></div>
    </div>
    <a id="rep-wa" class="wa-btn" href="#" target="_blank" title="Contactar por WhatsApp">
      <svg viewBox="0 0 24 24"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347z"/><path d="M12 0C5.373 0 0 5.373 0 12c0 2.126.554 4.118 1.523 5.847L.057 23.882a.5.5 0 00.611.611l6.063-1.463A11.945 11.945 0 0012 24c6.627 0 12-5.373 12-12S18.627 0 12 0zm0 21.9a9.884 9.884 0 01-5.031-1.378l-.36-.214-3.733.901.924-3.713-.234-.375A9.855 9.855 0 012.1 12C2.1 6.533 6.533 2.1 12 2.1c5.467 0 9.9 4.433 9.9 9.9 0 5.467-4.433 9.9-9.9 9.9z"/></svg>
    </a>
  </div>

  <!-- Items del pedido (estáticos) -->
  <div class="section-title">Tu pedido</div>
  <div class="items-card">
    {% for producto in productos %}
    <div class="item-row">
      <div class="item-left">
        <div class="item-name">{{ producto.nombre }}</div>
        <span class="order-item-qty">x{{ producto.cantidad }}</span>
      </div>
      <span class="order-item-price">{{ producto.precio }} €</span>
    </div>
    {% endfor %}
    <div class="item-total-row">
      <span>Total</span>
      <span class="item-total-val">{{ total }} €</span>
    </div>
  </div>

  <!-- Info almacén -->
  {% if store_phone or store_address %}
  <div class="section-title">Almacén</div>
  <div class="store-card">
    {% if store_phone %}
    <div class="store-row">📞 {{ store_phone }}</div>
    {% endif %}
    {% if store_address %}
    <div class="store-row">📍 {{ store_address }}</div>
    {% endif %}
  </div>
  {% endif %}

  <!-- Refresh bar -->
  <div class="refresh-bar" id="refresh-bar">
    <div class="refresh-dot"></div>
    <span id="refresh-label">Actualizando…</span>
  </div>

  <script>
    const PEDIDO_ID = {{ pedidoID }};
    const REFRESH_INTERVAL = 15;
    const TERMINAL_STATES = ["ENTREGADO", "CANCELADO", "REEMBOLSADO"];

    // Configuración de estados: icono, título, subtítulo, data-status, paso activo (1-4 o null)
    const STATE_CONFIG = {
      "PAGADO":             { icon: "📦", title: "Pedido recibido, preparando…", sub: "", status: "receiving",  step: 1 },
      "CONFIRMANDO_PAGO":   { icon: "📦", title: "Pedido recibido, preparando…", sub: "", status: "receiving",  step: 1 },
      "CONTRA_REEMBOLSO":   { icon: "📦", title: "Pedido recibido, preparando…", sub: "", status: "receiving",  step: 1 },
      "EN_PREPARACION":     { icon: "📦", title: "Preparando en almacén",         sub: "~15 min estimados",      status: "preparing", step: 2 },
      "PREPARADO":          { icon: "📦", title: "Listo, asignando repartidor",   sub: "",                      status: "ready",     step: 2 },
      "EN_REPARTO":         { icon: "🏍", title: "¡Tu pedido viene de camino!",   sub: "",                      status: "on_the_way",step: 3 },
      "ENTREGADO":          { icon: "✅", title: "¡Pedido entregado!",            sub: "Gracias por tu pedido", status: "delivered", step: 4 },
      "CANCELADO":          { icon: "❌", title: "Pedido cancelado",              sub: "Contacta con el almacén si tienes dudas", status: "cancelled", step: null },
      "REEMBOLSADO":        { icon: "💸", title: "Pedido reembolsado",            sub: "El importe será devuelto en breve",        status: "refunded",  step: null },
    };
    const DEFAULT_CONFIG = { icon: "📦", title: "Procesando tu pedido…", sub: "", status: "receiving", step: 1 };

    function applyStatus(data) {
      const cfg = STATE_CONFIG[data.estado] || DEFAULT_CONFIG;

      // Hero
      const hero = document.getElementById("status-hero");
      document.getElementById("status-icon").textContent  = cfg.icon;
      document.getElementById("status-title").textContent = cfg.title;
      document.getElementById("status-sub").textContent   = cfg.sub;
      hero.setAttribute("data-status", cfg.status);

      // Timeline
      const tracker = document.getElementById("tracker-section");
      if (cfg.step === null) {
        tracker.classList.add("hidden");
      } else {
        tracker.classList.remove("hidden");
        for (let i = 1; i <= 4; i++) {
          const dot   = document.getElementById("dot-" + i);
          const line  = document.getElementById("line-" + i);
          const label = document.getElementById("label-" + i);
          dot.className   = "tl-dot";
          label.className = "tl-label";
          if (line) line.className = "tl-line";

          if (i < cfg.step) {
            dot.className   += " done"; dot.textContent = "✓";
            label.className += " done";
            if (line) line.className += " done";
          } else if (i === cfg.step) {
            dot.className   += " active"; dot.textContent = "●";
            label.className += " active";
          } else {
            dot.textContent = "○";
          }
        }
      }

      // Reparto / repartidor
      const repPending = document.getElementById("rep-pending");
      const repCard    = document.getElementById("rep-card");

      if (data.reparto && data.reparto.repartidor_nombre) {
        repPending.classList.add("hidden");
        repCard.classList.remove("hidden");
        document.getElementById("rep-name").textContent = data.reparto.repartidor_nombre;
        document.getElementById("rep-role").textContent = "🏍 En camino a " + data.reparto.calle_destino;
        const waLink = document.getElementById("rep-wa");
        if (data.reparto.repartidor_telefono) {
          waLink.href = "https://wa.me/34" + data.reparto.repartidor_telefono.replace(/\D/g, "");
          waLink.classList.remove("hidden");
        } else {
          waLink.classList.add("hidden");
        }
        if (data.reparto.hora_estimada_entrega) {
          document.getElementById("status-sub").textContent = "Entrega estimada a las " + data.reparto.hora_estimada_entrega;
        }
      } else {
        if (cfg.step !== null && cfg.step < 3) {
          repPending.classList.remove("hidden");
        } else {
          repPending.classList.add("hidden");
        }
        repCard.classList.add("hidden");
      }

      // Detener polling en estados terminales
      if (TERMINAL_STATES.includes(data.estado)) {
        stopPolling();
      }
    }

    // ── Polling ──
    let countdown = REFRESH_INTERVAL;
    let timer = null;

    function poll() {
      fetch("/api/seguimiento/" + PEDIDO_ID)
        .then(function(r) { if (r.ok) return r.json(); })
        .then(function(data) { if (data) applyStatus(data); })
        .catch(function() { /* error de red: reintentar en el siguiente ciclo */ });
    }

    function tick() {
      countdown--;
      const label = document.getElementById("refresh-label");
      if (label) label.textContent = countdown > 0
        ? "Actualizando en " + countdown + "s…"
        : "Actualizando…";
      if (countdown <= 0) {
        countdown = REFRESH_INTERVAL;
        poll();
      }
    }

    function stopPolling() {
      if (timer) { clearInterval(timer); timer = null; }
      const bar = document.getElementById("refresh-bar");
      if (bar) bar.classList.add("hidden");
    }

    // Arrancar: primera consulta inmediata + intervalo
    poll();
    timer = setInterval(tick, 1000);
  </script>

</body>
</html>
```

- [ ] **Step 2: Verificar visualmente con el servidor de desarrollo**

```bash
python main.py
```

Abrir una URL de prueba (necesita un pedidoID válido en BD). Si no hay BD disponible, verificar al menos que la página carga sin error 500 con un ID inexistente (`/pago_confirmado?pedido_id=test` debería devolver 404 del template, que es el comportamiento actual cuando el Redis key no existe).

- [ ] **Step 3: Commit**

```bash
git add templates/ver_comandas.html
git commit -m "feat: reescribir ver_comandas.html como tracker de pedido en tiempo real"
```

---

## Task 5: Verificación final y tests

- [ ] **Step 1: Ejecutar suite completa**

```bash
pytest -v --tb=short
```

Los únicos fallos permitidos son los 3 pre-existentes de `TestWebhookMonei`.

- [ ] **Step 2: Commit final si todo está limpio**

```bash
git add -A
git status  # verificar que no hay ficheros indeseados
git commit -m "feat: página de seguimiento de pedido completa"
```
