# Confirmación de Pago — Rediseño Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rediseñar `confirmacion_pago.html` con nueva cabecera, artículos claros, campo de notas, animación de tiempo estimado y modales de confirmación de pago; persistir el campo `notas` hasta la BD.

**Architecture:** Cambios en capas de abajo hacia arriba: modelo → controlador → blueprint → template. Cada capa se testea antes de tocar la siguiente. El template es la última pieza y no requiere tests automatizados (se verifica manualmente en el navegador).

**Tech Stack:** Python 3, SQLAlchemy 2.x, Flask, Jinja2, Vanilla JS, CSS custom properties (ya definidas en `static/css/styles.css`).

---

## Mapa de archivos

| Archivo | Tipo | Cambio |
|---------|------|--------|
| `models.py` | Modificar | Añadir `Notas = Column(String(300), nullable=True)` a clase `Pedido` |
| `controllers/pago.py` | Modificar | Añadir param `notas: str = ""` a `iniciar_pago()` e `iniciar_pago_efectivo()`; asignar `pedido_activo.Notas = notas` |
| `blueprints/api.py` | Modificar | Leer `notas` del JSON en `agregar_pedido()` y `agregar_pedido_efectivo()`; pasarlo a controllers |
| `tests/test_api_pedido.py` | Modificar | Añadir tests para el campo `notas` en `iniciar_pago` e `iniciar_pago_efectivo` |
| `templates/confirmacion_pago.html` | Reescribir | Nuevo diseño completo: cabecera, artículos, notas, tiempo animado, modales |

---

## Task 1: Añadir columna `Notas` al modelo `Pedido`

**Files:**
- Modify: `models.py:64-93`

- [ ] **Step 1: Leer el modelo actual**

  Abrir `models.py` y localizar la clase `Pedido` (línea ~64). Confirmar que no existe columna `Notas`.

- [ ] **Step 2: Añadir la columna**

  En `models.py`, dentro de la clase `Pedido`, añadir justo antes de la línea `cliente = relationship(...)`:

  ```python
  Notas = Column(String(300), nullable=True)
  ```

  El bloque queda así:

  ```python
  cancel_reason = Column(String(50), nullable=True)
  cancelled_by = Column(Integer, ForeignKey('empleados.EmpleadoID'), nullable=True)
  cancelled_at = Column(DateTime, nullable=True)
  Notas = Column(String(300), nullable=True)   # ← nuevo

  cliente = relationship("Usuario", back_populates="pedidos")
  ```

- [ ] **Step 3: Verificar que el modelo importa sin error**

  ```bash
  cd /home/siemprearmando/proyectos/panchi-bot
  python -c "from models import Pedido; print('OK', Pedido.Notas)"
  ```

  Resultado esperado: `OK <sqlalchemy column ...>`

- [ ] **Step 4: Ejecutar suite de tests para confirmar que no hay regresión**

  ```bash
  pytest -v --tb=short -x
  ```

  Los 3 tests de `TestWebhookMonei` seguirán fallando (conocidos). El resto debe pasar.

- [ ] **Step 5: Commit**

  ```bash
  git add models.py
  git commit -m "feat(model): añadir columna Notas a Pedido"
  ```

---

## Task 2: Propagar `notas` por el controlador de pago

**Files:**
- Modify: `controllers/pago.py:11-108` (iniciar_pago) y `controllers/pago.py:111-177` (iniciar_pago_efectivo)
- Modify: `tests/test_api_pedido.py`

### 2a — Escribir los tests primero

- [ ] **Step 1: Escribir tests para `iniciar_pago` con `notas`**

  En `tests/test_api_pedido.py`, al final de la clase `TestIniciarPago`, añadir:

  ```python
  def test_notas_se_asigna_al_pedido(self):
      """iniciar_pago debe asignar notas al objeto pedido."""
      from controllers.pago import iniciar_pago

      pedido = make_pedido(EstadoPedido.ENLACE2)
      gestor = make_gestor_pedidos(pedido)

      iniciar_pago(
          user_id=10,
          productos_recibidos=PRODUCTOS_VALIDOS_PAGO,
          nombre_cliente="Maria",
          numero_cliente="+34600000005",
          direccion_cliente="C/ Test 3",
          notas="No tocar el timbre",
          cache=make_cache(),
          gestor_pedidos=gestor,
          gestor_productos=self._make_gestor_productos(),
          monei=self._make_monei("https://monei.com/pay/123"),
          public_url=PUBLIC_URL,
      )

      assert pedido.Notas == "No tocar el timbre"

  def test_notas_vacio_por_defecto(self):
      """iniciar_pago sin notas no debe fallar (backward compat)."""
      from controllers.pago import iniciar_pago

      pedido = make_pedido(EstadoPedido.ENLACE2)
      gestor = make_gestor_pedidos(pedido)

      success, _ = iniciar_pago(
          user_id=10,
          productos_recibidos=PRODUCTOS_VALIDOS_PAGO,
          nombre_cliente="Maria",
          numero_cliente="+34600000005",
          direccion_cliente="C/ Test 3",
          cache=make_cache(),
          gestor_pedidos=gestor,
          gestor_productos=self._make_gestor_productos(),
          monei=self._make_monei(),
          public_url=PUBLIC_URL,
      )

      assert success is True
  ```

  Y también añadir una clase de tests para `iniciar_pago_efectivo`:

  ```python
  class TestIniciarPagoEfectivo:
      def _make_gestor_productos(self, precio: float = 3.5) -> MagicMock:
          gp = MagicMock()
          gp.obtener_producto_por_codigo.return_value = {"Precio": precio}
          return gp

      def test_notas_se_asigna_al_pedido(self):
          from controllers.pago import iniciar_pago_efectivo

          pedido = make_pedido(EstadoPedido.ENLACE2)
          gestor = make_gestor_pedidos(pedido)

          with patch("controllers.pago.enviar_mensaje_whatsapp"):
              iniciar_pago_efectivo(
                  user_id=10,
                  productos_recibidos=PRODUCTOS_VALIDOS_PAGO,
                  nombre_cliente="Maria",
                  numero_cliente="+34600000005",
                  direccion_cliente="C/ Test 3",
                  notas="Dejar en portería",
                  cache=make_cache(),
                  gestor_pedidos=gestor,
                  gestor_productos=self._make_gestor_productos(),
                  public_url=PUBLIC_URL,
              )

          assert pedido.Notas == "Dejar en portería"

      def test_notas_vacio_por_defecto(self):
          from controllers.pago import iniciar_pago_efectivo

          pedido = make_pedido(EstadoPedido.ENLACE2)
          gestor = make_gestor_pedidos(pedido)

          with patch("controllers.pago.enviar_mensaje_whatsapp"):
              success, _ = iniciar_pago_efectivo(
                  user_id=10,
                  productos_recibidos=PRODUCTOS_VALIDOS_PAGO,
                  nombre_cliente="Maria",
                  numero_cliente="+34600000005",
                  direccion_cliente="C/ Test 3",
                  cache=make_cache(),
                  gestor_pedidos=gestor,
                  gestor_productos=self._make_gestor_productos(),
                  public_url=PUBLIC_URL,
              )

          assert success is True
  ```

  > **Nota sobre el import necesario:** añadir `from unittest.mock import patch` al bloque de imports del archivo si no está ya.

- [ ] **Step 2: Ejecutar los tests nuevos — deben FALLAR**

  ```bash
  pytest tests/test_api_pedido.py::TestIniciarPago::test_notas_se_asigna_al_pedido \
         tests/test_api_pedido.py::TestIniciarPagoEfectivo::test_notas_se_asigna_al_pedido \
         -v --tb=short
  ```

  Resultado esperado: `FAILED` — `TypeError: iniciar_pago() got an unexpected keyword argument 'notas'`

### 2b — Implementar los cambios en el controlador

- [ ] **Step 3: Actualizar `iniciar_pago` en `controllers/pago.py`**

  Cambiar la firma de la función (línea ~11):

  ```python
  def iniciar_pago(
      user_id,
      productos_recibidos: list,
      nombre_cliente: str,
      numero_cliente: str,
      direccion_cliente: str,
      cache,
      gestor_pedidos,
      gestor_productos,
      monei,
      public_url: str,
      notas: str = "",          # ← nuevo parámetro al final
  ) -> tuple:
  ```

  Luego, justo después de la línea `gestor_pedidos.agregar_productos_a_pedido(pedido_activo_id, productos_validos)` (línea ~63), añadir:

  ```python
  if notas:
      pedido_activo.Notas = notas
  ```

- [ ] **Step 4: Actualizar `iniciar_pago_efectivo` en `controllers/pago.py`**

  Cambiar la firma (línea ~111):

  ```python
  def iniciar_pago_efectivo(
      user_id,
      productos_recibidos: list,
      nombre_cliente: str,
      numero_cliente: str,
      direccion_cliente: str,
      cache,
      gestor_pedidos,
      gestor_productos,
      public_url: str,
      notas: str = "",          # ← nuevo parámetro al final
  ) -> tuple:
  ```

  Justo después de la línea `gestor_pedidos.agregar_productos_a_pedido(pedido_id, productos_validos)` (línea ~160), añadir:

  ```python
  if notas:
      pedido_activo.Notas = notas
  ```

  > **Atención:** en `iniciar_pago_efectivo` la variable del pedido se llama `pedido_activo` (línea 129). Confirmar que el nombre es correcto mirando la línea donde se obtiene: `pedido_activo = gestor_pedidos.obtener_pedido_mas_reciente(user_id)`.

- [ ] **Step 5: Ejecutar los tests — deben PASAR**

  ```bash
  pytest tests/test_api_pedido.py::TestIniciarPago::test_notas_se_asigna_al_pedido \
         tests/test_api_pedido.py::TestIniciarPago::test_notas_vacio_por_defecto \
         tests/test_api_pedido.py::TestIniciarPagoEfectivo::test_notas_se_asigna_al_pedido \
         tests/test_api_pedido.py::TestIniciarPagoEfectivo::test_notas_vacio_por_defecto \
         -v --tb=short
  ```

  Resultado esperado: 4 × `PASSED`

- [ ] **Step 6: Ejecutar la suite completa para confirmar sin regresión**

  ```bash
  pytest -v --tb=short -x
  ```

- [ ] **Step 7: Commit**

  ```bash
  git add controllers/pago.py tests/test_api_pedido.py
  git commit -m "feat(pago): propagar campo notas a iniciar_pago e iniciar_pago_efectivo"
  ```

---

## Task 3: Leer `notas` del JSON en el blueprint

**Files:**
- Modify: `blueprints/api.py:48-84` (agregar_pedido) y `blueprints/api.py:110-138` (agregar_pedido_efectivo)

- [ ] **Step 1: Actualizar `agregar_pedido`**

  En la función `agregar_pedido()` de `blueprints/api.py`, después de la línea `carrito = data.get(...)`, añadir:

  ```python
  notas = data.get("notas", "")
  ```

  Luego en la llamada a `iniciar_pago(...)`, añadir el argumento:

  ```python
  success, result = iniciar_pago(
      user_id=id_usuario,
      productos_recibidos=carrito,
      nombre_cliente=data.get("name"),
      numero_cliente=data.get("numero"),
      direccion_cliente=data.get("direccion"),
      notas=notas,              # ← nuevo
      cache=cache,
      gestor_pedidos=gestor_pedidos,
      gestor_productos=gestor_productos,
      monei=get_monei(),
      public_url=config.PUBLIC_URL or "",
  )
  ```

- [ ] **Step 2: Actualizar `agregar_pedido_efectivo`**

  En la función `agregar_pedido_efectivo()`, tras la validación del token, añadir:

  ```python
  notas = data.get("notas", "")
  ```

  En la llamada a `iniciar_pago_efectivo(...)`, añadir:

  ```python
  success, result = iniciar_pago_efectivo(
      user_id=id_usuario,
      productos_recibidos=data.get("productos", []),
      nombre_cliente=data.get("name"),
      numero_cliente=data.get("numero"),
      direccion_cliente=data.get("direccion"),
      notas=notas,              # ← nuevo
      cache=cache,
      gestor_pedidos=gestor_pedidos,
      gestor_productos=gestor_productos,
      public_url=config.PUBLIC_URL or "",
  )
  ```

- [ ] **Step 3: Ejecutar la suite completa**

  ```bash
  pytest -v --tb=short -x
  ```

  Todos los tests existentes deben seguir pasando (el param `notas` tiene default `""`).

- [ ] **Step 4: Commit**

  ```bash
  git add blueprints/api.py
  git commit -m "feat(api): leer y reenviar campo notas en agregar_pedido y agregar_pedido_efectivo"
  ```

---

## Task 4: Reescribir `confirmacion_pago.html`

**Files:**
- Rewrite: `templates/confirmacion_pago.html`

Este task no tiene tests automatizados — se verifica visualmente en el navegador con `python main.py`.

- [ ] **Step 1: Hacer copia de seguridad del template actual**

  ```bash
  cp templates/confirmacion_pago.html templates/confirmacion_pago.html.bak
  ```

- [ ] **Step 2: Reescribir el template**

  Reemplazar el contenido completo de `templates/confirmacion_pago.html` con:

  ```html
  <!DOCTYPE html>
  <html lang="es">
  <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Confirmar pedido — Panchi Bot</title>
    <link rel="stylesheet" href="/static/css/styles.css">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Manrope:wght@700;800;900&display=swap" rel="stylesheet">
  </head>
  <body>

    <!-- ── CABECERA ── -->
    <header class="conf-header">
      <div class="conf-header__row1">
        <span class="conf-header__name">Hola, {{ name.split()[0] }} 👋</span>
        <span class="conf-header__badge">✓ Envío gratis</span>
      </div>
      <div class="conf-header__addr">
        <div class="conf-header__addr-icon">📍</div>
        <div class="conf-header__addr-text">
          <span class="conf-header__addr-label">Dirección de entrega</span>
          <span class="conf-header__addr-street">{{ calle }}</span>
        </div>
      </div>
    </header>

    <!-- ── CONTENIDO (con padding-bottom para la action bar fija) ── -->
    <div class="conf-body">

      <!-- Tarjeta de pedido -->
      <div class="conf-card">
        <div class="conf-card__head">
          <span class="conf-card__title">Tu pedido</span>
          <span class="conf-card__id">#{{ pedidoID }}</span>
        </div>

        <ul id="productos" class="conf-items">
          {% for producto in productos %}
          <li class="conf-item"
              data-codigo="{{ producto.codigo }}"
              data-unit="{{ (producto.precio / producto.cantidad) | round(2) }}">
            <div class="conf-item__qty">{{ producto.cantidad }}</div>
            <span class="conf-item__name">{{ producto.nombre }}</span>
            <span class="conf-item__price">{{ producto.precio }} €</span>
            <button class="conf-item__remove" onclick="quitarUnidad(this)" title="Quitar una unidad">−</button>
          </li>
          {% endfor %}
        </ul>

        <!-- Campo de notas -->
        <div class="conf-notes">
          <div class="conf-notes__label">✏️ Indicaciones de entrega (opcional)</div>
          <textarea
            id="notas"
            class="conf-notes__area"
            maxlength="300"
            placeholder="Ej: no tocar el timbre, dejar en portería…"></textarea>
        </div>

        <!-- Total -->
        <div class="conf-total">
          <span class="conf-total__label">Total</span>
          <span id="order-total-val" class="conf-total__val">{{ total }} €</span>
        </div>
      </div>

      <!-- Tiempo estimado animado -->
      <div class="conf-time">
        <div class="conf-time__left">
          <div class="conf-time__pulse">
            <div class="conf-time__core">⏱</div>
          </div>
          <div class="conf-time__text">
            <span class="conf-time__label">Tiempo estimado de entrega</span>
            <span class="conf-time__val">~15 minutos</span>
          </div>
        </div>
        <div class="conf-time__dots">
          <div class="conf-time__dot"></div>
          <div class="conf-time__dot"></div>
          <div class="conf-time__dot"></div>
        </div>
      </div>

    </div><!-- /conf-body -->

    <!-- ── ACTION BAR fija ── -->
    <div class="conf-bar">
      <button class="conf-bar__back" onclick="handleBack()">← Volver</button>
      <button class="conf-bar__online" onclick="abrirModal('modal-online')">
        <div class="conf-bar__btn-icon">💳</div>
        <div class="conf-bar__btn-text">
          <span class="conf-bar__btn-title">Online</span>
          <span class="conf-bar__btn-sub">Pago seguro</span>
        </div>
        <span class="conf-bar__btn-arrow">›</span>
      </button>
      <button class="conf-bar__cash" onclick="abrirModal('modal-efectivo')">
        <div class="conf-bar__btn-icon">🪙</div>
        <div class="conf-bar__btn-text">
          <span class="conf-bar__btn-title">Al recibir</span>
          <span class="conf-bar__btn-sub">Efectivo o tarjeta</span>
        </div>
        <span class="conf-bar__btn-arrow">›</span>
      </button>
    </div>

    <!-- ── MODAL ONLINE ── -->
    <div id="modal-online" class="conf-modal" style="display:none;" onclick="cerrarModalOverlay(event, 'modal-online')">
      <div class="conf-sheet">
        <div class="conf-sheet__handle"></div>
        <div class="conf-sheet__icon conf-sheet__icon--online">💳</div>
        <h2 class="conf-sheet__title">¿Confirmas el pago online?</h2>
        <p class="conf-sheet__sub">Serás redirigido a la pasarela de pago segura. El pedido se registra al completar el pago.</p>
        <div class="conf-sheet__summary">
          <span class="conf-sheet__summary-label">Total a pagar</span>
          <span class="conf-sheet__summary-total" id="modal-online-total">{{ total }} €</span>
        </div>
        <div class="conf-sheet__actions">
          <button id="btn-confirmar-online" class="conf-sheet__confirm conf-sheet__confirm--online"
                  onclick="confirmarPago('modal-online', '/api/agregar_pedido', 'btn-confirmar-online')">
            Sí, pagar con tarjeta →
          </button>
          <button class="conf-sheet__cancel" onclick="cerrarModal('modal-online')">Cancelar, volver al pedido</button>
        </div>
      </div>
    </div>

    <!-- ── MODAL EFECTIVO ── -->
    <div id="modal-efectivo" class="conf-modal" style="display:none;" onclick="cerrarModalOverlay(event, 'modal-efectivo')">
      <div class="conf-sheet">
        <div class="conf-sheet__handle"></div>
        <div class="conf-sheet__icon conf-sheet__icon--cash">🪙</div>
        <h2 class="conf-sheet__title">¿Confirmas el pedido?</h2>
        <p class="conf-sheet__sub">Pagarás al repartidor en la puerta. Puedes pagar en efectivo o con tarjeta.</p>
        <div class="conf-sheet__summary">
          <span class="conf-sheet__summary-label">Total a pagar</span>
          <span class="conf-sheet__summary-total" id="modal-efectivo-total">{{ total }} €</span>
        </div>
        <div class="conf-sheet__actions">
          <button id="btn-confirmar-efectivo" class="conf-sheet__confirm conf-sheet__confirm--cash"
                  onclick="confirmarPago('modal-efectivo', '/api/agregar_pedido_efectivo', 'btn-confirmar-efectivo')">
            Sí, confirmar pedido →
          </button>
          <button class="conf-sheet__cancel" onclick="cerrarModal('modal-efectivo')">Cancelar, volver al pedido</button>
        </div>
      </div>
    </div>

    <style>
      /* ── Cabecera ── */
      .conf-header {
        background: linear-gradient(135deg, #FF6B35 0%, #FF4500 100%);
        padding: 16px 0 20px;
        position: relative;
        overflow: hidden;
        border-radius: 0 0 24px 24px;
        display: flex;
        flex-direction: column;
        gap: 12px;
      }
      .conf-header::before {
        content: ''; position: absolute;
        width: 160px; height: 160px; border-radius: 50%;
        background: rgba(255,255,255,0.08);
        top: -40px; right: -30px;
      }
      .conf-header::after {
        content: ''; position: absolute;
        width: 90px; height: 90px; border-radius: 50%;
        background: rgba(255,255,255,0.06);
        bottom: -20px; left: 10px;
      }
      .conf-header__row1 {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0 14px;
        position: relative; z-index: 1;
      }
      .conf-header__name {
        font-family: 'Manrope', sans-serif;
        font-weight: 900; font-size: 19px; color: #fff;
        letter-spacing: -0.3px;
      }
      .conf-header__badge {
        background: var(--success);
        color: #fff; font-size: 11px; font-weight: 700;
        padding: 5px 11px; border-radius: 20px;
        box-shadow: 0 2px 10px rgba(34,197,94,0.45);
        white-space: nowrap;
      }
      .conf-header__addr {
        display: flex; align-items: center; gap: 8px;
        background: rgba(255,255,255,0.15);
        border: 1px solid rgba(255,255,255,0.25);
        border-radius: 12px; padding: 9px 12px;
        margin: 0 14px;
        position: relative; z-index: 1;
      }
      .conf-header__addr-icon {
        width: 30px; height: 30px; border-radius: 8px;
        background: rgba(255,255,255,0.2);
        display: flex; align-items: center; justify-content: center;
        font-size: 14px; flex-shrink: 0;
      }
      .conf-header__addr-text { display: flex; flex-direction: column; min-width: 0; }
      .conf-header__addr-label {
        font-size: 9px; font-weight: 600; color: rgba(255,255,255,0.65);
        text-transform: uppercase; letter-spacing: 0.6px;
      }
      .conf-header__addr-street {
        font-family: 'Manrope', sans-serif;
        font-weight: 800; font-size: 13px; color: #fff;
        letter-spacing: -0.2px; margin-top: 1px;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
      }

      /* ── Body ── */
      .conf-body {
        padding: 10px;
        padding-bottom: 90px; /* espacio para action bar fija */
        display: flex; flex-direction: column; gap: 8px;
      }

      /* ── Tarjeta ── */
      .conf-card {
        background: var(--surface);
        border-radius: var(--radius);
        border: 1px solid var(--border);
        box-shadow: var(--shadow);
        overflow: hidden;
      }
      .conf-card__head {
        padding: 10px 12px 8px;
        display: flex; justify-content: space-between; align-items: center;
        border-bottom: 1px solid var(--border);
      }
      .conf-card__title {
        font-family: 'Manrope', sans-serif;
        font-weight: 800; font-size: 14px;
      }
      .conf-card__id {
        background: var(--bg); border: 1px solid var(--border);
        border-radius: 20px; padding: 2px 8px;
        font-size: 12px; color: var(--text-muted);
      }

      /* ── Items ── */
      .conf-items {
        list-style: none; margin: 0; padding: 8px;
        display: flex; flex-direction: column; gap: 5px;
      }
      .conf-item {
        display: flex; align-items: center; gap: 8px;
        background: var(--bg); border-radius: 8px;
        padding: 8px 9px; border: 1px solid var(--border);
      }
      .conf-item__qty {
        width: 28px; height: 28px; border-radius: 7px;
        background: var(--primary); color: #fff;
        display: flex; align-items: center; justify-content: center;
        font-family: 'Manrope', sans-serif; font-weight: 800; font-size: 13px;
        flex-shrink: 0;
      }
      .conf-item__name { flex: 1; font-weight: 600; font-size: 13px; }
      .conf-item__price { font-weight: 700; font-size: 13px; white-space: nowrap; }
      .conf-item__remove {
        width: 24px; height: 24px;
        background: #FEE2E2; color: var(--danger);
        border: none; border-radius: 6px;
        font-size: 16px; font-weight: 800;
        display: flex; align-items: center; justify-content: center;
        cursor: pointer; flex-shrink: 0; line-height: 1;
      }

      /* ── Notas ── */
      .conf-notes {
        margin: 0 8px 8px;
        border: 1.5px solid #FFD5C2;
        border-radius: 8px; overflow: hidden;
      }
      .conf-notes__label {
        background: #FFF8F5; padding: 6px 10px;
        font-size: 11px; font-weight: 700; color: var(--primary);
        border-bottom: 1px solid #FFE0D0;
      }
      .conf-notes__area {
        display: block; width: 100%; box-sizing: border-box;
        padding: 8px 10px; border: none; outline: none;
        font-family: 'Inter', sans-serif; font-size: 13px;
        color: var(--text); background: transparent;
        resize: none; min-height: 52px;
      }
      .conf-notes__area::placeholder { color: #bbb; }

      /* ── Total ── */
      .conf-total {
        display: flex; justify-content: space-between; align-items: center;
        padding: 10px 12px;
        border-top: 2px dashed var(--border);
        margin: 0 4px;
      }
      .conf-total__label { font-size: 13px; font-weight: 700; color: var(--text-muted); }
      .conf-total__val   { font-family: 'Manrope', sans-serif; font-weight: 900; font-size: 16px; }

      /* ── Tiempo estimado ── */
      .conf-time {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 12px; padding: 10px 12px;
        display: flex; align-items: center; justify-content: space-between;
      }
      .conf-time__left { display: flex; align-items: center; gap: 12px; }
      .conf-time__pulse {
        width: 40px; height: 40px;
        position: relative;
        display: flex; align-items: center; justify-content: center;
        flex-shrink: 0;
      }
      .conf-time__pulse::before,
      .conf-time__pulse::after {
        content: ''; position: absolute;
        width: 40px; height: 40px; border-radius: 50%;
        background: rgba(255,107,53,0.15);
        animation: ring-out 2s ease-out infinite;
      }
      .conf-time__pulse::after { animation-delay: 0.8s; }
      @keyframes ring-out {
        0%   { transform: scale(0.5); opacity: 0.8; }
        100% { transform: scale(1.6); opacity: 0; }
      }
      .conf-time__core {
        width: 28px; height: 28px; border-radius: 50%;
        background: var(--primary); color: #fff;
        display: flex; align-items: center; justify-content: center;
        font-size: 14px; position: relative; z-index: 1;
      }
      .conf-time__text { display: flex; flex-direction: column; }
      .conf-time__label { font-size: 11px; color: var(--text-muted); font-weight: 600; }
      .conf-time__val   { font-family: 'Manrope', sans-serif; font-weight: 900; font-size: 14px; letter-spacing: -0.3px; }
      .conf-time__dots  { display: flex; align-items: center; gap: 4px; }
      .conf-time__dot {
        width: 7px; height: 7px; border-radius: 50%;
        background: var(--primary); opacity: 0.3;
        animation: dot-beat 1.4s ease-in-out infinite;
      }
      .conf-time__dot:nth-child(2) { animation-delay: 0.2s; }
      .conf-time__dot:nth-child(3) { animation-delay: 0.4s; }
      @keyframes dot-beat {
        0%, 80%, 100% { transform: scale(0.7); opacity: 0.3; }
        40%            { transform: scale(1.2); opacity: 1; }
      }

      /* ── Action bar ── */
      .conf-bar {
        position: fixed; bottom: 0; left: 0; right: 0;
        background: var(--surface);
        border-top: 1px solid var(--border);
        padding: 10px 12px;
        display: flex; gap: 7px;
        z-index: 100;
      }
      .conf-bar__back {
        background: var(--bg); border: 1.5px solid var(--border);
        border-radius: 10px; padding: 8px 10px;
        font-size: 12px; font-weight: 600; color: var(--text-muted);
        cursor: pointer; white-space: nowrap;
      }
      .conf-bar__online,
      .conf-bar__cash {
        flex: 1;
        border-radius: 12px; padding: 8px 10px;
        display: flex; align-items: center; gap: 8px;
        cursor: pointer; border: none;
      }
      .conf-bar__online {
        background: var(--primary);
        box-shadow: 0 3px 10px rgba(255,107,53,0.35);
      }
      .conf-bar__cash {
        background: #F0FDF4;
        border: 2px solid var(--success) !important;
      }
      .conf-bar__btn-icon { font-size: 18px; flex-shrink: 0; }
      .conf-bar__btn-text { flex: 1; display: flex; flex-direction: column; align-items: flex-start; }
      .conf-bar__btn-title { font-family: 'Manrope', sans-serif; font-weight: 800; font-size: 12px; }
      .conf-bar__btn-sub   { font-size: 10px; font-weight: 500; }
      .conf-bar__online .conf-bar__btn-title,
      .conf-bar__online .conf-bar__btn-sub   { color: #fff; }
      .conf-bar__cash .conf-bar__btn-title   { color: var(--text); }
      .conf-bar__cash .conf-bar__btn-sub     { color: #15803d; }
      .conf-bar__btn-arrow { font-size: 18px; font-weight: 700; }
      .conf-bar__online .conf-bar__btn-arrow { color: rgba(255,255,255,0.7); }
      .conf-bar__cash   .conf-bar__btn-arrow { color: #15803d; }

      /* ── Modal overlay ── */
      .conf-modal {
        position: fixed; inset: 0;
        background: rgba(0,0,0,0.45);
        backdrop-filter: blur(2px);
        display: flex; align-items: flex-end;
        z-index: 200;
      }
      .conf-sheet {
        background: var(--surface);
        border-radius: 20px 20px 0 0;
        width: 100%; padding: 0 16px 20px;
      }
      .conf-sheet__handle {
        width: 36px; height: 4px; border-radius: 2px;
        background: var(--border); margin: 12px auto 16px;
      }
      .conf-sheet__icon {
        width: 54px; height: 54px; border-radius: 16px;
        display: flex; align-items: center; justify-content: center;
        font-size: 28px; margin: 0 auto 10px;
      }
      .conf-sheet__icon--online { background: #FFF0EB; }
      .conf-sheet__icon--cash   { background: #F0FDF4; }
      .conf-sheet__title {
        font-family: 'Manrope', sans-serif;
        font-weight: 900; font-size: 17px;
        text-align: center; margin: 0 0 6px;
        letter-spacing: -0.3px;
      }
      .conf-sheet__sub {
        font-size: 13px; color: var(--text-muted);
        text-align: center; margin: 0 0 12px; line-height: 1.5;
      }
      .conf-sheet__summary {
        background: var(--bg); border: 1px solid var(--border);
        border-radius: 12px; padding: 10px 14px;
        display: flex; justify-content: space-between; align-items: center;
        margin-bottom: 12px;
      }
      .conf-sheet__summary-label { font-size: 13px; color: var(--text-muted); font-weight: 600; }
      .conf-sheet__summary-total {
        font-family: 'Manrope', sans-serif;
        font-weight: 900; font-size: 20px; color: var(--primary);
      }
      .conf-sheet__actions { display: flex; flex-direction: column; gap: 8px; }
      .conf-sheet__confirm {
        border-radius: 12px; padding: 13px;
        font-family: 'Manrope', sans-serif; font-weight: 800; font-size: 14px;
        text-align: center; color: #fff; border: none; cursor: pointer;
      }
      .conf-sheet__confirm--online { background: var(--primary); box-shadow: 0 4px 12px rgba(255,107,53,0.35); }
      .conf-sheet__confirm--cash   { background: var(--success); box-shadow: 0 4px 12px rgba(34,197,94,0.35); }
      .conf-sheet__confirm:disabled { opacity: 0.6; cursor: not-allowed; }
      .conf-sheet__cancel {
        background: none; border: none;
        font-size: 13px; font-weight: 600; color: var(--text-muted);
        text-decoration: underline; cursor: pointer; padding: 4px;
        text-align: center;
      }
    </style>

    <script>
      // ── Quitar una unidad ──
      function quitarUnidad(btn) {
        const li      = btn.closest('li');
        const qtyEl   = li.querySelector('.conf-item__qty');
        const priceEl = li.querySelector('.conf-item__price');
        const unit    = parseFloat(li.dataset.unit);

        let qty = parseInt(qtyEl.textContent, 10);

        if (qty <= 1) {
          li.remove();
        } else {
          qty--;
          qtyEl.textContent   = qty;
          priceEl.textContent = (unit * qty).toFixed(2) + ' €';
        }
        recalcularTotal();
      }

      function recalcularTotal() {
        let total = 0;
        document.querySelectorAll('#productos li').forEach(li => {
          const txt = li.querySelector('.conf-item__price').textContent;
          total += parseFloat(txt.replace('€', '').trim());
        });
        const fmt = total.toFixed(2) + ' €';
        document.getElementById('order-total-val').textContent = fmt;
        document.getElementById('modal-online-total').textContent  = fmt;
        document.getElementById('modal-efectivo-total').textContent = fmt;
      }

      // ── Volver al menú ──
      async function handleBack() {
        const updatedQty = {};
        document.querySelectorAll('#productos li').forEach(li => {
          const nombre = li.querySelector('.conf-item__name').textContent.trim();
          const qty    = parseInt(li.querySelector('.conf-item__qty').textContent, 10);
          if (qty > 0) updatedQty[nombre] = qty;
        });
        sessionStorage.setItem('cart_{{ token }}', JSON.stringify(updatedQty));

        try {
          await fetch('/api/volver_al_menu', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ token: '{{ token }}', userID: '{{ userID }}' }),
          });
        } catch (e) {
          console.warn('No se pudo restablecer el estado del pedido:', e);
        }
        window.location.href = '/menu/{{ token }}';
      }

      // ── Construir objeto de pedido desde el DOM ──
      function buildOrder() {
        const items = document.querySelectorAll('#productos li');
        if (items.length === 0) return null;

        const productos = Array.from(items).map(li => ({
          codigo:   li.getAttribute('data-codigo'),
          nombre:   li.querySelector('.conf-item__name').textContent.trim(),
          cantidad: parseInt(li.querySelector('.conf-item__qty').textContent, 10),
          precio:   parseFloat(li.querySelector('.conf-item__price').textContent.replace('€', '').trim()),
        }));

        return {
          name:      '{{ name }}',
          direccion: '{{ direccion }}',
          userID:    '{{ userID }}',
          numero:    '{{ numero }}',
          token:     '{{ token }}',
          notas:     document.getElementById('notas').value.trim(),
          productos,
          total: parseFloat(document.getElementById('order-total-val').textContent.replace('€', '').trim()),
        };
      }

      // ── Modales ──
      function abrirModal(modalId) {
        const order = buildOrder();
        if (!order) {
          alert('No hay productos en el pedido. Añade algo antes de confirmar.');
          return;
        }
        document.getElementById(modalId).style.display = 'flex';
      }

      function cerrarModal(modalId) {
        document.getElementById(modalId).style.display = 'none';
      }

      function cerrarModalOverlay(event, modalId) {
        // Cerrar si se pulsa el overlay (no el sheet)
        if (event.target.id === modalId) cerrarModal(modalId);
      }

      // ── Confirmar pago ──
      async function confirmarPago(modalId, endpoint, btnId) {
        const order = buildOrder();
        if (!order) return;

        const confirmBtn = document.getElementById(btnId);
        confirmBtn.disabled = true;

        try {
          const response = await fetch('{{ public_url }}' + endpoint, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify(order),
          });
          const result = await response.json();
          if (result.redirect_url) {
            sessionStorage.removeItem('cart_{{ token }}');
            window.location.href = result.redirect_url;
          } else {
            alert(result.message || 'Pedido enviado correctamente.');
            cerrarModal(modalId);
          }
        } catch (err) {
          console.error('Error de conexión:', err);
          alert('No se pudo conectar con el servidor. Inténtalo de nuevo.');
          confirmBtn.disabled = false;
        }
      }
    </script>

  </body>
  </html>
  ```

- [ ] **Step 3: Verificar que Flask puede renderizar el template sin errores**

  ```bash
  python -c "
  from main import app
  with app.test_request_context():
      from flask import render_template
      html = render_template('confirmacion_pago.html',
          name='Carlos García', calle='Calle Mayor 12',
          pedidoID=1042, productos=[], total='0.00',
          token='abc', userID=1, numero='+34600000000',
          direccion='Calle Mayor 12', public_url='http://localhost:5000')
      print('OK, len=', len(html))
  "
  ```

  Resultado esperado: `OK, len= XXXX` (sin errores de Jinja2)

- [ ] **Step 4: Verificar visualmente en el navegador**

  ```bash
  python main.py
  ```

  Navegar a `http://localhost:5000`. Para llegar a la página de confirmación, el flujo normal requiere un pedido activo en base de datos. Como alternativa rápida para revisar el diseño, se puede crear una ruta de prueba temporal o revisar el HTML directamente en el navegador con datos mock.

  **Checklist visual:**
  - [ ] Cabecera: gradiente naranja, saludo izquierda, badge verde derecha, dirección debajo
  - [ ] Artículos: badge naranja con cantidad, botón `−` rojo
  - [ ] Campo de notas visible y funcional (escribir texto, verificar que se conserva)
  - [ ] Total se actualiza al pulsar `−`
  - [ ] Tiempo estimado: animación de pulso visible, puntos latiendo
  - [ ] Botones de pago: pill con icono y flecha
  - [ ] Pulsar botón de pago → abre modal de confirmación
  - [ ] Modal muestra total correcto y método de pago
  - [ ] Pulsar "Cancelar" cierra el modal
  - [ ] Pulsar el overlay (fuera del sheet) cierra el modal
  - [ ] Pulsar "← Volver" navega al menú

- [ ] **Step 5: Eliminar el backup si todo es correcto**

  ```bash
  rm templates/confirmacion_pago.html.bak
  ```

- [ ] **Step 6: Ejecutar la suite de tests**

  ```bash
  pytest -v --tb=short
  ```

- [ ] **Step 7: Commit**

  ```bash
  git add templates/confirmacion_pago.html
  git commit -m "feat(template): rediseño completo de confirmacion_pago con notas, modales y animaciones"
  ```

---

## Verificación final

- [ ] Ejecutar la suite completa una última vez:

  ```bash
  pytest -v --tb=short
  ```

  Esperado: todos los tests pasan excepto los 3 `TestWebhookMonei` conocidos.

- [ ] Confirmar en DevTools (Network → Fonts) que Manrope carga con pesos 700, 800 y 900.

- [ ] Para producción: ejecutar en SQL Server antes de desplegar:

  ```sql
  ALTER TABLE pedidos ADD Notas NVARCHAR(300) NULL;
  ```
