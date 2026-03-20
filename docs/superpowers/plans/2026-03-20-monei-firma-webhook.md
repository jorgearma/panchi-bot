# Monei Webhook Signature Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminar la excepción de seguridad debug en `blueprints/webhook.py` y corregir el helper de firma en `tests/test_webhook.py` para que los 3 tests que fallan pasen.

**Architecture:** Dos cambios quirúrgicos: (1) en producción, reemplazar la rama `elif not current_app.debug / else: pass` por un único `else: return 401`, sin excepciones; (2) en tests, reemplazar `sign_monei` (que firma solo `body`) por `make_monei_signature` (que produce el header completo `t=<ts>,v1=<hmac>` firmando `<ts>.<body>`), y actualizar los 3 tests que usan el helper.

**Tech Stack:** Python 3, Flask, pytest, `hmac` / `hashlib` (stdlib)

---

## Archivos modificados

| Archivo | Cambio |
|---------|--------|
| `blueprints/webhook.py` | Eliminar rama debug en líneas 114-119: `elif not current_app.debug` + `else: pass` → `else: return 401` |
| `tests/test_webhook.py` | Reemplazar helper `sign_monei` por `make_monei_signature`; actualizar 3 tests |

No se crea ningún archivo nuevo.

---

## Task 1: Corregir la excepción debug en `blueprints/webhook.py`

**Files:**
- Modify: `blueprints/webhook.py:114-119`
- Test: `tests/test_webhook.py` (clase `TestWebhookMonei`)

### Contexto

El código actual (líneas 114-119) es:

```python
elif not current_app.debug:
    logger.warning("MONEI_WEBHOOK_SECRET not configured — rejecting webhook")
    return jsonify({"error": "Invalid signature"}), 401
else:
    # TODO: configurar MONEI_WEBHOOK_SECRET en producción
    logger.warning("MONEI_WEBHOOK_SECRET no configurado — omitiendo verificación (modo debug)")
```

Esto permite que en modo debug, sin secret, cualquier request pase. Debe reemplazarse por un `else` incondicional que siempre devuelva 401.

- [ ] **Step 1: Verificar que `test_sin_secret_configurado_retorna_401` ya pasa antes del cambio**

  ```bash
  venv/bin/pytest tests/test_webhook.py::TestWebhookMonei::test_sin_secret_configurado_retorna_401 -v
  ```

  Expected: PASS (el test parchea `config.MONEI_WEBHOOK_SECRET = None`, lo que activa la rama `elif not current_app.debug` en modo no-debug de test, devolviendo 401 — el test pasa pero por razón diferente a la que cree)

- [ ] **Step 2: Aplicar el fix en `blueprints/webhook.py`**

  Localizar el bloque (líneas 114-119):

  ```python
  elif not current_app.debug:
      logger.warning("MONEI_WEBHOOK_SECRET not configured — rejecting webhook")
      return jsonify({"error": "Invalid signature"}), 401
  else:
      # TODO: configurar MONEI_WEBHOOK_SECRET en producción
      logger.warning("MONEI_WEBHOOK_SECRET no configurado — omitiendo verificación (modo debug)")
  ```

  Sustituir por:

  ```python
  else:
      logger.warning("MONEI_WEBHOOK_SECRET not configured — rejecting webhook")
      return jsonify({"error": "Invalid signature"}), 401
  ```

- [ ] **Step 3: Verificar que el test sigue pasando tras el fix**

  ```bash
  venv/bin/pytest tests/test_webhook.py::TestWebhookMonei::test_sin_secret_configurado_retorna_401 -v
  ```

  Expected: PASS

- [ ] **Step 4: Verificar que ningún otro test de webhook rompe**

  ```bash
  venv/bin/pytest tests/test_webhook.py -v
  ```

  Expected: todos los tests que ya pasaban siguen pasando; los 3 tests de `sign_monei` siguen fallando (se arreglan en Task 2)

---

## Task 2: Corregir el helper de firma en `tests/test_webhook.py`

**Files:**
- Modify: `tests/test_webhook.py:37-38` (helper `sign_monei`)
- Modify: `tests/test_webhook.py:179,188,211` (3 usos de `sign_monei`)

### Contexto

El helper actual firma solo el `body`:

```python
def sign_monei(secret: str, body: bytes) -> str:
    return hmac.HMAC(secret.encode(), body, hashlib.sha256).hexdigest()
```

El código de producción espera el header `t=<timestamp>,v1=<hex_sig>` donde el HMAC se calcula sobre `<timestamp>.<body>`. Sin el formato correcto, el parser extrae `timestamp=""` y `v1=""`, y el guard de la línea 105 devuelve 401 antes de llegar al cuerpo del test.

### Cambio en el helper

- [ ] **Step 1: Reemplazar `sign_monei` por `make_monei_signature`**

  Localizar en `tests/test_webhook.py` (líneas 37-38):

  ```python
  def sign_monei(secret: str, body: bytes) -> str:
      return hmac.HMAC(secret.encode(), body, hashlib.sha256).hexdigest()
  ```

  Sustituir por:

  ```python
  MONEI_TIMESTAMP = "1700000000"


  def make_monei_signature(secret: str, body: bytes, timestamp: str = MONEI_TIMESTAMP) -> str:
      """Devuelve el header MONEI-SIGNATURE completo: t=<ts>,v1=<hmac>"""
      signed_payload = f"{timestamp}.".encode() + body
      sig = hmac.HMAC(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
      return f"t={timestamp},v1={sig}"
  ```

  > El `MONEI_TIMESTAMP` se define justo encima de la función (misma zona del módulo que el helper anterior).

- [ ] **Step 2: Actualizar `test_order_id_no_numerico_retorna_400` (línea ~179)**

  Localizar:

  ```python
  sig = sign_monei(MONEI_SECRET, bad_body)
  ```

  Sustituir por:

  ```python
  sig = make_monei_signature(MONEI_SECRET, bad_body)
  ```

- [ ] **Step 3: Actualizar `test_pago_exitoso_actualiza_estado_y_retorna_200` (línea ~188)**

  Localizar:

  ```python
  sig = sign_monei(MONEI_SECRET, body)
  ```

  Sustituir por:

  ```python
  sig = make_monei_signature(MONEI_SECRET, body)
  ```

- [ ] **Step 4: Actualizar `test_pago_no_succeeded_no_actualiza_estado` (línea ~211)**

  Localizar:

  ```python
  sig = sign_monei(MONEI_SECRET, body)
  ```

  Sustituir por:

  ```python
  sig = make_monei_signature(MONEI_SECRET, body)
  ```

- [ ] **Step 5: Verificar que los 3 tests ahora pasan**

  ```bash
  venv/bin/pytest tests/test_webhook.py::TestWebhookMonei::test_order_id_no_numerico_retorna_400 \
                  tests/test_webhook.py::TestWebhookMonei::test_pago_exitoso_actualiza_estado_y_retorna_200 \
                  tests/test_webhook.py::TestWebhookMonei::test_pago_no_succeeded_no_actualiza_estado -v
  ```

  Expected: los 3 en PASS

- [ ] **Step 6: Verificar suite completa de webhook sin regresiones**

  ```bash
  venv/bin/pytest tests/test_webhook.py -v
  ```

  Expected: todos pasan (incluyendo `test_sin_secret_configurado_retorna_401`, `test_sin_header_firma_retorna_401`, `test_firma_incorrecta_retorna_401`)

- [ ] **Step 7: Verificar suite completa sin regresiones**

  ```bash
  venv/bin/pytest -v --tb=short
  ```

  Expected: misma cantidad de tests pasando que antes más los 3 nuevos — sin regresiones en ningún otro módulo

---

## Criterios de aceptación (del spec)

1. Sin `MONEI_WEBHOOK_SECRET` → siempre 401, en cualquier modo (debug o no).
2. Con secret + header `t=<ts>,v1=<sig>` correcto → procesa el webhook (200).
3. Con secret + header malformado (sin `t=` o sin `v1=`) → 401.
4. Con secret + HMAC incorrecto → 401.
5. Los 3 tests que antes fallaban ahora pasan.
6. Los tests que ya pasaban siguen pasando.
7. Suite completa: sin regresiones.
