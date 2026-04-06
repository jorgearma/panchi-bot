# Auditoría de `controllers/pago.py`

> Auditoría técnica estricta. Fecha: 2026-04-06.
> Archivos analizados: `controllers/pago.py`, `controllers/pago_notifier.py`, `services/monei_service.py`, `states.py`.

---

## 1. Rol del archivo

**Responsabilidad principal:** Orquestador de los dos flujos de confirmación de pago: online via Monei (`iniciar_pago`) y contra reembolso en efectivo (`iniciar_pago_efectivo`). Incluye la validación de precios del carrito contra DB.

**Qué debería hacer:** Validar carrito, crear el cobro en Monei o confirmar el efectivo, hacer avanzar el estado del pedido en DB, notificar al cliente.

**Qué no debería hacer:** Aceptar parámetros que no usa, dejar flujos sin protección ante fallos parciales después de escribir en sistemas externos, devolver tipos inconsistentes en el retorno de la guardia de idempotencia.

**Dependencias clave:**
- `gestor_pedidos`, `gestor_productos` — inyectados como parámetros (correcto)
- `services/monei_service.py` — adaptador del SDK de Monei
- `controllers/pago_notifier.py` — notificación WhatsApp del pedido en efectivo
- `states.EstadoPedido` — enum de estados

**Nivel de criticidad: Crítico** — Es el punto donde se crea el cobro real en Monei y donde un pedido pasa a `CONFIRMANDO_PAGO` o `CONTRA_REEMBOLSO`. Cualquier inconsistencia aquí tiene impacto económico directo.

---

## 2. Lo que hace bien

- Diseño de dependencias excelente: todas las dependencias externas (DB, Redis, Monei, URL base) se reciben como parámetros en ambas funciones — sin globales de `container`. Es el controlador más testeable de los auditados hasta ahora.
- El orden correcto en `iniciar_pago`: Monei **antes** que DB (comentado explícitamente en líneas 74-75). Si Monei falla, la DB no se toca y el retry es limpio.
- `_validar_carrito` recalcula precios desde DB — previene manipulación client-side del importe enviado a Monei.
- Guardia de estado correcta: líneas 55-63 en `iniciar_pago` y líneas 123-128 en `iniciar_pago_efectivo` impiden transiciones desde estados incorrectos.
- `confirmar_pago_efectivo` se llama **antes** de la notificación WhatsApp (línea 138 antes de 145) — el pedido queda en DB aunque falle el mensaje.
- `logger.info("PAGO_INICIADO")` documenta el evento de negocio más importante del flujo online.

---

## 3. Hallazgos

### Hallazgo 1

**Tipo:** consistencia / errores
**Severidad: Alta**

**Problema:** En `iniciar_pago_efectivo`, `_enviar_confirmacion_efectivo` (línea 145) se llama después de que `confirmar_pago_efectivo` ya persistió el pedido como `CONTRA_REEMBOLSO`. Si el envío WhatsApp falla (API caída, red, etc.), la excepción se propaga sin capturar. El blueprint recibe un 500 y el cliente ve un error genérico de "algo salió mal". El pedido **sí está confirmado** en DB, pero el cliente no lo sabe y el retry está bloqueado: si intenta de nuevo, el estado ya no es `ENLACE2` sino `CONTRA_REEMBOLSO`, y `iniciar_pago_efectivo` devuelve `False, "El pedido no está listo para confirmar"`. El cliente queda atrapado: pedido real en sistema, sin confirmación en pantalla.

**Evidencia:**
```python
# líneas 138-148 — sin try/except en la notificación
ok = gestor_pedidos.confirmar_pago_efectivo(
    pedido_id, productos_validos, notas=notas or None
)
if not ok:
    return False, "Error al registrar el pedido contra reembolso"

total_euros = round(total_calculado, 2)
_enviar_confirmacion_efectivo(...)  # ← si lanza, 500 con pedido ya confirmado en DB
```

**Impacto real:** Un fallo puntual de la API de WhatsApp en el momento del checkout en efectivo hace que el cliente tenga un pedido activo en el sistema sin saberlo y sin poder continuar. El equipo de operaciones ve el pedido, el cliente no.

**Recomendación mínima concreta:**
```python
try:
    _enviar_confirmacion_efectivo(numero_cliente, nombre_cliente, total_euros, pedido_id, direccion_cliente)
except Exception as e:
    logger.error(
        "CONFIRMACION_EFECTIVO_WA_FALLIDA pedido=%s error=%s",
        pedido_id, e, exc_info=True
    )
    # El pedido está confirmado — devolver True igual, el cliente verá la confirmación web
return True, f"{public_url}/pago_confirmado?pedido_id={redis_id}"
```

---

### Hallazgo 2

**Tipo:** consistencia / seguridad
**Severidad: Alta**

**Problema:** La guardia de idempotencia en `iniciar_pago` (líneas 55-56) devuelve `(True, "El pedido ya está en proceso de pago.")` — un string de texto como segundo elemento de la tupla. El contrato del caller espera `(True, redirect_url)` para redirigir al cliente al pago. Si el caller hace `return redirect(url)` con este valor, intenta redirigir a la cadena de texto como URL.

**Evidencia:**
```python
# líneas 55-56
if pedido_activo.Estado == EstadoPedido.CONFIRMANDO_PAGO:
    return True, "El pedido ya está en proceso de pago."  # ← no es una URL

# Contraste con el retorno normal:
# línea 102
return True, redirect_url  # ← esto sí es URL
```

**Impacto real:** Posible riesgo no confirmado sin leer el blueprint caller. Si el caller hace `redirect(url)` con el string de texto, el navegador del cliente recibe una redirección a una URL inválida. Si el caller hace `if ok: return jsonify({"url": url})`, el cliente web recibe el string de texto en lugar de la URL de Monei y el botón de pago queda roto.

**Recomendación mínima concreta:** Obtener y devolver la URL de pago real del pedido en lugar de un string de mensaje. Si no está disponible en DB, redirigir a una página de "pago en curso":
```python
if pedido_activo.Estado == EstadoPedido.CONFIRMANDO_PAGO:
    enlace_pago = pedido_activo.enlace  # la URL de Monei ya guardada
    logger.info("PAGO_YA_INICIADO pedido=%s", pedido_activo.PedidoID)
    return True, enlace_pago or f"{public_url}/pago_en_curso"
```

---

### Hallazgo 3

**Tipo:** consistencia / seguridad
**Severidad: Alta**

**Problema:** `_validar_carrito` no valida que `productos_recibidos` sea una lista no vacía. Con lista vacía, el loop no itera, devuelve `([], 0.0, None)`. Esto lleva a `amount_in_cents = 0` y se crea un pago en Monei por **0 céntimos**. Dependiendo de la respuesta de Monei, puede crearse un pago válido con importe cero o lanzar un `ApiException`.

**Evidencia:**
```python
# líneas 17-33 — sin guardia de lista vacía
def _validar_carrito(productos_recibidos, gestor_productos):
    productos_validos = []
    total = 0.0
    for item in productos_recibidos:  # ← vacío = no itera
        ...
    return productos_validos, total, None  # ← ([], 0.0, None) — sin error

# línea 72
amount_in_cents = int(round(total_calculado * 100))  # ← 0 céntimos
```

**Impacto real:** Idéntico al Hallazgo 2 de `controllers/pedido.py` auditado previamente — pago de 0€ en Monei, pedido en `CONFIRMANDO_PAGO` con 0 artículos. La duplicidad de la función `_validar_carrito` / `_validar_productos` sin coordinar las guardias crea el mismo bug dos veces.

**Recomendación mínima concreta:**
```python
def _validar_carrito(productos_recibidos, gestor_productos):
    if not productos_recibidos:
        return None, None, "El carrito no puede estar vacío"
    ...
```

---

### Hallazgo 4

**Tipo:** consistencia / seguridad
**Severidad: Media**

**Problema:** `cantidad` en `_validar_carrito` (línea 21) se obtiene con `item.get("cantidad", 1)` sin validar que sea positivo. Un valor `cantidad: -1` o `cantidad: 0` produce un `total` negativo o cero. Con `cantidad: -3` y un producto de 10€ se obtiene `total = -30€`, `amount_in_cents = -3000`, que se envía a Monei sin ningún filtro.

**Evidencia:**
```python
# línea 21 — sin validación de signo
cantidad = item.get("cantidad", 1)
# línea 27 — operación directa con valor no validado
total += float(producto_db["Precio"]) * cantidad
```

**Impacto real:** Pago con importe negativo enviado a Monei. Comportamiento indefinido: puede fallar con ApiException, puede crear un abono en lugar de un cargo, o puede rechazarse silenciosamente.

**Recomendación mínima concreta:**
```python
cantidad = item.get("cantidad", 1)
if not isinstance(cantidad, int) or cantidad <= 0:
    return None, None, f"Cantidad inválida para el producto {codigo}"
```

---

### Hallazgo 5

**Tipo:** consistencia
**Severidad: Media**

**Problema:** Si `gestor_pedidos.confirmar_pago_online` devuelve `False` (líneas 95-96), se devuelve el error **sin logging**. En este punto Monei ya creó el pago — hay un cobro pendiente en Monei sin un pedido en `CONFIRMANDO_PAGO` en DB. El cliente no puede reintentar (la guardia de `ENLACE2` en línea 58 ya no aplica si el estado avanzó parcialmente, o sigue bloqueado si no avanzó). No hay ninguna traza en logs que permita detectar esta situación.

**Evidencia:**
```python
# líneas 92-96
ok = gestor_pedidos.confirmar_pago_online(
    pedido_activo_id, productos_validos, redirect_url, notas=notas or None
)
if not ok:
    return False, "Error al registrar el pedido tras el pago"  # ← sin logger
```

**Impacto real:** Pago creado en Monei sin orden correspondiente en DB. El cliente recibe un error pero puede tener un cargo pendiente. Sin log, el equipo de soporte no tiene trazabilidad para investigar.

**Recomendación mínima concreta:**
```python
if not ok:
    logger.error(
        "CONFIRMAR_PAGO_ONLINE_FALLIDO pedido=%s importe=%s monei_url=%s",
        pedido_activo_id, amount_in_cents, redirect_url
    )
    return False, "Error al registrar el pedido tras el pago"
```

---

### Hallazgo 6

**Tipo:** diseño
**Severidad: Media**

**Problema:** El parámetro `cache` aparece en la firma de `iniciar_pago` (línea 42) y de `iniciar_pago_efectivo` (línea 111) pero **no se usa en ninguna de las dos funciones**. Es un parámetro muerto que infla la interfaz sin propósito.

**Evidencia:**
```python
# línea 36-48 — cache declarado pero nunca referenciado en el cuerpo
def iniciar_pago(
    user_id,
    productos_recibidos: list,
    ...
    cache,              # ← no se usa
    gestor_pedidos,
    ...
```
No hay ninguna línea `cache.` en el cuerpo de ninguna de las dos funciones.

**Impacto real:** Cualquier caller debe pasar `cache` o recibirá `TypeError`. Tests deben mockear un objeto que no se usa. Si el parámetro se añadió "por si acaso" para coherencia con `confirmar_carrito`, la razón ya no aplica.

**Recomendación mínima concreta:** Eliminar `cache` de las firmas de `iniciar_pago` e `iniciar_pago_efectivo` y actualizar los callers en `blueprints/api/`.

---

### Hallazgo 7

**Tipo:** consistencia
**Severidad: Media**

**Problema:** Las dos funciones de validación de carrito en el proyecto usan nombres de clave distintos para el mismo campo: `_validar_carrito` en este archivo usa `"codigo"` (minúsculas, línea 20) mientras que `_validar_productos` en `controllers/pedido.py` usa `"Codigo"` (mayúscula inicial). El mismo carrito enviado desde el frontend con una clave concreta solo funcionará en uno de los dos flujos.

**Evidencia:**
```python
# pago.py línea 20
codigo = item.get("codigo")       # ← minúsculas

# pedido.py línea 72
codigo = p.get("Codigo")          # ← mayúscula inicial
```

**Impacto real:** Si el frontend envía `{"Codigo": 1}`, `pago.py` lo trata como `None` → "Producto con código None no encontrado". Si envía `{"codigo": 1}`, `pedido.py` lo trata como `None`. Uno de los dos flujos de validación siempre falla silenciosamente si el frontend no sabe exactamente qué key usar para cada endpoint.

**Recomendación mínima concreta:** Estandarizar a `"codigo"` (minúsculas) en ambos archivos, o definir el schema de producto en un `TypedDict` o Pydantic en `schemas/` que ambas funciones usen.

---

### Hallazgo 8

**Tipo:** errores
**Severidad: Media**

**Problema:** `gestor_pedidos.obtener_pedido_mas_reciente` (línea 50 en `iniciar_pago`, línea 118 en `iniciar_pago_efectivo`) y `gestor_pedidos.confirmar_pago_online` / `confirmar_pago_efectivo` no están envueltos en try/except. Si `tenacity` agota sus reintentos y lanza la excepción final, se propaga sin capturar al blueprint.

**Evidencia:**
```python
# línea 50 — sin try/except
pedido_activo = gestor_pedidos.obtener_pedido_mas_reciente(user_id)

# línea 92 — sin try/except
ok = gestor_pedidos.confirmar_pago_online(...)
```

**Impacto real:** Caída de SQL Server durante el checkout → excepción no capturada → 500 en el cliente web durante el proceso de pago. Para `iniciar_pago`, si ocurre después de crear el pago en Monei, el usuario tiene un cobro pendiente y un error en pantalla.

**Recomendación mínima concreta:**
```python
from sqlalchemy.exc import SQLAlchemyError
from tenacity import RetryError

try:
    pedido_activo = gestor_pedidos.obtener_pedido_mas_reciente(user_id)
except (SQLAlchemyError, RetryError) as e:
    logger.error("iniciar_pago: DB error para usuario %s: %s", user_id, e)
    return False, "Error de base de datos. Intente más tarde."
```

---

### Hallazgo 9

**Tipo:** observabilidad
**Severidad: Baja**

**Problema:** El path de idempotencia en `iniciar_pago` (líneas 55-56) no tiene logging. Si un cliente llega dos veces al checkout, no hay trazabilidad de cuántas veces ocurre esto ni si es un bug de frontend o un comportamiento esperado.

**Evidencia:**
```python
# líneas 55-56 — sin logger
if pedido_activo.Estado == EstadoPedido.CONFIRMANDO_PAGO:
    return True, "El pedido ya está en proceso de pago."
```

**Impacto real:** Bajo. Dificulta detectar si hay un doble-submit sistemático desde el frontend.

**Recomendación mínima concreta:**
```python
logger.info("PAGO_YA_INICIADO pedido=%s usuario=%s", pedido_activo.PedidoID, user_id)
```

---

## 4. Riesgos principales si no se toca

| Riesgo | Escenario concreto |
|--------|-------------------|
| Pedido confirmado en efectivo sin que el cliente lo sepa | WhatsApp API falla tras `confirmar_pago_efectivo` → 500 → cliente no puede reintentar porque estado cambió a `CONTRA_REEMBOLSO` |
| Caller redirige a string de texto | `iniciar_pago` con estado `CONFIRMANDO_PAGO` devuelve texto como URL → redirección rota en el cliente web |
| Pago de 0€ en Monei | Frontend envía carrito vacío → `_validar_carrito` no detecta lista vacía → `amount_in_cents = 0` |
| Pago de importe negativo en Monei | `cantidad: -1` en el request → total negativo → Monei recibe importe negativo |
| Cobro en Monei sin orden en DB sin log | `confirmar_pago_online` devuelve False después de crear el pago → sin trazabilidad para soporte |
| Frontend incompatible con un endpoint | Clave `"Codigo"` vs `"codigo"` → uno de los dos flujos de validación siempre recibe `None` |

---

## 5. Refactor mínimo recomendado

### Qué tocar primero (en orden de impacto)

1. **Wrappear `_enviar_confirmacion_efectivo` en try/except** (Hallazgo 1). Cuatro líneas. Evita que el cliente quede atrapado con un pedido confirmado que no puede ver.

2. **Corregir el retorno de la guardia de idempotencia** (Hallazgo 2). Una línea: devolver `pedido_activo.enlace` en lugar del string de texto.

3. **Añadir guardia de lista vacía** en `_validar_carrito` (Hallazgo 3). Dos líneas. Misma corrección que en `pedido.py:_validar_productos`.

4. **Validar `cantidad > 0`** en `_validar_carrito` (Hallazgo 4). Tres líneas.

5. **Añadir log al path `ok=False` de `confirmar_pago_online`** (Hallazgo 5). Una línea. Trazabilidad crítica para soporte cuando hay cobro sin orden.

6. **Eliminar el parámetro `cache`** de ambas firmas (Hallazgo 6). Actualizar callers.

7. **Estandarizar la clave `"codigo"`** entre `_validar_carrito` y `_validar_productos` (Hallazgo 7). Una línea en `pedido.py` si se elige `"codigo"` como estándar.

### Qué NO tocar todavía

- El orden Monei→DB en `iniciar_pago` — es correcto y está bien documentado.
- El diseño de parámetros inyectables — es el mejor de todos los controladores auditados.
- La lógica de `_validar_carrito` más allá de las guardias — recalcula precios desde DB correctamente.
- Los logs de `PAGO_INICIADO` y `iniciar_pago_efectivo: pedido confirmado` — están bien.

---

## 6. Tests que deberían existir

- `test_iniciar_pago_carrito_vacio_rechazado`: `productos_recibidos=[]` → devuelve `False`.
- `test_iniciar_pago_cantidad_negativa_rechazada`: `cantidad=-1` → devuelve `False`.
- `test_iniciar_pago_idempotente_devuelve_url`: estado `CONFIRMANDO_PAGO` → devuelve `True` y una URL válida (no un string de mensaje).
- `test_iniciar_pago_monei_falla_db_sin_cambios`: `monei_crear_pago` devuelve error → `confirmar_pago_online` nunca se llama.
- `test_iniciar_pago_efectivo_wa_falla_devuelve_ok`: `_enviar_confirmacion_efectivo` lanza → función devuelve `True` igualmente (pedido confirmado).
- `test_iniciar_pago_efectivo_doble_llamada`: dos llamadas simultáneas → solo una confirma el pedido.
- `test_validar_carrito_precio_desde_db`: precio manipulado en el request → el importe final usa el precio de DB.
- `test_iniciar_pago_db_error_capturado`: `obtener_pedido_mas_reciente` lanza `SQLAlchemyError` → devuelve `False`, no propaga excepción.

---

## 7. Veredicto final

**Estado general del archivo:** El mejor diseñado de los controladores auditados (sin globales, dependencias inyectables, orden correcto Monei→DB). Sin embargo, tiene tres bugs activos con impacto real en producción: el Hallazgo 1 puede dejar a un cliente atrapado con un pedido confirmado que no puede ver, el Hallazgo 2 puede romper la redirección del pago en el flujo de idempotencia y el Hallazgo 3/4 permite pagos de 0€ o negativos en Monei.

**¿Bloquea crecimiento?** No. La estructura es sólida para añadir nuevas formas de pago siguiendo el mismo patrón.

**¿Bloquea testeo?** No. Es el controlador más testeable del proyecto — todas las dependencias son inyectables.

**¿Tiene riesgo operativo real?** Sí. El Hallazgo 1 (cliente atrapado tras fallo de WhatsApp) y el Hallazgo 2 (URL inválida en idempotencia) son bugs que pueden activarse en producción con fallos puntuales de la API de WhatsApp o con doble-submit desde el frontend.
