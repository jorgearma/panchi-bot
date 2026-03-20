# Spec: Corregir verificación de firma Monei webhook

**Fecha:** 2026-03-20
**Ámbito:** `blueprints/webhook.py`, `tests/test_webhook.py`

---

## Problemas

### 1. Excepción de seguridad en modo debug (`webhook.py:114-119`)

Si `MONEI_WEBHOOK_SECRET` no está configurado y `current_app.debug=True`, el código
acepta cualquier webhook sin verificar la firma. Cualquier atacante que conozca el
endpoint puede forjar pagos en entornos staging o de desarrollo mal configurados.

```python
# código actual — rama insegura
elif not current_app.debug:
    return 401
else:
    logger.warning("omitiendo verificación")  # ← acepta sin secret en debug
```

### 2. Tests fallidos por formato de firma incorrecto (`test_webhook.py`)

El helper `sign_monei` firma solo el `body` raw. Pero el código de producción espera:
- Header: `t=<timestamp>,v1=<hex_signature>`
- Payload firmado: `<timestamp>.<body>` (no solo `body`)

Los 3 tests que fallan (`test_order_id_no_numerico_retorna_400`,
`test_pago_exitoso_actualiza_estado_y_retorna_200`,
`test_pago_no_succeeded_no_actualiza_estado`) pasan la firma como hex puro sin formato
`t=...,v1=...`, por lo que el parser extrae `timestamp=""` y `received_signature=""`
y devuelve 401 antes de llegar al assert esperado.

---

## Solución

### 1. `blueprints/webhook.py` — eliminar excepción debug

Sustituir:
```python
elif not current_app.debug:
    logger.warning("MONEI_WEBHOOK_SECRET not configured — rejecting webhook")
    return jsonify({"error": "Invalid signature"}), 401
else:
    logger.warning("MONEI_WEBHOOK_SECRET no configurado — omitiendo verificación (modo debug)")
```

Por:
```python
else:
    logger.warning("MONEI_WEBHOOK_SECRET not configured — rejecting webhook")
    return jsonify({"error": "Invalid signature"}), 401
```

Sin condición sobre `debug`. Si no hay secret, siempre 401.

### 2. `tests/test_webhook.py` — arreglar `sign_monei` y los 3 tests

**Helper nuevo** — reemplaza `sign_monei` existente:
```python
MONEI_TIMESTAMP = "1700000000"

def make_monei_signature(secret: str, body: bytes, timestamp: str = MONEI_TIMESTAMP) -> str:
    """Devuelve el header MONEI-SIGNATURE completo: t=<ts>,v1=<hmac>"""
    signed_payload = f"{timestamp}.".encode() + body
    sig = hmac.HMAC(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={sig}"
```

**Tres tests que usan `sign_monei(secret, body)`** deben pasar a usar
`make_monei_signature(secret, body)` como valor del argumento `signature=` en `_post`.

**`test_sin_header_firma_retorna_401`** — ya correcto, no cambia (pasa `signature=""`
que hace que timestamp y v1 queden vacíos → 401).

**`test_firma_incorrecta_retorna_401`** — ya correcto, no cambia (pasa header
malformado sin `t=` ni `v1=` → timestamp="" → 401).

---

## Lo que NO cambia

- La lógica de verificación HMAC en sí (`hmac.compare_digest`) — ya correcta.
- El guard de timestamp/v1 vacíos (líneas 105-107) — ya correcto.
- El resto del flujo Monei (parseo de orderId, actualización de estado, etc.).
- Ningún otro blueprint o controller.

---

## Criterios de aceptación

1. Sin `MONEI_WEBHOOK_SECRET` → siempre 401, en cualquier modo (debug o no).
2. Con secret + header `t=<ts>,v1=<sig>` correcto → procesa el webhook (200).
3. Con secret + header malformado (sin `t=` o sin `v1=`) → 401.
4. Con secret + HMAC incorrecto → 401.
5. Los 3 tests pre-existentes que fallaban ahora pasan.
6. Los tests que ya pasaban (`test_sin_secret_configurado_retorna_401`,
   `test_sin_header_firma_retorna_401`, `test_firma_incorrecta_retorna_401`) siguen pasando.
7. Suite completa: sin regresiones.
