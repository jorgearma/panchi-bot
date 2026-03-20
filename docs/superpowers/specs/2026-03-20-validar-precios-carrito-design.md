# Spec: Validar precios del carrito contra BD en confirmar_carrito()

**Fecha:** 2026-03-20
**Ámbito:** `controllers/pedido.py`, `blueprints/api.py`, `tests/test_api_pedido.py`

---

## Problema

`confirmar_carrito()` acepta `precio_unitario` del frontend sin validación.
Esos precios se almacenan en Redis y se muestran en la página de confirmación.
Un usuario puede manipularlos en DevTools antes de confirmar el carrito.

El importe cobrado por Monei y el registrado en `PedidoDetalle` son correctos
(recalculados desde BD en `iniciar_pago()`), pero el total visible en la
página de confirmación puede no coincidir con lo que se cobra, generando
confusión y riesgo de chargebacks.

---

## Solución

Validar y sustituir precios contra BD dentro de `confirmar_carrito()`,
ignorando completamente el `precio_unitario` enviado por el cliente.

---

## Cambios

### 1. `controllers/pedido.py` — `confirmar_carrito()`

**Firma nueva** (añadir `gestor_productos`):
```python
def confirmar_carrito(
    pedido_id_redis, name, token, user_id, numero,
    direccion, productos_recibidos, cache, gestor_pedidos,
    gestor_productos, public_url
) -> tuple:
```

**Loop nuevo** — sustituye el bloque `precio_unitario` existente:
```python
codigo = p.get("Codigo")
if not codigo:
    logger.error("confirmar_carrito: producto sin código identificador")
    return False, "Producto sin código identificador"

cantidad = p.get("cantidad", 1)
if cantidad <= 0:
    logger.error("confirmar_carrito: cantidad inválida %s para código %s", cantidad, codigo)
    return False, f"Cantidad inválida para el producto {codigo}"

producto_db = gestor_productos.obtener_producto_por_codigo(codigo)
if not producto_db:
    # None puede significar producto inexistente O error de BD (el manager devuelve None en ambos casos).
    # Se trata ambos igual: abortar con error. El log del manager ya registra el error de BD si lo hay.
    logger.error("confirmar_carrito: código %s no encontrado o error de BD", codigo)
    return False, f"Producto con código {codigo} no encontrado"

precio_db = producto_db.get("Precio")
if precio_db is None:
    logger.error("confirmar_carrito: precio NULL en BD para código %s", codigo)
    return False, f"Precio no disponible para el producto {codigo}"

precio_unitario = float(precio_db)
precio_total = round(precio_unitario * cantidad, 2)
```

El campo `nombre` del producto puede seguir viniendo del frontend (solo display).

### 2. `blueprints/api.py` — `/api/confirmacion`

Añadir `gestor_productos=gestor_productos` en la llamada a `confirmar_carrito()`.
`gestor_productos` ya está importado en el módulo desde `services`.

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
    gestor_productos=gestor_productos,   # ← nuevo
    public_url=config.PUBLIC_URL or "",
)
```

### 3. `tests/test_api_pedido.py`

#### 3a. Tests existentes en `TestConfirmarCarrito`

Todos los tests de `TestConfirmarCarrito` que llamen a `confirmar_carrito()` o
al endpoint `/api/confirmacion` deben añadir un mock de `gestor_productos`.
Ejemplo de patrón:

```python
mock_gestor_productos = MagicMock()
mock_gestor_productos.obtener_producto_por_codigo.return_value = {
    "Precio": Decimal("5.00"), "Nombre": "Producto Test", ...
}
```

Aplicar con `patch` o como argumento directo según el patrón existente en el test.

#### 3b. Nuevo test: precio frontend ignorado

Usar el mismo patrón directo del proyecto (llama a `confirmar_carrito()` directamente,
no a través del cliente HTTP, igual que `test_cart_stored_in_cache`):

```python
def test_confirmacion_ignora_precio_frontend(self):
    """El total almacenado en Redis usa precio de BD, no el precio_unitario del frontend."""
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
            "precio_unitario": precio_frontend_manipulado,  # manipulado por atacante
        }],
        cache=cache,
        gestor_pedidos=gestor,
        gestor_productos=mock_gp,
        public_url=PUBLIC_URL,
    )

    stored = json.loads(store["uuid-precio-test"])
    # Debe usar precio de BD (5.00 × 2 = 10.00), no precio frontend (0.01 × 2 = 0.02)
    assert stored["total"] == round(float(precio_bd) * cantidad, 2)  # 10.00
    assert stored["productos"][0]["precio"] == round(float(precio_bd) * cantidad, 2)
```

> Nota: adaptar la inspección del Redis mock al patrón existente en el proyecto
> (ver cómo otros tests verifican `cache.set`).

#### 3c. Nuevo test: producto con código ausente devuelve error

```python
def test_confirmacion_codigo_ausente_devuelve_error(client, ...):
    payload = {..., "productos": [{"nombre": "X", "cantidad": 1}]}  # sin "Codigo"
    resp = client.post("/api/confirmacion", json=payload)
    assert resp.status_code == 404
```

#### 3d. Nuevo test: cantidad inválida devuelve error

```python
def test_confirmacion_cantidad_cero_devuelve_error(client, ...):
    payload = {..., "productos": [{"Codigo": "P001", "cantidad": 0}]}
    resp = client.post("/api/confirmacion", json=payload)
    assert resp.status_code == 404
```

---

## Lo que NO cambia

- `controllers/pago.py` — ya calcula desde BD, correcto.
- `confirmacion_pago.html` — sin cambios de template.
- Estructura del JSON almacenado en Redis — mismos campos, precio ahora correcto.
- `iniciar_pago()` e `iniciar_pago_efectivo()` — sin cambios.

---

## Criterios de aceptación

1. El campo `total` almacenado en Redis por `confirmar_carrito()` es igual al total que calcula independientemente `iniciar_pago()` para el mismo carrito (ambos usan precio de BD × cantidad).
2. Si `precio_unitario` del frontend difiere del precio en BD, Redis almacena el precio de BD.
3. Si un código de producto no existe en BD (o la BD falla), `confirmar_carrito()` devuelve `(False, "Producto con código X no encontrado")` y el endpoint responde 404.
4. Si `cantidad <= 0`, `confirmar_carrito()` devuelve `(False, "Cantidad inválida...")` y el endpoint responde 404.
5. Si `"Codigo"` está ausente del item, `confirmar_carrito()` devuelve `(False, "Producto sin código...")` y el endpoint responde 404.
6. Si `Precio` en BD es NULL, `confirmar_carrito()` devuelve `(False, "Precio no disponible...")` y el endpoint responde 404.
7. Tests existentes pasan (actualizados con mock de `gestor_productos`).
8. Nuevos tests pasan.
