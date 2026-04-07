# Pedido Controller — Hallazgos de Auditoría Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corregir los hallazgos críticos y altos de la auditoría de `controllers/pedido.py` y extraer las responsabilidades del carrito web a su propio módulo.

**Architecture:** Se atacan primero los bugs de negocio (carrito vacío, inconsistencia Redis/DB, errores no capturados), luego los de diseño (shadowing de parámetro, logging), y por último la separación estructural (`confirmar_carrito` → `controllers/carrito.py`). Cada tarea es independiente y produce tests verdes antes de pasar a la siguiente.

**Tech Stack:** Python 3, Flask, SQLAlchemy, FakeRedis (tests), pytest, unittest.mock

---

## Mapa de archivos

| Archivo | Cambio |
|---------|--------|
| `controllers/pedido.py` | H2 guard, H3 reorder, H4 try/except, H5 estado check, H9 logging; luego borrar `confirmar_carrito` y `_validar_productos` |
| `controllers/carrito.py` | CREAR — recibe `confirmar_carrito` y `_validar_productos` con renombre de parámetro (H7) |
| `blueprints/api/cart.py` | Cambiar import: `from controllers.pedido` → `from controllers.carrito` |
| `tests/test_api_pedido.py` | Actualizar tests que pasan `[]` (fallarán con H2); actualizar imports en Task 6; añadir tests nuevos |

---

## Task 1: H9 — Logging para paths sin cobertura en `procesar_pedido`

**Files:**
- Modify: `controllers/pedido.py:29-30` y `57-58`

- [ ] **Step 1: Verificar que el test suite pasa antes de tocar nada**

```bash
pytest tests/test_api_pedido.py -v --tb=short
```
Expected: todos pasan (hay 3 preexistentes que pueden fallar — ver MEMORY.md; estos no son regresiones).

- [ ] **Step 2: Añadir logging en los dos paths sin cobertura**

En `controllers/pedido.py`, reemplazar:

```python
    if es_pregunta(datos.pedido):
        return "Lo siento, no reconocí tu pregunta."
```

por:

```python
    if es_pregunta(datos.pedido):
        logger.info("PREGUNTA_DETECTADA usuario=%s input=%r", numero_cliente, datos.pedido)
        return "Lo siento, no reconocí tu pregunta."
```

Y reemplazar:

```python
    menu_comando_no_reconocido = mostrar_menu()
    return f"❌Comando no reconocido \n▪️ Por favor, elige una *opción*  {menu_comando_no_reconocido}\nEscribe el *Número* correspondiente para elegir."
```

por:

```python
    logger.info("COMANDO_NO_RECONOCIDO usuario=%s input=%r", numero_cliente, pedido_limpio)
    menu_comando_no_reconocido = mostrar_menu()
    return f"❌Comando no reconocido \n▪️ Por favor, elige una *opción*  {menu_comando_no_reconocido}\nEscribe el *Número* correspondiente para elegir."
```

- [ ] **Step 3: Verificar que los tests siguen pasando**

```bash
pytest tests/test_api_pedido.py -v --tb=short
```
Expected: mismos resultados que Step 1.

- [ ] **Step 4: Commit**

```bash
git add controllers/pedido.py
git commit -m "obs: añadir logging PREGUNTA_DETECTADA y COMANDO_NO_RECONOCIDO en procesar_pedido (H9)"
```

---

## Task 2: H2 — Guard de carrito vacío en `confirmar_carrito`

**Files:**
- Modify: `controllers/pedido.py:115-131` (inicio de `confirmar_carrito`)
- Modify: `tests/test_api_pedido.py` — actualizar 3 tests que pasan `[]` y añadir nuevo test

**Contexto:** Tres tests existentes pasan `productos_recibidos=[]`. Con el guard nuevo devolverán `(False, "El carrito no puede estar vacío")` antes de llegar a la lógica que testean. Hay que darles productos válidos.

- [ ] **Step 1: Escribir el test que falla**

En `tests/test_api_pedido.py`, dentro de `class TestConfirmarCarrito`, añadir:

```python
    def test_confirmar_carrito_vacio_rechazado(self):
        """Un carrito sin productos debe ser rechazado antes de consultar la BD."""
        from controllers.pedido import confirmar_carrito

        gestor = MagicMock()  # no debe ser llamado nunca

        success, msg = confirmar_carrito(
            pedido_id_redis="uuid-vacio",
            name="X",
            token="t",
            user_id=1,
            numero="+34",
            direccion="C/",
            productos_recibidos=[],
            cache=MagicMock(),
            gestor_pedidos=gestor,
            gestor_productos=MagicMock(),
            public_url=PUBLIC_URL,
        )

        assert success is False
        assert "vacío" in msg.lower() or "vacio" in msg.lower()
        gestor.obtener_pedido_mas_reciente.assert_not_called()
```

- [ ] **Step 2: Ejecutar el test para verificar que falla**

```bash
pytest tests/test_api_pedido.py::TestConfirmarCarrito::test_confirmar_carrito_vacio_rechazado -v
```
Expected: FAIL — `assert False is False` pasa pero `"vacío"` no está en el mensaje actual.

- [ ] **Step 3: Implementar el guard en `confirmar_carrito`**

En `controllers/pedido.py`, en la función `confirmar_carrito`, añadir como **primera línea del cuerpo** (antes de `_validar_productos`):

```python
    if not productos_recibidos:
        logger.warning("confirmar_carrito: carrito vacío para usuario %s", user_id)
        return False, "El carrito no puede estar vacío"
```

El inicio de la función queda así:

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
    """Guarda el carrito validado, calcula su total y lo deja listo para confirmar."""
    if not productos_recibidos:
        logger.warning("confirmar_carrito: carrito vacío para usuario %s", user_id)
        return False, "El carrito no puede estar vacío"

    ok, resultado = _validar_productos(productos_recibidos, gestor_productos)
    ...
```

- [ ] **Step 4: Verificar que el nuevo test pasa**

```bash
pytest tests/test_api_pedido.py::TestConfirmarCarrito::test_confirmar_carrito_vacio_rechazado -v
```
Expected: PASS.

- [ ] **Step 5: Reparar los tres tests que pasan `[]` y ahora fallan**

Los tests afectados pasan `productos_recibidos=[]` para llegar a una lógica posterior (estado, pedido activo). Con el guard nuevo se corta antes. Hay que darles un producto válido y mockear `gestor_productos`.

**`test_state_transition_to_enlace2_called`** — cambiar `productos_recibidos=[]` por productos válidos:

```python
    def test_state_transition_to_enlace2_called(self):
        from controllers.pedido import confirmar_carrito

        pedido = make_pedido(EstadoPedido.ENLACE)
        gestor = make_gestor_pedidos(pedido)
        mock_gp = MagicMock()
        mock_gp.obtener_producto_por_codigo.return_value = {"Precio": 3.5}

        confirmar_carrito(
            pedido_id_redis="uuid-003",
            name="X",
            token="t",
            user_id=1,
            numero="+34600000003",
            direccion="C/ Test 1",
            productos_recibidos=PRODUCTOS_RECIBIDOS,
            cache=make_cache(),
            gestor_pedidos=gestor,
            gestor_productos=mock_gp,
            public_url=PUBLIC_URL,
        )

        gestor.fijar_carrito_confirmado.assert_called_once()
        call_args = gestor.fijar_carrito_confirmado.call_args
        assert call_args.args[0] == pedido.PedidoID
        assert call_args.args[1] == "uuid-003"
```

**`test_wrong_state_does_not_call_fijar_carrito_confirmado`** — cambiar `productos_recibidos=[]` por productos válidos:

```python
    def test_wrong_state_does_not_call_fijar_carrito_confirmado(self):
        """If the order is not in ENLACE state, no state transition is attempted."""
        from controllers.pedido import confirmar_carrito

        pedido = make_pedido(EstadoPedido.ENLACE2)  # already past ENLACE
        gestor = make_gestor_pedidos(pedido)
        mock_gp = MagicMock()
        mock_gp.obtener_producto_por_codigo.return_value = {"Precio": 3.5}

        success, msg = confirmar_carrito(
            pedido_id_redis="uuid-004",
            name="X",
            token="t",
            user_id=1,
            numero="+34600000004",
            direccion="C/ Test 2",
            productos_recibidos=PRODUCTOS_RECIBIDOS,
            cache=make_cache(),
            gestor_pedidos=gestor,
            gestor_productos=mock_gp,
            public_url=PUBLIC_URL,
        )

        assert success is False
        gestor.fijar_carrito_confirmado.assert_not_called()
```

**`test_no_active_order_returns_false`** — cambiar `productos_recibidos=[]` por productos válidos y añadir mock de productos:

```python
    def test_no_active_order_returns_false(self):
        from controllers.pedido import confirmar_carrito

        gestor = MagicMock()
        gestor.obtener_pedido_mas_reciente.return_value = None
        mock_gp = MagicMock()
        mock_gp.obtener_producto_por_codigo.return_value = {"Precio": 3.5}

        success, msg = confirmar_carrito(
            pedido_id_redis="uuid-005",
            name="X",
            token="t",
            user_id=1,
            numero="+34",
            direccion="C/",
            productos_recibidos=PRODUCTOS_RECIBIDOS,
            cache=make_cache(),
            gestor_pedidos=gestor,
            gestor_productos=mock_gp,
            public_url=PUBLIC_URL,
        )

        assert success is False
        assert "pedido activo" in msg.lower()
```

- [ ] **Step 6: Ejecutar todos los tests de la clase para verificar que pasan**

```bash
pytest tests/test_api_pedido.py::TestConfirmarCarrito -v --tb=short
```
Expected: todos los tests de `TestConfirmarCarrito` en verde.

- [ ] **Step 7: Ejecutar suite completa para verificar sin regresiones**

```bash
pytest tests/test_api_pedido.py -v --tb=short
```
Expected: mismos resultados que al inicio (sin nuevas regresiones).

- [ ] **Step 8: Commit**

```bash
git add controllers/pedido.py tests/test_api_pedido.py
git commit -m "fix: guard de carrito vacío al inicio de confirmar_carrito — pedido 0 productos no pasa (H2)"
```

---

## Task 3: H4 — try/except en llamadas DB de `confirmar_carrito`

**Files:**
- Modify: `controllers/pedido.py:134` y `170` (wrappear en try/except)
- Modify: `tests/test_api_pedido.py` — añadir test de DB error

**Contexto:** `SQLAlchemyError` lanzada por `obtener_pedido_mas_reciente` o `fijar_carrito_confirmado` propaga al blueprint sin log. `tenacity` ya reintenta en el manager; si todos los reintentos fallan, el `RetryError` llega aquí sin captura.

- [ ] **Step 1: Añadir import de `RetryError` en `controllers/pedido.py`**

Al inicio del archivo, añadir al bloque de imports:

```python
from tenacity import RetryError
```

El bloque de imports queda (orden existente + nuevo import):

```python
import json
import logging

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from tenacity import RetryError
from utils.es_pregunta import es_pregunta
from container import gestor_pedidos
from services.token_service import generar_enlace
from maps_module import geocodificar_direccion
from utils.menu_opciones import menu, mostrar_menu
from utils.text_utils import limpiar_texto
from schemas.twilio import PedidoInput
from states import EstadoPedido
```

- [ ] **Step 2: Escribir el test que falla para DB error en `obtener_pedido_mas_reciente`**

En `tests/test_api_pedido.py`, dentro de `class TestConfirmarCarrito`, añadir:

```python
    def test_confirmar_carrito_db_error_capturado(self):
        """SQLAlchemyError en obtener_pedido_mas_reciente no debe propagarse — devuelve (False, msg)."""
        from controllers.pedido import confirmar_carrito
        from sqlalchemy.exc import SQLAlchemyError

        gestor = MagicMock()
        gestor.obtener_pedido_mas_reciente.side_effect = SQLAlchemyError("timeout")
        mock_gp = MagicMock()
        mock_gp.obtener_producto_por_codigo.return_value = {"Precio": 3.5}

        success, msg = confirmar_carrito(
            pedido_id_redis="uuid-db-error",
            name="X",
            token="t",
            user_id=1,
            numero="+34",
            direccion="C/",
            productos_recibidos=PRODUCTOS_RECIBIDOS,
            cache=make_cache(),
            gestor_pedidos=gestor,
            gestor_productos=mock_gp,
            public_url=PUBLIC_URL,
        )

        assert success is False
        assert "base de datos" in msg.lower() or "error" in msg.lower()
```

- [ ] **Step 3: Ejecutar el test para verificar que falla**

```bash
pytest tests/test_api_pedido.py::TestConfirmarCarrito::test_confirmar_carrito_db_error_capturado -v
```
Expected: FAIL — la excepción se propaga en lugar de ser capturada.

- [ ] **Step 4: Wrappear `obtener_pedido_mas_reciente` en try/except**

En `confirmar_carrito`, reemplazar:

```python
    pedido_activo = gestor_pedidos.obtener_pedido_mas_reciente(user_id)
    if pedido_activo is None:
        logger.error("confirmar_carrito: no active order found for user %s", user_id)
        return False, "No se encontró un pedido activo para este usuario"
```

por:

```python
    try:
        pedido_activo = gestor_pedidos.obtener_pedido_mas_reciente(user_id)
    except (SQLAlchemyError, OperationalError, RetryError) as e:
        logger.error("confirmar_carrito: DB error obteniendo pedido usuario=%s: %s", user_id, e)
        return False, "Error de base de datos. Intente más tarde."
    if pedido_activo is None:
        logger.error("confirmar_carrito: no active order found for user %s", user_id)
        return False, "No se encontró un pedido activo para este usuario"
```

- [ ] **Step 5: Wrappear `fijar_carrito_confirmado` en try/except**

Reemplazar:

```python
    # Single atomic commit: redisID + coordinates + state transition to ENLACE2.
    gestor_pedidos.fijar_carrito_confirmado(pedido_id_db, pedido_id_redis, lat=lat, lng=lng)
    logger.info("CARRITO_CONFIRMADO pedido_id=%s", pedido_id_db)
```

por:

```python
    # Single atomic commit: redisID + coordinates + state transition to ENLACE2.
    try:
        gestor_pedidos.fijar_carrito_confirmado(pedido_id_db, pedido_id_redis, lat=lat, lng=lng)
    except (SQLAlchemyError, OperationalError, RetryError) as e:
        logger.error("confirmar_carrito: DB error en fijar_carrito_confirmado pedido=%s: %s", pedido_id_db, e)
        return False, "Error de base de datos al confirmar el carrito. Intente más tarde."
    logger.info("CARRITO_CONFIRMADO pedido_id=%s", pedido_id_db)
```

- [ ] **Step 6: Verificar que el nuevo test pasa**

```bash
pytest tests/test_api_pedido.py::TestConfirmarCarrito::test_confirmar_carrito_db_error_capturado -v
```
Expected: PASS.

- [ ] **Step 7: Ejecutar suite completa**

```bash
pytest tests/test_api_pedido.py -v --tb=short
```
Expected: sin nuevas regresiones.

- [ ] **Step 8: Commit**

```bash
git add controllers/pedido.py tests/test_api_pedido.py
git commit -m "fix: try/except en obtener_pedido_mas_reciente y fijar_carrito_confirmado — DB errors no propagan al blueprint (H4)"
```

---

## Task 4: H3 — Invertir orden Redis/DB en `confirmar_carrito`

**Files:**
- Modify: `controllers/pedido.py:149-170` (reordenar `cache.set` después de `fijar_carrito_confirmado`)

**Contexto:** Actualmente Redis se escribe antes de que DB confirme. Si Maps tarda y SQL Server cae en esa ventana, Redis tiene el carrito pero DB no ha transitado. La geocodificación no tiene side-effects, así que moverla antes de DB es correcto.

Orden objetivo:
1. `geocodificar_direccion` (sin side-effects)
2. `fijar_carrito_confirmado` (DB — operación crítica)
3. `cache.set` (Redis — solo si DB confirma)

- [ ] **Step 1: Reordenar las operaciones en `confirmar_carrito`**

Reemplazar el bloque completo desde `cache.set` hasta el final de la función:

```python
    cache.set(
        pedido_id_redis,
        json.dumps({
            "name": name,
            "token": token,
            "userID": user_id,
            "pedidoID": pedido_id_db,
            "numero": numero,
            "direccion": direccion,
            "productos": productos,
            "total": total,
        }),
        ex=3600,
    )

    coords = geocodificar_direccion(direccion)
    lat, lng = (coords[0], coords[1]) if coords else (None, None)
    if not coords:
        logger.warning("confirmar_carrito: no se pudieron geocodificar las coordenadas del pedido %s", pedido_id_db)

    # Single atomic commit: redisID + coordinates + state transition to ENLACE2.
    try:
        gestor_pedidos.fijar_carrito_confirmado(pedido_id_db, pedido_id_redis, lat=lat, lng=lng)
    except (SQLAlchemyError, OperationalError, RetryError) as e:
        logger.error("confirmar_carrito: DB error en fijar_carrito_confirmado pedido=%s: %s", pedido_id_db, e)
        return False, "Error de base de datos al confirmar el carrito. Intente más tarde."
    logger.info("CARRITO_CONFIRMADO pedido_id=%s", pedido_id_db)

    confirmacion_url = f"{public_url}/confirmacion_pago?pedido_id={pedido_id_redis}"
    return True, confirmacion_url
```

por:

```python
    coords = geocodificar_direccion(direccion)
    lat, lng = (coords[0], coords[1]) if coords else (None, None)
    if not coords:
        logger.warning("confirmar_carrito: no se pudieron geocodificar las coordenadas del pedido %s", pedido_id_db)

    # DB primero: la transición de estado es la operación crítica.
    try:
        gestor_pedidos.fijar_carrito_confirmado(pedido_id_db, pedido_id_redis, lat=lat, lng=lng)
    except (SQLAlchemyError, OperationalError, RetryError) as e:
        logger.error("confirmar_carrito: DB error en fijar_carrito_confirmado pedido=%s: %s", pedido_id_db, e)
        return False, "Error de base de datos al confirmar el carrito. Intente más tarde."

    # Redis solo si DB confirma — el carrito es cache recuperable.
    cache.set(
        pedido_id_redis,
        json.dumps({
            "name": name,
            "token": token,
            "userID": user_id,
            "pedidoID": pedido_id_db,
            "numero": numero,
            "direccion": direccion,
            "productos": productos,
            "total": total,
        }),
        ex=3600,
    )
    logger.info("CARRITO_CONFIRMADO pedido_id=%s", pedido_id_db)

    confirmacion_url = f"{public_url}/confirmacion_pago?pedido_id={pedido_id_redis}"
    return True, confirmacion_url
```

- [ ] **Step 2: Ejecutar suite completa para verificar que el reordenamiento no rompe tests**

```bash
pytest tests/test_api_pedido.py -v --tb=short
```
Expected: todos los tests siguen en verde. El mock de `fijar_carrito_confirmado` devuelve `True` en todos los tests que llegan hasta ese punto, por lo que la lógica no cambia desde la perspectiva de los tests.

- [ ] **Step 3: Commit**

```bash
git add controllers/pedido.py
git commit -m "fix: invertir orden Redis/DB en confirmar_carrito — DB confirma antes de escribir en cache (H3)"
```

---

## Task 5: H5 — Prevenir tokens huérfanos en `procesar_pedido`

**Files:**
- Modify: `controllers/pedido.py:43-54` (añadir verificación de estado antes de generar token)

**Contexto:** Meta puede reintentar el webhook. Si el pedido ya transitó a `ENLACE`, el segundo reintento llama `generar_enlace` (crea token en Redis con TTL 24h) y luego `iniciar_enlace` devuelve `False` porque el estado ya no es `PENDIENTE`. El token queda huérfano. La fix: verificar el estado del pedido con una query antes de generar el token.

- [ ] **Step 1: Reemplazar el bloque de generación de enlace**

En `controllers/pedido.py`, dentro de `procesar_pedido`, reemplazar:

```python
                if mensaje_respuesta == "Tienda online":
                    try:
                        enlace = generar_enlace(item, usuario_datos)
                        if not gestor_pedidos.iniciar_enlace(datos.id_pedido_actual, enlace):
                            return "❌ Ocurrió un error al procesar la opción. Intente nuevamente."
                        logger.info(
                            "PEDIDO_INICIADO pedido_id=%s usuario=%s",
                            datos.id_pedido_actual, datos.numero_cliente,
                        )
                        return f"❕ {mensaje_respuesta} ❕\n\n🔗 *Enlace único*: {enlace}"
                    except (ValueError, SQLAlchemyError, OperationalError) as e:
                        logger.error("Error al generar el enlace [%s]: %s", type(e).__name__, e)
                        return "❌ Error inesperado. Intente nuevamente."
```

por:

```python
                if mensaje_respuesta == "Tienda online":
                    try:
                        pedido_actual = gestor_pedidos.obtener_pedido(datos.id_pedido_actual)
                        if not pedido_actual or pedido_actual.Estado != EstadoPedido.PENDIENTE:
                            logger.warning(
                                "procesar_pedido: pedido %s en estado inesperado, no se genera enlace",
                                datos.id_pedido_actual,
                            )
                            return "❌ Ocurrió un error al procesar la opción. Intente nuevamente."
                        enlace = generar_enlace(item, usuario_datos)
                        if not gestor_pedidos.iniciar_enlace(datos.id_pedido_actual, enlace):
                            return "❌ Ocurrió un error al procesar la opción. Intente nuevamente."
                        logger.info(
                            "PEDIDO_INICIADO pedido_id=%s usuario=%s",
                            datos.id_pedido_actual, datos.numero_cliente,
                        )
                        return f"❕ {mensaje_respuesta} ❕\n\n🔗 *Enlace único*: {enlace}"
                    except (ValueError, SQLAlchemyError, OperationalError) as e:
                        logger.error("Error al generar el enlace [%s]: %s", type(e).__name__, e)
                        return "❌ Error inesperado. Intente nuevamente."
```

- [ ] **Step 2: Ejecutar suite completa para verificar sin regresiones**

```bash
pytest tests/ -v --tb=short -q
```
Expected: sin nuevas regresiones.

- [ ] **Step 3: Commit**

```bash
git add controllers/pedido.py
git commit -m "fix: verificar estado pedido antes de generar enlace — previene tokens huérfanos en reintentos Meta (H5)"
```

---

## Task 6: H1 + H7 — Extraer `confirmar_carrito` y `_validar_productos` a `controllers/carrito.py`

**Files:**
- Create: `controllers/carrito.py`
- Modify: `controllers/pedido.py` — eliminar las dos funciones
- Modify: `blueprints/api/cart.py:11` — cambiar import
- Modify: `tests/test_api_pedido.py` — cambiar imports en `TestConfirmarCarrito`

**Contexto (H7):** En el mismo movimiento renombramos el parámetro `gestor_pedidos` a `pedidos_manager` en la firma de `confirmar_carrito` para eliminar el shadowing del global del módulo. Hay que actualizar los call-sites que usan el kwarg.

Call-sites a actualizar:
- `blueprints/api/cart.py` línea 55: `gestor_pedidos=gestor_pedidos` → `pedidos_manager=gestor_pedidos`
- `tests/test_api_pedido.py`: todos los calls de `confirmar_carrito(..., gestor_pedidos=..., ...)`

- [ ] **Step 1: Crear `controllers/carrito.py` con el contenido movido**

Crear el archivo `/home/siemprearmando/test/panchi-bot/controllers/carrito.py` con el siguiente contenido (es el código actual de `confirmar_carrito` + `_validar_productos` ya con el renombre de parámetro):

```python
import json
import logging

from sqlalchemy.exc import SQLAlchemyError, OperationalError
from tenacity import RetryError
from maps_module import geocodificar_direccion
from states import EstadoPedido

logger = logging.getLogger(__name__)


def _validar_productos(productos_recibidos: list, gestor_productos) -> tuple:
    """Valida cada producto contra la BD y construye la lista con precios confirmados.

    Devuelve (True, lista_productos) o (False, mensaje_error).
    """
    productos = []
    total = 0.0

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

        removed = p.get("ingredientes_removidos", [])
        notas   = f"Sin: {', '.join(removed)}" if removed else ""
        productos.append({
            "nombre": nombre_producto,
            "cantidad": cantidad,
            "precio": precio_total,
            "codigo": codigo,
            "notas": notas,
        })
        total += precio_total

    return True, (productos, round(total, 2))


def confirmar_carrito(
    pedido_id_redis: str,
    name: str,
    token: str,
    user_id,
    numero: str,
    direccion: str,
    productos_recibidos: list,
    cache,
    pedidos_manager,
    gestor_productos,
    public_url: str,
) -> tuple:
    """Guarda el carrito validado, calcula su total y lo deja listo para confirmar."""
    if not productos_recibidos:
        logger.warning("confirmar_carrito: carrito vacío para usuario %s", user_id)
        return False, "El carrito no puede estar vacío"

    ok, resultado = _validar_productos(productos_recibidos, gestor_productos)
    if not ok:
        return False, resultado
    productos, total = resultado

    try:
        pedido_activo = pedidos_manager.obtener_pedido_mas_reciente(user_id)
    except (SQLAlchemyError, OperationalError, RetryError) as e:
        logger.error("confirmar_carrito: DB error obteniendo pedido usuario=%s: %s", user_id, e)
        return False, "Error de base de datos. Intente más tarde."
    if pedido_activo is None:
        logger.error("confirmar_carrito: no active order found for user %s", user_id)
        return False, "No se encontró un pedido activo para este usuario"

    pedido_id_db = pedido_activo.PedidoID

    if pedido_activo.Estado != EstadoPedido.ENLACE:
        logger.warning(
            "confirmar_carrito: cannot transition order %s from state '%s' to ENLACE2",
            pedido_id_db,
            pedido_activo.Estado,
        )
        return False, "El pedido no se encuentra en el estado correcto para confirmar el carrito"

    coords = geocodificar_direccion(direccion)
    lat, lng = (coords[0], coords[1]) if coords else (None, None)
    if not coords:
        logger.warning("confirmar_carrito: no se pudieron geocodificar las coordenadas del pedido %s", pedido_id_db)

    # DB primero: la transición de estado es la operación crítica.
    try:
        pedidos_manager.fijar_carrito_confirmado(pedido_id_db, pedido_id_redis, lat=lat, lng=lng)
    except (SQLAlchemyError, OperationalError, RetryError) as e:
        logger.error("confirmar_carrito: DB error en fijar_carrito_confirmado pedido=%s: %s", pedido_id_db, e)
        return False, "Error de base de datos al confirmar el carrito. Intente más tarde."

    # Redis solo si DB confirma — el carrito es cache recuperable.
    cache.set(
        pedido_id_redis,
        json.dumps({
            "name": name,
            "token": token,
            "userID": user_id,
            "pedidoID": pedido_id_db,
            "numero": numero,
            "direccion": direccion,
            "productos": productos,
            "total": total,
        }),
        ex=3600,
    )
    logger.info("CARRITO_CONFIRMADO pedido_id=%s", pedido_id_db)

    confirmacion_url = f"{public_url}/confirmacion_pago?pedido_id={pedido_id_redis}"
    return True, confirmacion_url
```

- [ ] **Step 2: Actualizar el import en `blueprints/api/cart.py`**

Reemplazar:

```python
from controllers.pedido import confirmar_carrito
```

por:

```python
from controllers.carrito import confirmar_carrito
```

Y actualizar el call-site (línea ~55) cambiando el kwarg `gestor_pedidos` a `pedidos_manager`:

```python
        success, result = confirmar_carrito(
            pedido_id_redis=pedido_id_redis,
            name=data.get("name", "Nombre no especificado"),
            token=data.get("token", ""),
            user_id=token_user_id,
            numero=data.get("numero", "Numero no especificado"),
            direccion=data.get("direccion", "Dirección no especificada"),
            productos_recibidos=data.get("productos", []),
            cache=cache,
            pedidos_manager=gestor_pedidos,
            gestor_productos=gestor_productos,
            public_url=config.PUBLIC_URL or "",
        )
```

- [ ] **Step 3: Actualizar imports y call-sites en `tests/test_api_pedido.py`**

En cada método de `TestConfirmarCarrito` que llama a `confirmar_carrito`:
- Cambiar `from controllers.pedido import confirmar_carrito` → `from controllers.carrito import confirmar_carrito`
- Cambiar `gestor_pedidos=gestor` → `pedidos_manager=gestor` (y `gestor_pedidos=MagicMock()` → `pedidos_manager=MagicMock()`)

Los métodos afectados son todos los de `TestConfirmarCarrito`:
`test_happy_path_returns_true_and_url`, `test_cart_stored_in_cache`, `test_state_transition_to_enlace2_called`, `test_wrong_state_does_not_call_fijar_carrito_confirmado`, `test_no_active_order_returns_false`, `test_confirmacion_ignora_precio_frontend`, `test_confirmacion_codigo_ausente_devuelve_error`, `test_confirmacion_cantidad_cero_devuelve_error`, `test_confirmacion_producto_no_encontrado_devuelve_error`, `test_confirmacion_precio_null_devuelve_error`, `test_confirmar_carrito_vacio_rechazado`, `test_confirmar_carrito_db_error_capturado`.

- [ ] **Step 4: Eliminar `confirmar_carrito` y `_validar_productos` de `controllers/pedido.py`**

Borrar el bloque completo desde la línea `def _validar_productos(...)` hasta el final del archivo (incluyendo `confirmar_carrito`). También eliminar los imports que solo usaban esas funciones:

- `from maps_module import geocodificar_direccion` — eliminar (solo lo usaba `confirmar_carrito`)
- `from states import EstadoPedido` — **conservar** (lo usa `procesar_pedido` → no, no lo usa... verificar)

Verificar si `EstadoPedido` sigue siendo necesario en `pedido.py` después de la extracción. Si `procesar_pedido` no lo usa, eliminar ese import también.

- [ ] **Step 5: Ejecutar todos los tests**

```bash
pytest tests/test_api_pedido.py -v --tb=short
```
Expected: todos los tests en verde, incluyendo los de `TestConfirmarCarrito` que ahora importan desde `controllers.carrito`.

- [ ] **Step 6: Ejecutar suite completa**

```bash
pytest tests/ -v --tb=short -q
```
Expected: sin nuevas regresiones.

- [ ] **Step 7: Commit**

```bash
git add controllers/carrito.py controllers/pedido.py blueprints/api/cart.py tests/test_api_pedido.py
git commit -m "refactor: extraer confirmar_carrito a controllers/carrito.py; renombrar param gestor_pedidos→pedidos_manager (H1, H7)"
```

---

## Self-Review

### Spec coverage

| Hallazgo | Severidad | Tarea |
|----------|-----------|-------|
| H1 — dos flujos en un módulo | Alta | Task 6 |
| H2 — carrito vacío aceptado | Crítica | Task 2 |
| H3 — Redis antes de DB | Alta | Task 4 |
| H4 — DB errors no capturados | Alta | Task 3 |
| H5 — tokens huérfanos | Media | Task 5 |
| H6 — N+1 en `_validar_productos` | Media | **no incluido** — la auditoría lo marca como "no urgente con catálogo actual" |
| H7 — shadowing de parámetro | Media | Task 6 (junto con H1) |
| H8 — XSS en notas/nombre | Media | **no incluido** — la auditoría dice "no confirmado, verificar templates" |
| H9 — logging faltante | Baja | Task 1 |

H6 y H8 quedan fuera del plan porque la auditoría los marca explícitamente como fuera del refactor mínimo.

### Placeholder scan

Sin TODOs, TBDs ni referencias a código no definido.

### Type consistency

- `confirmar_carrito` en Task 6 usa `pedidos_manager` en la firma y en todos los call-sites — consistente.
- `_validar_productos` mantiene la misma firma en `carrito.py` — consistente con los tests existentes que no la llaman directamente.
- `PRODUCTOS_RECIBIDOS` de `test_api_pedido.py` se reutiliza en los tests actualizados — consistente.
