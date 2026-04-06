# Diseño: Corrección de hallazgos — `controllers/pago.py`

> Fecha: 2026-04-06  
> Auditoría base: `docs/auditoria/controllers/auditoria_controllers_pago.md`  
> Alcance: H1, H2, H3, H4, H5, H6, H8, H9. H7 (estandarización `"codigo"`) queda para auditoría de `pedido.py`. Tests en ticket separado.

---

## Archivos modificados

| Archivo | Acción |
|---------|--------|
| `controllers/pago.py` | Modificar — todos los hallazgos excepto H7 |
| `blueprints/api/payments.py` | Modificar — H2 (eliminar string comparison) y H6 (eliminar `cache=cache`) |

---

## Hallazgos y cambios

### H3 — Guardia de lista vacía en `_validar_carrito`

Sin esta guardia, un carrito vacío pasa la validación con `([], 0.0, None)` → `amount_in_cents = 0` → pago de 0€ en Monei.

**Cambio:** Al inicio de `_validar_carrito`, antes del loop:
```python
if not productos_recibidos:
    return None, None, "El carrito no puede estar vacío"
```

---

### H4 — Validar `cantidad > 0` en `_validar_carrito`

`cantidad: -1` produce un total negativo que se envía a Monei sin filtro.

**Cambio:** Después de obtener `cantidad` del item:
```python
cantidad = item.get("cantidad", 1)
if not isinstance(cantidad, int) or cantidad <= 0:
    return None, None, f"Cantidad inválida para el producto {codigo}"
```

---

### H5 — Log cuando `confirmar_pago_online` devuelve `False`

En este punto Monei ya cobró. Sin log, no hay trazabilidad para soporte.

**Cambio:** En el bloque `if not ok:` después de `confirmar_pago_online`:
```python
if not ok:
    logger.error(
        "CONFIRMAR_PAGO_ONLINE_FALLIDO pedido=%s importe=%s monei_url=%s",
        pedido_activo_id, amount_in_cents, redirect_url
    )
    return False, "Error al registrar el pedido tras el pago"
```

---

### H9 — Log en path de idempotencia de `iniciar_pago`

Sin log no hay trazabilidad de doble-submit desde el frontend.

**Cambio:** En la guardia `if pedido_activo.Estado == EstadoPedido.CONFIRMANDO_PAGO:`:
```python
logger.info("PAGO_YA_INICIADO pedido=%s usuario=%s", pedido_activo.PedidoID, user_id)
```

---

### H2 — Guardia de idempotencia devuelve URL real (no texto)

`iniciar_pago` devolvía el string `"El pedido ya está en proceso de pago."` cuando el estado era `CONFIRMANDO_PAGO`. El blueprint tenía una string comparison frágil para detectarlo.

**Cambio en `controllers/pago.py`** — devolver la URL de Monei ya almacenada (combinado con H9):
```python
if pedido_activo.Estado == EstadoPedido.CONFIRMANDO_PAGO:
    logger.info("PAGO_YA_INICIADO pedido=%s usuario=%s", pedido_activo.PedidoID, user_id)
    return True, pedido_activo.enlace or f"{public_url}/pago_en_curso"
```

**Cambio en `blueprints/api/payments.py`** — eliminar la string comparison muerta (líneas 54-55):
```python
# eliminar estas dos líneas:
if result == "El pedido ya está en proceso de pago.":
    return jsonify({"message": result}), 200
```

El flujo después de la limpieza:
```python
if not success:
    return jsonify({"error": result}), 400
return jsonify({"redirect_url": result, "message": "Pedido enviado correctamente."}), 200
```

---

### H6 — Eliminar parámetro `cache` sin usar

`cache` aparece en las firmas de `iniciar_pago` e `iniciar_pago_efectivo` pero nunca se usa en ninguna de las dos. Los callers deben pasarlo o reciben `TypeError`.

**Cambio en `controllers/pago.py`** — eliminar `cache` de ambas firmas.

**Cambio en `blueprints/api/payments.py`** — eliminar `cache=cache` de ambas llamadas. Verificar si `cache` sigue usándose en otro sitio del archivo; si no, eliminar también del import `from container import ...`.

---

### H8 — DB error handling en ambas funciones (opción A: cobertura completa)

Ninguna llamada a DB tiene try/except. Un error de SQL Server durante el checkout lanza una excepción no capturada al blueprint.

**Cambio en `iniciar_pago`:**

```python
# Wrap obtener_pedido_mas_reciente
try:
    pedido_activo = gestor_pedidos.obtener_pedido_mas_reciente(user_id)
except (SQLAlchemyError, RetryError) as e:
    logger.error("iniciar_pago: DB error usuario=%s: %s", user_id, e)
    return False, "Error de base de datos. Intente más tarde."

# Wrap confirmar_pago_online (CRÍTICO: Monei ya cobró en este punto)
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
```

**Cambio en `iniciar_pago_efectivo`:**

```python
# Wrap obtener_pedido_mas_reciente
try:
    pedido_activo = gestor_pedidos.obtener_pedido_mas_reciente(user_id)
except (SQLAlchemyError, RetryError) as e:
    logger.error("iniciar_pago_efectivo: DB error usuario=%s: %s", user_id, e)
    return False, "Error de base de datos. Intente más tarde."

# Wrap confirmar_pago_efectivo
try:
    ok = gestor_pedidos.confirmar_pago_efectivo(
        pedido_id, productos_validos, notas=notas or None
    )
except (SQLAlchemyError, RetryError) as e:
    logger.error("iniciar_pago_efectivo: DB error al confirmar pedido=%s: %s", pedido_id, e)
    return False, "Error de base de datos al confirmar el pedido."
```

Imports a añadir al inicio de `controllers/pago.py`:
```python
from sqlalchemy.exc import SQLAlchemyError
from tenacity import RetryError
```

---

### H1 — try/except en `_enviar_confirmacion_efectivo`

Si WhatsApp falla después de que `confirmar_pago_efectivo` ya persistió el pedido como `CONTRA_REEMBOLSO`, la excepción propagaba un 500. El cliente no sabía que su pedido estaba confirmado y no podía reintentar (estado ya cambió).

**Cambio en `iniciar_pago_efectivo`** — wrap del envío WhatsApp:
```python
try:
    _enviar_confirmacion_efectivo(numero_cliente, nombre_cliente, total_euros, pedido_id, direccion_cliente)
except Exception as e:
    logger.error(
        "CONFIRMACION_EFECTIVO_WA_FALLIDA pedido=%s error=%s",
        pedido_id, e, exc_info=True
    )
# Pedido confirmado en DB — devolver True aunque falle WhatsApp
return True, f"{public_url}/pago_confirmado?pedido_id={redis_id}"
```

---

## Qué NO se toca

- El orden Monei→DB en `iniciar_pago` — correcto y bien documentado.
- La lógica de recálculo de precios en `_validar_carrito` — correcta.
- Los guards de estado (ENLACE2, CONFIRMANDO_PAGO) — correctos.
- `controllers/pago_notifier.py` — sin cambios.
- H7 (`"codigo"` vs `"Codigo"`) — auditoría de `pedido.py`.
- Tests — ticket separado.

---

## Orden de aplicación

1. H3 + H4 — validaciones en `_validar_carrito` (2 bloques, misma función)
2. H9 + H2 — log + URL real en guardia idempotencia (misma línea)
3. H5 — log en `confirmar_pago_online` falla
4. H6 — eliminar `cache` de firmas y blueprint
5. H8 — imports DB + try/except en 4 puntos (2 funciones × 2 calls)
6. H1 — try/except en `_enviar_confirmacion_efectivo`
7. H2 blueprint — eliminar string comparison en `payments.py`
