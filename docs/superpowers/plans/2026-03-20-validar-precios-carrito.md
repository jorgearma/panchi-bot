# Validar precios del carrito contra BD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hacer que `confirmar_carrito()` ignore el `precio_unitario` del frontend y use siempre el precio de BD, eliminando la discrepancia entre el total mostrado en la página de confirmación y el total cobrado.

**Architecture:** Añadir `gestor_productos` como parámetro a `confirmar_carrito()`. En el loop de productos, sustituir el precio del frontend por una consulta a BD con validaciones defensivas (código presente, producto existente, precio no NULL, cantidad > 0). Actualizar el caller en `api.py` y todos los tests que llaman a `confirmar_carrito()`.

**Tech Stack:** Python, Flask, SQLAlchemy, pytest, unittest.mock.

**Spec:** `docs/superpowers/specs/2026-03-20-validar-precios-carrito-design.md`

---

## Archivos que cambian

| Archivo | Tipo | Qué cambia |
|---------|------|------------|
| `controllers/pedido.py` | Modify | Firma + loop de `confirmar_carrito()` |
| `blueprints/api.py` | Modify | Pasar `gestor_productos` al llamar a `confirmar_carrito()` |
| `tests/test_api_pedido.py` | Modify | Añadir `gestor_productos` a llamadas existentes + 4 tests nuevos |

---

## Task 1: Añadir tests nuevos (en rojo)

**Files:**
- Modify: `tests/test_api_pedido.py`

- [ ] **Step 1: Verificar estado actual de los tests**

```bash
cd /home/siemprearmando/proyectos/panchi-bot
pytest tests/test_api_pedido.py -v --tb=short
```

Expected: todos pasan. Anotar el número total.

> **Nota sobre `geocodificar_direccion`:** `confirmar_carrito()` llama a `geocodificar_direccion()` en línea ~140. En tests no hay GOOGLE_MAPS_API_KEY, la función devuelve `None`, y el código maneja eso con `logger.warning` + continúa sin error. Los tests existentes ya pasan con este comportamiento y nuestro cambio no altera esa ruta. No es necesario parchear `geocodificar_direccion` en los tests.

> **Nota sobre criterios 3c/3d (HTTP 404):** Los tests 3c/3d se implementan como tests unitarios que llaman a `confirmar_carrito()` directamente. El endpoint devuelve 404 porque `api.py:39-40` hace `return jsonify({"error": result}), 404` cuando `success is False`. El comportamiento HTTP está cubierto por esa ruta de código que no cambia.

- [ ] **Step 2: Añadir los 5 tests nuevos al final de `TestConfirmarCarrito`**

En `tests/test_api_pedido.py`, dentro de la clase `TestConfirmarCarrito` (después del último método existente, antes del cierre de clase), añadir:

```python
    def test_confirmacion_ignora_precio_frontend(self):
        """El total en Redis usa precio de BD, no precio_unitario del frontend."""
        from controllers.pedido import confirmar_carrito
        from decimal import Decimal

        precio_frontend_manipulado = 0.01
        precio_bd = Decimal("5.00")
        cantidad = 2

        pedido = make_pedido(EstadoPedido.ENLACE)
        store = {}
        cache = MagicMock()
        cache.set.side_effect = lambda k, v, ex=None: store.update({k: v})
        gestor = make_gestor_pedidos(pedido)
        mock_gp = MagicMock()
        mock_gp.obtener_producto_por_codigo.return_value = {"Precio": precio_bd}

        confirmar_carrito(
            pedido_id_redis="uuid-precio-test",
            name="Test",
            token="tok",
            user_id=1,
            numero="+34600000000",
            direccion="Calle Mayor 1",
            productos_recibidos=[{
                "Codigo": "P001",
                "nombre": "Producto Test",
                "cantidad": cantidad,
                "precio_unitario": precio_frontend_manipulado,
            }],
            cache=cache,
            gestor_pedidos=gestor,
            gestor_productos=mock_gp,
            public_url=PUBLIC_URL,
        )

        stored = json.loads(store["uuid-precio-test"])
        assert stored["total"] == round(float(precio_bd) * cantidad, 2)          # 10.00, no 0.02
        assert stored["productos"][0]["precio"] == round(float(precio_bd) * cantidad, 2)

    def test_confirmacion_codigo_ausente_devuelve_error(self):
        """Si un item no tiene 'Codigo', confirmar_carrito devuelve (False, mensaje)."""
        from controllers.pedido import confirmar_carrito

        pedido = make_pedido(EstadoPedido.ENLACE)
        gestor = make_gestor_pedidos(pedido)
        mock_gp = MagicMock()

        success, msg = confirmar_carrito(
            pedido_id_redis="uuid-sin-codigo",
            name="Test",
            token="tok",
            user_id=1,
            numero="+34600000000",
            direccion="Calle Mayor 1",
            productos_recibidos=[{"nombre": "X", "cantidad": 1}],  # sin Codigo
            cache=make_cache(),
            gestor_pedidos=gestor,
            gestor_productos=mock_gp,
            public_url=PUBLIC_URL,
        )

        assert success is False
        assert "código" in msg.lower() or "codigo" in msg.lower()

    def test_confirmacion_cantidad_cero_devuelve_error(self):
        """Si cantidad <= 0, confirmar_carrito devuelve (False, mensaje)."""
        from controllers.pedido import confirmar_carrito

        pedido = make_pedido(EstadoPedido.ENLACE)
        gestor = make_gestor_pedidos(pedido)
        mock_gp = MagicMock()

        success, msg = confirmar_carrito(
            pedido_id_redis="uuid-cant-cero",
            name="Test",
            token="tok",
            user_id=1,
            numero="+34600000000",
            direccion="Calle Mayor 1",
            productos_recibidos=[{"Codigo": "P001", "nombre": "X", "cantidad": 0}],
            cache=make_cache(),
            gestor_pedidos=gestor,
            gestor_productos=mock_gp,
            public_url=PUBLIC_URL,
        )

        assert success is False
        assert "cantidad" in msg.lower()

    def test_confirmacion_producto_no_encontrado_devuelve_error(self):
        """Si gestor_productos no encuentra el código, confirmar_carrito devuelve error."""
        from controllers.pedido import confirmar_carrito

        pedido = make_pedido(EstadoPedido.ENLACE)
        gestor = make_gestor_pedidos(pedido)
        mock_gp = MagicMock()
        mock_gp.obtener_producto_por_codigo.return_value = None  # producto no existe

        success, msg = confirmar_carrito(
            pedido_id_redis="uuid-no-producto",
            name="Test",
            token="tok",
            user_id=1,
            numero="+34600000000",
            direccion="Calle Mayor 1",
            productos_recibidos=[{"Codigo": "INEXISTENTE", "nombre": "X", "cantidad": 1}],
            cache=make_cache(),
            gestor_pedidos=gestor,
            gestor_productos=mock_gp,
            public_url=PUBLIC_URL,
        )

        assert success is False
        assert "INEXISTENTE" in msg or "no encontrado" in msg.lower()

    def test_confirmacion_precio_null_devuelve_error(self):
        """Si Precio en BD es NULL, confirmar_carrito devuelve (False, mensaje)."""
        from controllers.pedido import confirmar_carrito

        pedido = make_pedido(EstadoPedido.ENLACE)
        gestor = make_gestor_pedidos(pedido)
        mock_gp = MagicMock()
        mock_gp.obtener_producto_por_codigo.return_value = {"Precio": None}

        success, msg = confirmar_carrito(
            pedido_id_redis="uuid-null-precio",
            name="Test",
            token="tok",
            user_id=1,
            numero="+34600000000",
            direccion="Calle Mayor 1",
            productos_recibidos=[{"Codigo": "P001", "nombre": "X", "cantidad": 1}],
            cache=make_cache(),
            gestor_pedidos=gestor,
            gestor_productos=mock_gp,
            public_url=PUBLIC_URL,
        )

        assert success is False
        assert "precio" in msg.lower() or "disponible" in msg.lower()
```

- [ ] **Step 3: Ejecutar los 5 tests nuevos para confirmar que fallan**

```bash
pytest tests/test_api_pedido.py::TestConfirmarCarrito::test_confirmacion_ignora_precio_frontend \
       tests/test_api_pedido.py::TestConfirmarCarrito::test_confirmacion_codigo_ausente_devuelve_error \
       tests/test_api_pedido.py::TestConfirmarCarrito::test_confirmacion_cantidad_cero_devuelve_error \
       tests/test_api_pedido.py::TestConfirmarCarrito::test_confirmacion_producto_no_encontrado_devuelve_error \
       tests/test_api_pedido.py::TestConfirmarCarrito::test_confirmacion_precio_null_devuelve_error \
       -v --tb=short
```

Expected: todos fallan con `TypeError: confirmar_carrito() got an unexpected keyword argument 'gestor_productos'`. Si pasan, hay un error — no continuar.

---

## Task 2: Modificar `confirmar_carrito()` en `controllers/pedido.py`

**Files:**
- Modify: `controllers/pedido.py:69-150`

- [ ] **Step 1: Añadir `gestor_productos` a la firma**

En `controllers/pedido.py`, localizar la línea:
```python
def confirmar_carrito(
    pedido_id_redis: str,
    name: str,
    token: str,
    user_id,
    numero: str,
    direccion: str,
    productos_recibidos: list,
    cache,
    gestor_pedidos,
    public_url: str,
) -> tuple:
```

Sustituir por:
```python
def confirmar_carrito(
    pedido_id_redis: str,
    name: str,
    token: str,
    user_id,
    numero: str,
    direccion: str,
    productos_recibidos: list,
    cache,
    gestor_pedidos,
    gestor_productos,
    public_url: str,
) -> tuple:
```

- [ ] **Step 2: Sustituir el loop de productos**

Localizar el bloque actual (líneas ~88-104):
```python
    for p in productos_recibidos:
        nombre_producto = p.get("nombre", "Producto desconocido")
        cantidad = p.get("cantidad", 1)
        precio_unitario = p.get("precio_unitario", 0.0)
        codigo = p.get("Codigo")
        precio_total = round(precio_unitario * cantidad, 2)

        productos.append({
            "nombre": nombre_producto,
            "cantidad": cantidad,
            "precio": precio_total,
            "codigo": codigo,
        })
        total += precio_total
```

Sustituir por:
```python
    for p in productos_recibidos:
        nombre_producto = p.get("nombre", "Producto desconocido")

        codigo = p.get("Codigo")
        if not codigo:
            logger.error("confirmar_carrito: producto sin código identificador")
            return False, "Producto sin código identificador"

        cantidad = p.get("cantidad", 1)
        if cantidad <= 0:
            logger.error(
                "confirmar_carrito: cantidad inválida %s para código %s", cantidad, codigo
            )
            return False, f"Cantidad inválida para el producto {codigo}"

        producto_db = gestor_productos.obtener_producto_por_codigo(codigo)
        if not producto_db:
            logger.error(
                "confirmar_carrito: código %s no encontrado o error de BD", codigo
            )
            return False, f"Producto con código {codigo} no encontrado"

        precio_db = producto_db.get("Precio")
        if precio_db is None:
            logger.error(
                "confirmar_carrito: precio NULL en BD para código %s", codigo
            )
            return False, f"Precio no disponible para el producto {codigo}"

        precio_unitario = float(precio_db)
        precio_total = round(precio_unitario * cantidad, 2)

        productos.append({
            "nombre": nombre_producto,
            "cantidad": cantidad,
            "precio": precio_total,
            "codigo": codigo,
        })
        total += precio_total
```

- [ ] **Step 3: Ejecutar los 5 tests nuevos — ahora deben pasar**

```bash
pytest tests/test_api_pedido.py::TestConfirmarCarrito::test_confirmacion_ignora_precio_frontend \
       tests/test_api_pedido.py::TestConfirmarCarrito::test_confirmacion_codigo_ausente_devuelve_error \
       tests/test_api_pedido.py::TestConfirmarCarrito::test_confirmacion_cantidad_cero_devuelve_error \
       tests/test_api_pedido.py::TestConfirmarCarrito::test_confirmacion_producto_no_encontrado_devuelve_error \
       tests/test_api_pedido.py::TestConfirmarCarrito::test_confirmacion_precio_null_devuelve_error \
       -v --tb=short
```

Expected: 5 PASSED.

---

## Task 3: Actualizar tests existentes de `TestConfirmarCarrito`

Los tests que llaman a `confirmar_carrito()` sin `gestor_productos` ahora fallan porque el parámetro es obligatorio.

**Files:**
- Modify: `tests/test_api_pedido.py`

- [ ] **Step 1: Ejecutar la clase completa para ver qué falla**

```bash
pytest tests/test_api_pedido.py::TestConfirmarCarrito -v --tb=short
```

Expected: los tests existentes fallan con `TypeError: confirmar_carrito() missing 1 required positional argument: 'gestor_productos'` (o similar).

- [ ] **Step 2: Actualizar `test_happy_path_returns_true_and_url`**

Localizar:
```python
        success, result = confirmar_carrito(
            pedido_id_redis="uuid-001",
            name="Ana",
            token="tok",
            user_id=99,
            numero="+34600000001",
            direccion="Calle Mayor 1",
            productos_recibidos=PRODUCTOS_RECIBIDOS,
            cache=cache,
            gestor_pedidos=gestor,
            public_url=PUBLIC_URL,
        )
```

Sustituir por:
```python
        mock_gp = MagicMock()
        mock_gp.obtener_producto_por_codigo.return_value = {"Precio": 3.5}

        success, result = confirmar_carrito(
            pedido_id_redis="uuid-001",
            name="Ana",
            token="tok",
            user_id=99,
            numero="+34600000001",
            direccion="Calle Mayor 1",
            productos_recibidos=PRODUCTOS_RECIBIDOS,
            cache=cache,
            gestor_pedidos=gestor,
            gestor_productos=mock_gp,
            public_url=PUBLIC_URL,
        )
```

- [ ] **Step 3: Actualizar `test_cart_stored_in_cache`**

Localizar:
```python
        confirmar_carrito(
            pedido_id_redis="uuid-002",
            name="Juan",
            token="tok2",
            user_id=42,
            numero="+34600000002",
            direccion="Calle Ancha 5",
            productos_recibidos=PRODUCTOS_RECIBIDOS,
            cache=cache,
            gestor_pedidos=gestor,
            public_url=PUBLIC_URL,
        )

        assert "uuid-002" in store
        payload = json.loads(store["uuid-002"])
        assert payload["name"] == "Juan"
        assert payload["total"] == round(3.5 * 2, 2)
```

Sustituir por:
```python
        mock_gp = MagicMock()
        mock_gp.obtener_producto_por_codigo.return_value = {"Precio": 3.5}

        confirmar_carrito(
            pedido_id_redis="uuid-002",
            name="Juan",
            token="tok2",
            user_id=42,
            numero="+34600000002",
            direccion="Calle Ancha 5",
            productos_recibidos=PRODUCTOS_RECIBIDOS,
            cache=cache,
            gestor_pedidos=gestor,
            gestor_productos=mock_gp,
            public_url=PUBLIC_URL,
        )

        assert "uuid-002" in store
        payload = json.loads(store["uuid-002"])
        assert payload["name"] == "Juan"
        assert payload["total"] == round(3.5 * 2, 2)  # precio de BD mock = 3.5
```

- [ ] **Step 4: Actualizar los 3 tests con `productos_recibidos=[]`**

Los tests `test_state_transition_to_enlace2_called`, `test_wrong_state_does_not_call_actualizar_estado` y `test_no_active_order_returns_false` usan `productos_recibidos=[]` — el loop no itera, pero el parámetro sigue siendo obligatorio. Añadir `gestor_productos=MagicMock()` a cada uno.

Para `test_state_transition_to_enlace2_called`, localizar:
```python
        confirmar_carrito(
            pedido_id_redis="uuid-003",
            name="X",
            token="t",
            user_id=1,
            numero="+34600000003",
            direccion="C/ Test 1",
            productos_recibidos=[],
            cache=make_cache(),
            gestor_pedidos=gestor,
            public_url=PUBLIC_URL,
        )
```
Añadir `gestor_productos=MagicMock(),` antes de `public_url=PUBLIC_URL,`.

Hacer lo mismo para `test_wrong_state_does_not_call_actualizar_estado` (uuid-004) y `test_no_active_order_returns_false` (uuid-005).

- [ ] **Step 5: Ejecutar la clase completa para confirmar que todo pasa**

```bash
pytest tests/test_api_pedido.py::TestConfirmarCarrito -v --tb=short
```

Expected: todos los tests de la clase pasan (los originales + los 4 nuevos).

---

## Task 4: Actualizar `blueprints/api.py`

**Files:**
- Modify: `blueprints/api.py:26-42`

- [ ] **Step 1: Añadir `gestor_productos` a la llamada**

En `blueprints/api.py`, localizar el bloque de la llamada a `confirmar_carrito()`:
```python
    success, result = confirmar_carrito(
        pedido_id_redis=pedido_id_redis,
        name=data.get("name", "Nombre no especificado"),
        token=data.get("token", ""),
        user_id=data.get("userId", "ID no especificado"),
        numero=data.get("numero", "Numero no especificado"),
        direccion=data.get("direccion", "Dirección no especificada"),
        productos_recibidos=data.get("productos", []),
        cache=cache,
        gestor_pedidos=gestor_pedidos,
        public_url=config.PUBLIC_URL or "",
    )
```

Sustituir por:
```python
    success, result = confirmar_carrito(
        pedido_id_redis=pedido_id_redis,
        name=data.get("name", "Nombre no especificado"),
        token=data.get("token", ""),
        user_id=data.get("userId", "ID no especificado"),
        numero=data.get("numero", "Numero no especificado"),
        direccion=data.get("direccion", "Dirección no especificada"),
        productos_recibidos=data.get("productos", []),
        cache=cache,
        gestor_pedidos=gestor_pedidos,
        gestor_productos=gestor_productos,
        public_url=config.PUBLIC_URL or "",
    )
```

`gestor_productos` ya está importado en la línea 8: `from services import gestor_pedidos, gestor_productos, get_monei, cache`. No se necesita ningún import adicional.

- [ ] **Step 2: Ejecutar la suite completa**

```bash
pytest -v --tb=short
```

Expected: misma cantidad de tests que al inicio + 5 nuevos, todos en verde. Los 3 pre-existentes `TestWebhookMonei` que fallaban antes siguen fallando (conocidos, no relacionados).

- [ ] **Step 3: Commit**

```bash
git add controllers/pedido.py blueprints/api.py tests/test_api_pedido.py
git commit -m "fix(carrito): validar precios contra BD en confirmar_carrito — ignora precio_unitario del frontend"
```
