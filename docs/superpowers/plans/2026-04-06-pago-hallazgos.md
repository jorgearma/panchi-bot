# Corrección hallazgos controllers/pago.py Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corregir los hallazgos H1–H6, H8, H9 de la auditoría de `controllers/pago.py` para eliminar pagos de 0€/negativos en Monei, clientes atrapados tras fallo de WhatsApp, contratos frágiles en el blueprint y puntos ciegos en observabilidad.

**Architecture:** Todos los cambios van en `controllers/pago.py` y `blueprints/api/payments.py`. No se crean nuevos archivos ni se modifica la lógica de negocio — solo se añaden guardias, try/except, logs y se elimina código muerto. No hay tests existentes para `pago.py`; cada tarea verifica con la suite completa.

**Tech Stack:** Python, Flask, SQLAlchemy, tenacity, pytest.

**Spec:** `docs/superpowers/specs/2026-04-06-pago-hallazgos-design.md`

---

## Archivos modificados

| Archivo | Acción |
|---------|--------|
| `controllers/pago.py` | Modificar — H1, H2, H3, H4, H5, H6, H8, H9 |
| `blueprints/api/payments.py` | Modificar — H2 (eliminar string comparison) y H6 (eliminar cache kwarg) |

---

### Task 1: H3 + H4 — Validaciones en `_validar_carrito`

**Files:**
- Modify: `controllers/pago.py:10-33`

- [ ] **Step 1: Añadir guardia de lista vacía (H3)**

En `controllers/pago.py`, reemplazar la función `_validar_carrito` completa (líneas 10-33):

```python
def _validar_carrito(productos_recibidos, gestor_productos):
    """Recalcula el carrito con datos de BD para evitar importes manipulados.

    Devuelve una lista de dicts {producto_id, cantidad, notas} — un dict por línea
    de pedido. El mismo producto puede aparecer varias veces con notas distintas
    (e.g. pizza sin cebolla + pizza con todo = dos líneas separadas).
    """
    if not productos_recibidos:
        return None, None, "El carrito no puede estar vacío"

    productos_validos = []
    total = 0.0
    for item in productos_recibidos:
        codigo   = item.get("codigo")
        cantidad = item.get("cantidad", 1)
        if not isinstance(cantidad, int) or cantidad <= 0:
            return None, None, f"Cantidad inválida para el producto {codigo}"
        notas    = item.get("notas", "") or None
        producto_db = gestor_productos.obtener_producto_por_codigo(codigo)
        if not producto_db:
            logger.error("_validar_carrito: producto %s no encontrado en BD", codigo)
            return None, None, f"Producto con código {codigo} no encontrado"
        total += float(producto_db["Precio"]) * cantidad
        productos_validos.append({
            "producto_id": codigo,  # codigo == ProductoID en este sistema
            "cantidad":    cantidad,
            "notas":       notas,
        })
    return productos_validos, total, None
```

- [ ] **Step 2: Verificar suite**

```bash
pytest -v --tb=short 2>&1 | tail -5
```

Expected: mismos failures que antes (pre-existing), ninguno nuevo.

- [ ] **Step 3: Commit**

```bash
git add controllers/pago.py
git commit -m "fix: validar carrito vacío y cantidad <= 0 en _validar_carrito (H3, H4)"
```

---

### Task 2: H9 + H2 — Log y URL real en guardia de idempotencia

**Files:**
- Modify: `controllers/pago.py:55-56`

**Contexto:** La función `iniciar_pago` recibe `public_url` como parámetro. La guardia de idempotencia necesita `public_url` para el fallback si `pedido_activo.enlace` es None.

- [ ] **Step 1: Reemplazar la guardia de idempotencia**

En `controllers/pago.py`, reemplazar las líneas 55-56:

```python
    # antes
    if pedido_activo.Estado == EstadoPedido.CONFIRMANDO_PAGO:
        return True, "El pedido ya está en proceso de pago."
```

por:

```python
    if pedido_activo.Estado == EstadoPedido.CONFIRMANDO_PAGO:
        logger.info("PAGO_YA_INICIADO pedido=%s usuario=%s", pedido_activo.PedidoID, user_id)
        return True, pedido_activo.enlace or f"{public_url}/pago_en_curso"
```

- [ ] **Step 2: Verificar suite**

```bash
pytest -v --tb=short 2>&1 | tail -5
```

Expected: mismos failures pre-existing, ninguno nuevo.

- [ ] **Step 3: Commit**

```bash
git add controllers/pago.py
git commit -m "fix: guardia idempotencia devuelve URL real con log (H2, H9)"
```

---

### Task 3: H5 — Log cuando `confirmar_pago_online` falla

**Files:**
- Modify: `controllers/pago.py:95-96`

**Contexto:** En este punto Monei ya creó el cobro. Sin log, si la DB falla aquí no hay trazabilidad para soporte. Las variables `pedido_activo_id`, `amount_in_cents` y `redirect_url` ya existen en scope.

- [ ] **Step 1: Añadir log en el bloque `if not ok`**

En `controllers/pago.py`, reemplazar las líneas 95-96:

```python
    # antes
    if not ok:
        return False, "Error al registrar el pedido tras el pago"
```

por:

```python
    if not ok:
        logger.error(
            "CONFIRMAR_PAGO_ONLINE_FALLIDO pedido=%s importe=%s monei_url=%s",
            pedido_activo_id, amount_in_cents, redirect_url
        )
        return False, "Error al registrar el pedido tras el pago"
```

- [ ] **Step 2: Verificar suite**

```bash
pytest -v --tb=short 2>&1 | tail -5
```

Expected: mismos failures pre-existing, ninguno nuevo.

- [ ] **Step 3: Commit**

```bash
git add controllers/pago.py
git commit -m "fix: log CONFIRMAR_PAGO_ONLINE_FALLIDO para trazabilidad (H5)"
```

---

### Task 4: H6 — Eliminar parámetro `cache` de `pago.py`

**Files:**
- Modify: `controllers/pago.py:36-48` y `controllers/pago.py:105-116`

- [ ] **Step 1: Eliminar `cache` de la firma de `iniciar_pago`**

En `controllers/pago.py`, reemplazar la firma completa de `iniciar_pago` (líneas 36-48):

```python
def iniciar_pago(
    user_id,
    productos_recibidos: list,
    nombre_cliente: str,
    numero_cliente: str,
    direccion_cliente: str,
    gestor_pedidos,
    gestor_productos,
    monei,
    public_url: str,
    notas: str = "",
) -> tuple:
    """Crea el pago online y mueve el pedido al estado de confirmación de pago."""
```

- [ ] **Step 2: Eliminar `cache` de la firma de `iniciar_pago_efectivo`**

En `controllers/pago.py`, reemplazar la firma completa de `iniciar_pago_efectivo` (líneas 105-116):

```python
def iniciar_pago_efectivo(
    user_id,
    productos_recibidos: list,
    nombre_cliente: str,
    numero_cliente: str,
    direccion_cliente: str,
    gestor_pedidos,
    gestor_productos,
    public_url: str,
    notas: str = "",
) -> tuple:
    """Confirma un pedido contra reembolso sin pasar por Monei."""
```

- [ ] **Step 3: Verificar suite**

```bash
pytest -v --tb=short 2>&1 | tail -5
```

Expected: FAIL en `test_webhook.py` y otros que usen `iniciar_pago` con `cache=` — necesitaremos arreglarlos en Task 5.

**Nota:** Si no hay tests que llamen a `iniciar_pago` directamente → solo pre-existing failures.

- [ ] **Step 4: Commit**

```bash
git add controllers/pago.py
git commit -m "fix: eliminar parámetro cache sin usar de pago.py (H6)"
```

---

### Task 5: H6 blueprint + H2 blueprint — Limpiar `payments.py`

**Files:**
- Modify: `blueprints/api/payments.py`

**Contexto:** Hay dos cambios en este archivo:
1. Eliminar `cache=cache` de las dos llamadas a `iniciar_pago` / `iniciar_pago_efectivo` (H6)
2. Eliminar la string comparison `if result == "El pedido ya está en proceso de pago."` que queda como código muerto tras H2 (H2)
3. Verificar si `cache` sigue siendo importado de `container` por otros motivos — si solo era para pasarlo a `iniciar_pago`, eliminar también del import.

- [ ] **Step 1: Limpiar `agregar_pedido`**

En `blueprints/api/payments.py`, reemplazar la función `agregar_pedido` completa:

```python
    @bp.route('/api/agregar_pedido', methods=['POST'])
    def agregar_pedido():
        """Inicia el flujo de pago online para el carrito recibido."""
        data = request.json
        logger.debug("Datos recibidos en agregar pedido: %s", data)

        token = data.get("token", "")
        token_user_id = _user_id_del_token(token)
        if not token or not token_user_id:
            return jsonify({"error": "Sesión inválida o expirada"}), 401

        post_user_id = data.get("userID")
        if str(post_user_id) != str(token_user_id):
            logger.warning("Token-userId mismatch en /api/agregar_pedido: token=%s post=%s", token_user_id, post_user_id)
            return jsonify({"error": "No autorizado"}), 403

        carrito = data.get("productos", data.get("carrito", []))
        if not carrito:
            return jsonify({"error": "El carrito está vacío"}), 400

        notas = data.get("notas", "")

        success, result = iniciar_pago(
            user_id=token_user_id,
            productos_recibidos=carrito,
            nombre_cliente=data.get("name"),
            numero_cliente=data.get("numero"),
            direccion_cliente=data.get("direccion"),
            notas=notas,
            gestor_pedidos=gestor_pedidos,
            gestor_productos=gestor_productos,
            monei=get_monei(),
            public_url=config.PUBLIC_URL or "",
        )

        if not success:
            return jsonify({"error": result}), 400

        return jsonify({"redirect_url": result, "message": "Pedido enviado correctamente."}), 200
```

- [ ] **Step 2: Limpiar `agregar_pedido_efectivo`**

En `blueprints/api/payments.py`, reemplazar la función `agregar_pedido_efectivo` completa:

```python
    @bp.route('/api/agregar_pedido_efectivo', methods=['POST'])
    def agregar_pedido_efectivo():
        """Confirma un pedido con pago contra entrega."""
        data = request.json
        logger.debug("Datos recibidos en agregar_pedido_efectivo: %s", data)

        token = data.get("token", "")
        token_user_id = _user_id_del_token(token)
        if not token or not token_user_id:
            return jsonify({"error": "Sesión inválida o expirada"}), 401

        post_user_id = data.get("userID")
        if str(post_user_id) != str(token_user_id):
            logger.warning("Token-userId mismatch en /api/agregar_pedido_efectivo: token=%s post=%s", token_user_id, post_user_id)
            return jsonify({"error": "No autorizado"}), 403

        notas = data.get("notas", "")

        success, result = iniciar_pago_efectivo(
            user_id=token_user_id,
            productos_recibidos=data.get("productos", []),
            nombre_cliente=data.get("name"),
            numero_cliente=data.get("numero"),
            direccion_cliente=data.get("direccion"),
            notas=notas,
            gestor_pedidos=gestor_pedidos,
            gestor_productos=gestor_productos,
            public_url=config.PUBLIC_URL or "",
        )

        if not success:
            return jsonify({"error": result}), 400

        return jsonify({"redirect_url": result, "message": "Pedido confirmado. Pago a la entrega."}), 200
```

- [ ] **Step 3: Limpiar el import de `cache` si ya no se usa**

Verificar la línea 6 del archivo:
```python
from container import gestor_pedidos, gestor_productos, get_monei, cache
```

Si `cache` no aparece en ningún otro lugar del archivo, eliminarla del import:
```python
from container import gestor_pedidos, gestor_productos, get_monei
```

Para verificar: `grep -n "cache" blueprints/api/payments.py` — si solo aparece en la línea de import, elimínala.

- [ ] **Step 4: Verificar suite**

```bash
pytest -v --tb=short 2>&1 | tail -5
```

Expected: mismos failures pre-existing, ninguno nuevo.

- [ ] **Step 5: Commit**

```bash
git add blueprints/api/payments.py
git commit -m "fix: eliminar cache kwarg y string comparison muerta en payments.py (H2, H6)"
```

---

### Task 6: H8 — DB error handling en ambas funciones

**Files:**
- Modify: `controllers/pago.py:1-7` (imports) y cuerpos de `iniciar_pago` e `iniciar_pago_efectivo`

- [ ] **Step 1: Añadir imports de SQLAlchemy y tenacity**

En `controllers/pago.py`, reemplazar el bloque de imports al inicio del archivo (líneas 1-7):

```python
import logging

from sqlalchemy.exc import SQLAlchemyError
from tenacity import RetryError

from states import EstadoPedido
from services.monei_service import crear_pago as monei_crear_pago
from controllers.pago_notifier import _enviar_confirmacion_efectivo
```

- [ ] **Step 2: Wrap `obtener_pedido_mas_reciente` en `iniciar_pago`**

En `controllers/pago.py`, reemplazar la línea `pedido_activo = gestor_pedidos.obtener_pedido_mas_reciente(user_id)` al inicio de `iniciar_pago` (línea ~50 tras Tasks anteriores):

```python
    try:
        pedido_activo = gestor_pedidos.obtener_pedido_mas_reciente(user_id)
    except (SQLAlchemyError, RetryError) as e:
        logger.error("iniciar_pago: DB error usuario=%s: %s", user_id, e)
        return False, "Error de base de datos. Intente más tarde."
```

- [ ] **Step 3: Wrap `confirmar_pago_online` en `iniciar_pago`**

En `controllers/pago.py`, reemplazar el bloque `ok = gestor_pedidos.confirmar_pago_online(...)` e `if not ok:` en `iniciar_pago`:

```python
    try:
        ok = gestor_pedidos.confirmar_pago_online(
            pedido_activo_id, productos_validos, redirect_url, notas=notas or None
        )
    except (SQLAlchemyError, RetryError) as e:
        logger.error(
            "iniciar_pago: DB error al confirmar pedido=%s monei_url=%s: %s",
            pedido_activo_id, redirect_url, e
        )
        return False, "Error de base de datos tras crear el pago."
    if not ok:
        logger.error(
            "CONFIRMAR_PAGO_ONLINE_FALLIDO pedido=%s importe=%s monei_url=%s",
            pedido_activo_id, amount_in_cents, redirect_url
        )
        return False, "Error al registrar el pedido tras el pago"
```

**Nota:** El `if not ok:` va **fuera** del try/except (mismo nivel de indentación que `try:`). Si `confirmar_pago_online` lanza excepción → rama except. Si devuelve False → rama `if not ok`. Si devuelve True → continúa.

- [ ] **Step 4: Wrap `obtener_pedido_mas_reciente` en `iniciar_pago_efectivo`**

En `controllers/pago.py`, reemplazar la llamada al inicio de `iniciar_pago_efectivo`:

```python
    try:
        pedido_activo = gestor_pedidos.obtener_pedido_mas_reciente(user_id)
    except (SQLAlchemyError, RetryError) as e:
        logger.error("iniciar_pago_efectivo: DB error usuario=%s: %s", user_id, e)
        return False, "Error de base de datos. Intente más tarde."
```

- [ ] **Step 5: Wrap `confirmar_pago_efectivo` en `iniciar_pago_efectivo`**

En `controllers/pago.py`, reemplazar el bloque `ok = gestor_pedidos.confirmar_pago_efectivo(...)` e `if not ok:` en `iniciar_pago_efectivo`:

```python
    try:
        ok = gestor_pedidos.confirmar_pago_efectivo(
            pedido_id, productos_validos, notas=notas or None
        )
    except (SQLAlchemyError, RetryError) as e:
        logger.error("iniciar_pago_efectivo: DB error al confirmar pedido=%s: %s", pedido_id, e)
        return False, "Error de base de datos al confirmar el pedido."
    if not ok:
        return False, "Error al registrar el pedido contra reembolso"
```

- [ ] **Step 6: Verificar suite**

```bash
pytest -v --tb=short 2>&1 | tail -5
```

Expected: mismos failures pre-existing, ninguno nuevo.

- [ ] **Step 7: Commit**

```bash
git add controllers/pago.py
git commit -m "fix: DB error handling con try/except en iniciar_pago e iniciar_pago_efectivo (H8)"
```

---

### Task 7: H1 — try/except en `_enviar_confirmacion_efectivo`

**Files:**
- Modify: `controllers/pago.py` — final de `iniciar_pago_efectivo`

**Contexto:** `_enviar_confirmacion_efectivo` se llama **después** de que `confirmar_pago_efectivo` ya persistió el pedido como `CONTRA_REEMBOLSO`. Si WhatsApp falla aquí, el pedido está confirmado en DB pero el cliente recibe un 500 y no puede reintentar (el estado ya cambió). La solución: capturar la excepción, loguear, y devolver `True` de todas formas — el cliente ve la confirmación en la web aunque no llegue el WhatsApp.

- [ ] **Step 1: Wrap `_enviar_confirmacion_efectivo` en try/except**

En `controllers/pago.py`, localiza el final de `iniciar_pago_efectivo`. Reemplaza las dos líneas:

```python
    # antes (tras las Tasks anteriores, el bloque confirmar_pago_efectivo ya tiene try/except)
    total_euros = round(total_calculado, 2)
    _enviar_confirmacion_efectivo(numero_cliente, nombre_cliente, total_euros, pedido_id, direccion_cliente)
    logger.info("iniciar_pago_efectivo: pedido %s confirmado contra reembolso", pedido_id)

    return True, f"{public_url}/pago_confirmado?pedido_id={redis_id}"
```

por:

```python
    total_euros = round(total_calculado, 2)
    try:
        _enviar_confirmacion_efectivo(numero_cliente, nombre_cliente, total_euros, pedido_id, direccion_cliente)
    except Exception as e:
        logger.error(
            "CONFIRMACION_EFECTIVO_WA_FALLIDA pedido=%s error=%s",
            pedido_id, e, exc_info=True
        )
    logger.info("iniciar_pago_efectivo: pedido %s confirmado contra reembolso", pedido_id)

    return True, f"{public_url}/pago_confirmado?pedido_id={redis_id}"
```

- [ ] **Step 2: Verificar suite**

```bash
pytest -v --tb=short 2>&1 | tail -5
```

Expected: mismos failures pre-existing, ninguno nuevo.

- [ ] **Step 3: Commit**

```bash
git add controllers/pago.py
git commit -m "fix: try/except en _enviar_confirmacion_efectivo — cliente no queda atrapado (H1)"
```

---

### Task 8: Verificación final

**Files:**
- Read: `controllers/pago.py`
- Read: `blueprints/api/payments.py`

- [ ] **Step 1: Suite completa**

```bash
pytest -v --tb=short
```

Expected: mismos 4 failures pre-existing, todos los demás en PASS.

- [ ] **Step 2: Revisión visual de `controllers/pago.py`**

Lee el archivo completo y confirma:

- Imports incluyen `SQLAlchemyError` y `RetryError`
- `_validar_carrito` tiene guardia `if not productos_recibidos` al inicio
- `_validar_carrito` valida `cantidad > 0` dentro del loop
- `iniciar_pago`: guardia idempotencia tiene `logger.info("PAGO_YA_INICIADO...")` y devuelve `pedido_activo.enlace or ...`
- `iniciar_pago`: `obtener_pedido_mas_reciente` envuelta en try/except
- `iniciar_pago`: `confirmar_pago_online` envuelta en try/except con log en `if not ok`
- `iniciar_pago`: firma sin `cache`
- `iniciar_pago_efectivo`: firma sin `cache`
- `iniciar_pago_efectivo`: `obtener_pedido_mas_reciente` envuelta en try/except
- `iniciar_pago_efectivo`: `confirmar_pago_efectivo` envuelta en try/except
- `iniciar_pago_efectivo`: `_enviar_confirmacion_efectivo` envuelta en try/except

- [ ] **Step 3: Revisión visual de `blueprints/api/payments.py`**

Confirma:
- No hay `cache=cache` en ninguna llamada
- No hay `if result == "El pedido ya está en proceso de pago."` 
- Import de `cache` eliminado si no se usa en otro lugar

- [ ] **Step 4: Commit final si hubo ajustes**

```bash
git add controllers/pago.py blueprints/api/payments.py
git commit -m "fix: ajustes menores tras revisión final"
```

Solo si hubo cambios. Si no, omitir.
