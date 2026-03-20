# WhatsApp Multi-Proveedor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **⚠️ IMPORTANTE:** El usuario hace los commits manualmente. NO ejecutes `git commit`. Al final de cada tarea muestra el comando exacto para que el usuario lo ejecute.

**Goal:** Añadir soporte para Meta WhatsApp Cloud API como proveedor alternativo a Twilio, seleccionable mediante `WHATSAPP_PROVIDER=twilio|meta`.

**Architecture:** Un único fichero `services/whatsapp_service.py` sustituye a `twilio_service.py` y enruta internamente a Twilio o Meta según la env var. Para la recepción, se añaden dos nuevas rutas `/webhook/meta` (GET verificación, POST mensajes) en el blueprint existente, reutilizando toda la lógica de negocio actual sin modificarla.

**Tech Stack:** Python 3, Flask, Twilio SDK, `requests` (ya en requirements), `hmac`/`hashlib` (stdlib), `tenacity`, pytest

---

## Mapa de ficheros

| Fichero | Acción | Responsabilidad |
|---------|--------|-----------------|
| `services/whatsapp_service.py` | Crear | Envío de mensajes vía Twilio o Meta |
| `services/twilio_service.py` | Eliminar | Reemplazado por whatsapp_service.py |
| `blueprints/webhook.py` | Modificar | Añadir GET+POST `/webhook/meta` |
| `config.py` | Modificar | Añadir vars Meta |
| `main.py` | Modificar | Validación condicional de vars obligatorias |
| `tests/test_whatsapp_service.py` | Crear | Tests unitarios del servicio |
| `tests/test_webhook.py` | Modificar | Tests para `/webhook/meta` + actualizar patches |
| 8 ficheros importadores | Modificar | Cambiar import de `twilio_service` a `whatsapp_service` |

---

## Task 1: Crear `services/whatsapp_service.py` con proveedor Twilio

**Files:**
- Create: `services/whatsapp_service.py`
- Create: `tests/test_whatsapp_service.py`

> En este task solo implementamos la rama Twilio. Meta viene en Task 3. El objetivo es tener el nuevo fichero funcionando como sustituto exacto de `twilio_service.py`.

- [ ] **Step 1: Escribir el test que verifica que con proveedor twilio se llama al cliente Twilio**

  Crear `tests/test_whatsapp_service.py`:

  ```python
  import os
  import pytest
  from unittest.mock import patch, MagicMock


  class TestEnviarMensajeTwilio:

      def test_twilio_es_proveedor_por_defecto(self):
          """Sin WHATSAPP_PROVIDER, usa Twilio."""
          with patch.dict(os.environ, {}, clear=False):
              os.environ.pop("WHATSAPP_PROVIDER", None)
              with patch("services.whatsapp_service._get_client") as mock_client:
                  mock_client.return_value.messages.create = MagicMock()
                  from services.whatsapp_service import enviar_mensaje_whatsapp
                  enviar_mensaje_whatsapp("hola", "whatsapp:+34600000000")
                  mock_client.return_value.messages.create.assert_called_once()

      def test_twilio_pasa_numero_con_prefijo(self):
          """_enviar_twilio pasa el número tal cual (con prefijo whatsapp:+)."""
          with patch.dict(os.environ, {"WHATSAPP_PROVIDER": "twilio"}):
              with patch("services.whatsapp_service._get_client") as mock_client:
                  mock_create = mock_client.return_value.messages.create
                  from services.whatsapp_service import enviar_mensaje_whatsapp
                  enviar_mensaje_whatsapp("hola", "whatsapp:+34600000000")
                  call_kwargs = mock_create.call_args.kwargs
                  assert call_kwargs["to"] == "whatsapp:+34600000000"
                  assert call_kwargs["body"] == "hola"
  ```

- [ ] **Step 2: Verificar que el test falla (fichero no existe aún)**

  ```bash
  venv/bin/pytest tests/test_whatsapp_service.py -v
  ```

  Expected: `ModuleNotFoundError` o `ImportError`

- [ ] **Step 3: Crear `services/whatsapp_service.py`**

  ```python
  import os
  import logging
  import config
  import requests
  from twilio.rest import Client
  from twilio.base.exceptions import TwilioRestException
  from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

  logger = logging.getLogger(__name__)

  _client = None


  def _get_client():
      global _client
      if _client is None:
          _client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
      return _client


  @retry(
      stop=stop_after_attempt(3),
      wait=wait_exponential(multiplier=1, min=1, max=10),
      retry=retry_if_exception_type(TwilioRestException),
      reraise=True,
  )
  def _enviar_twilio(mensaje: str, destinatario: str) -> None:
      _get_client().messages.create(
          body=mensaje,
          from_=config.TWILIO_WHATSAPP_NUMBER,
          to=destinatario,
      )
      logger.info("Mensaje enviado (Twilio) a %s", destinatario)


  @retry(
      stop=stop_after_attempt(3),
      wait=wait_exponential(multiplier=1, min=1, max=10),
      retry=retry_if_exception_type(requests.exceptions.RequestException),
      reraise=True,
  )
  def _enviar_meta(mensaje: str, destinatario: str) -> None:
      numero = destinatario.replace("whatsapp:+", "")
      url = f"https://graph.facebook.com/v19.0/{config.META_PHONE_NUMBER_ID}/messages"
      payload = {
          "messaging_product": "whatsapp",
          "to": numero,
          "type": "text",
          "text": {"body": mensaje},
      }
      resp = requests.post(
          url,
          json=payload,
          headers={"Authorization": f"Bearer {config.META_ACCESS_TOKEN}"},
          timeout=10,
      )
      resp.raise_for_status()
      logger.info("Mensaje enviado (Meta) a %s", destinatario)


  def enviar_mensaje_whatsapp(mensaje: str, destinatario: str) -> None:
      provider = os.getenv("WHATSAPP_PROVIDER", "twilio")
      if provider == "meta":
          _enviar_meta(mensaje, destinatario)
      else:
          _enviar_twilio(mensaje, destinatario)
  ```

  > Nota: `_enviar_meta` se define aquí ya aunque su test viene en Task 3. Así el fichero es completo desde el principio.

- [ ] **Step 4: Verificar que los tests del servicio pasan**

  ```bash
  venv/bin/pytest tests/test_whatsapp_service.py -v
  ```

  Expected: 2 PASS

- [ ] **Step 5: Mostrar comando de commit al usuario**

  ```
  git add services/whatsapp_service.py tests/test_whatsapp_service.py
  git commit -m "feat: crear whatsapp_service.py con proveedor Twilio"
  ```

---

## Task 2: Actualizar los 8 ficheros importadores

**Files:**
- Modify: `blueprints/webhook.py:15`
- Modify: `blueprints/repartidor.py:9`
- Modify: `blueprints/dashboard.py:9`
- Modify: `blueprints/picker.py:8`
- Modify: `controllers/pago.py:6`
- Modify: `controllers/registro.py:3`
- Modify: `controllers/mensajes_registrados.py:3`
- Modify: `controllers/pedido.py:8`
- Modify: `tests/test_webhook.py` (patches)
- Modify: `tests/test_registro.py` (patches)
- Modify: `tests/test_mensajes_registrados.py` (patches)

> En este task NO se toca la lógica de negocio — solo se renombra el módulo importado. El criterio de éxito es que la suite completa pase igual que antes.

- [ ] **Step 1: En cada uno de los 8 ficheros de producción, cambiar la línea de import**

  Buscar: `from services.twilio_service import enviar_mensaje_whatsapp`
  Reemplazar por: `from services.whatsapp_service import enviar_mensaje_whatsapp`

  Ficheros (hacer uno a uno para evitar errores):
  - `blueprints/webhook.py`
  - `blueprints/repartidor.py`
  - `blueprints/dashboard.py`
  - `blueprints/picker.py`
  - `controllers/pago.py`
  - `controllers/registro.py`
  - `controllers/mensajes_registrados.py`
  - `controllers/pedido.py`

- [ ] **Step 2: Verificar que ningún test parchea directamente `services.twilio_service`**

  Los patches en los tests usan rutas como `"controllers.registro.enviar_mensaje_whatsapp"` — estos NO cambian porque el patch se aplica en el módulo consumidor, no en el de origen. Sin embargo, verificar por si acaso:

  ```bash
  grep -r "twilio_service" tests/
  ```

  Expected: sin resultados. Si aparece alguno, cambiarlo a `services.whatsapp_service`. Este paso es habitualmente un no-op.

- [ ] **Step 3: Verificar que la suite completa pasa sin regresiones**

  ```bash
  venv/bin/pytest -v --tb=short
  ```

  Expected: mismo resultado que antes (153 pass, 1 fail pre-existente en test_health)

- [ ] **Step 4: Verificar que `twilio_service.py` ya no se importa en ningún sitio de producción**

  ```bash
  grep -r "twilio_service" blueprints/ controllers/ services/ --include="*.py"
  ```

  Expected: sin resultados

- [ ] **Step 5: Eliminar `services/twilio_service.py`**

  ```bash
  rm services/twilio_service.py
  ```

- [ ] **Step 6: Volver a correr la suite para confirmar que la eliminación no rompe nada**

  ```bash
  venv/bin/pytest -v --tb=short
  ```

  Expected: mismo resultado que Step 3

- [ ] **Step 7: Mostrar comando de commit al usuario**

  ```
  git add -A
  git commit -m "refactor: renombrar twilio_service a whatsapp_service, actualizar importadores"
  ```

---

## Task 3: Añadir y testear el proveedor Meta en `services/whatsapp_service.py`

**Files:**
- Modify: `tests/test_whatsapp_service.py`

> `_enviar_meta` ya existe en el fichero (creado en Task 1). Este task añade sus tests y verifica que funciona correctamente.

- [ ] **Step 1: Añadir tests para el proveedor Meta en `tests/test_whatsapp_service.py`**

  Añadir la siguiente clase al final del fichero:

  ```python
  class TestEnviarMensajeMeta:

      def test_meta_normaliza_numero(self):
          """_enviar_meta elimina el prefijo whatsapp:+ antes de enviar."""
          with patch.dict(os.environ, {"WHATSAPP_PROVIDER": "meta"}):
              with patch("services.whatsapp_service.requests.post") as mock_post:
                  mock_post.return_value.raise_for_status = MagicMock()
                  with patch("services.whatsapp_service.config") as mock_cfg:
                      mock_cfg.META_PHONE_NUMBER_ID = "123456"
                      mock_cfg.META_ACCESS_TOKEN = "token-test"
                      from services.whatsapp_service import enviar_mensaje_whatsapp
                      enviar_mensaje_whatsapp("hola", "whatsapp:+34600000000")
                  call_kwargs = mock_post.call_args.kwargs
                  assert call_kwargs["json"]["to"] == "34600000000"

      def test_meta_envia_mensaje_correcto(self):
          """_enviar_meta construye el payload correcto para la Cloud API."""
          with patch.dict(os.environ, {"WHATSAPP_PROVIDER": "meta"}):
              with patch("services.whatsapp_service.requests.post") as mock_post:
                  mock_post.return_value.raise_for_status = MagicMock()
                  with patch("services.whatsapp_service.config") as mock_cfg:
                      mock_cfg.META_PHONE_NUMBER_ID = "123456"
                      mock_cfg.META_ACCESS_TOKEN = "mi-token"
                      from services.whatsapp_service import enviar_mensaje_whatsapp
                      enviar_mensaje_whatsapp("Pedido listo", "whatsapp:+34611222333")
                  call_kwargs = mock_post.call_args.kwargs
                  assert call_kwargs["json"]["messaging_product"] == "whatsapp"
                  assert call_kwargs["json"]["type"] == "text"
                  assert call_kwargs["json"]["text"]["body"] == "Pedido listo"
                  assert "Bearer mi-token" in call_kwargs["headers"]["Authorization"]

      def test_meta_llama_raise_for_status(self):
          """_enviar_meta llama raise_for_status para detectar errores HTTP."""
          with patch.dict(os.environ, {"WHATSAPP_PROVIDER": "meta"}):
              with patch("services.whatsapp_service.requests.post") as mock_post:
                  mock_post.return_value.raise_for_status = MagicMock()
                  with patch("services.whatsapp_service.config") as mock_cfg:
                      mock_cfg.META_PHONE_NUMBER_ID = "123456"
                      mock_cfg.META_ACCESS_TOKEN = "token"
                      from services.whatsapp_service import enviar_mensaje_whatsapp
                      enviar_mensaje_whatsapp("hola", "whatsapp:+34600000000")
                  mock_post.return_value.raise_for_status.assert_called_once()
  ```

- [ ] **Step 2: Verificar que los nuevos tests pasan**

  ```bash
  venv/bin/pytest tests/test_whatsapp_service.py -v
  ```

  Expected: 5 PASS (2 anteriores + 3 nuevos)

- [ ] **Step 3: Mostrar comando de commit al usuario**

  ```
  git add tests/test_whatsapp_service.py
  git commit -m "test: añadir tests para proveedor Meta en whatsapp_service"
  ```

---

## Task 4: Actualizar `config.py` y `main.py`

**Files:**
- Modify: `config.py`
- Modify: `main.py:18-28`

- [ ] **Step 1: Añadir las 5 variables Meta al final de `config.py`**

  Añadir justo antes del final del fichero (después de `CUSTOMER_SUPPORT_PHONE`):

  ```python
  # WhatsApp provider ("twilio" o "meta")
  WHATSAPP_PROVIDER: str = os.environ.get("WHATSAPP_PROVIDER", "twilio")

  # Meta WhatsApp Cloud API (solo necesario si WHATSAPP_PROVIDER=meta)
  META_ACCESS_TOKEN: str | None = os.environ.get("META_ACCESS_TOKEN")
  META_PHONE_NUMBER_ID: str | None = os.environ.get("META_PHONE_NUMBER_ID")
  META_APP_SECRET: str | None = os.environ.get("META_APP_SECRET")
  META_VERIFY_TOKEN: str | None = os.environ.get("META_VERIFY_TOKEN")
  ```

- [ ] **Step 2: Actualizar la validación de arranque en `main.py`**

  Localizar el bloque actual (líneas 18-28):

  ```python
  _VARS_OBLIGATORIAS = [
      'SECRET_KEY', 'TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN',
      'TWILIO_WHATSAPP_NUMBER', 'MONEI_API_KEY', 'MONEI_WEBHOOK_SECRET', 'PUBLIC_URL',
  ]
  if not (config or {}).get('TESTING'):
      faltantes = [v for v in _VARS_OBLIGATORIAS if not os.environ.get(v)]
      if faltantes:
          raise EnvironmentError(
              f"Variables de entorno obligatorias no definidas: {', '.join(faltantes)}\n"
              "Comprueba tu archivo .env"
          )
  ```

  Sustituir por:

  ```python
  _VARS_COMUNES = ['SECRET_KEY', 'MONEI_API_KEY', 'MONEI_WEBHOOK_SECRET', 'PUBLIC_URL']
  if os.environ.get('WHATSAPP_PROVIDER', 'twilio') == 'meta':
      _VARS_OBLIGATORIAS = _VARS_COMUNES + [
          'META_ACCESS_TOKEN', 'META_PHONE_NUMBER_ID', 'META_APP_SECRET', 'META_VERIFY_TOKEN',
      ]
  else:
      _VARS_OBLIGATORIAS = _VARS_COMUNES + [
          'TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_WHATSAPP_NUMBER',
      ]
  if not (config or {}).get('TESTING'):
      faltantes = [v for v in _VARS_OBLIGATORIAS if not os.environ.get(v)]
      if faltantes:
          raise EnvironmentError(
              f"Variables de entorno obligatorias no definidas: {', '.join(faltantes)}\n"
              "Comprueba tu archivo .env"
          )
  ```

- [ ] **Step 3: Verificar que la suite no rompe con este cambio**

  ```bash
  venv/bin/pytest -v --tb=short
  ```

  Expected: mismo resultado (153 pass, 1 fail pre-existente)

- [ ] **Step 4: Mostrar comando de commit al usuario**

  ```
  git add config.py main.py
  git commit -m "feat: añadir vars Meta a config y validación condicional en arranque"
  ```

---

## Task 5: Añadir endpoints `/webhook/meta` en `blueprints/webhook.py`

> **Prerequisito:** Task 2 debe estar completada. El import en `blueprints/webhook.py` ya debe ser `from services.whatsapp_service import enviar_mensaje_whatsapp` — `webhook_meta` lo usa.

**Files:**
- Modify: `blueprints/webhook.py` (añadir al final)
- Modify: `tests/test_webhook.py` (añadir clase `TestWebhookMeta`)

- [ ] **Step 1: Escribir los tests para los nuevos endpoints**

  Añadir al final de `tests/test_webhook.py`:

  ```python
  # ─────────────────────────────────────────────
  # GET + POST /webhook/meta — Meta Cloud API
  # ─────────────────────────────────────────────

  META_SECRET = "meta_app_secret_test"
  META_VERIFY = "mi_verify_token"


  def make_meta_signature(secret: str, body: bytes) -> str:
      """Genera el header X-Hub-Signature-256 que Meta envía."""
      sig = hmac.HMAC(secret.encode(), body, hashlib.sha256).hexdigest()
      return f"sha256={sig}"


  def meta_body(from_number="34600000000", text="hola", msg_type="text"):
      return json.dumps({
          "entry": [{
              "changes": [{
                  "value": {
                      "messages": [{
                          "from": from_number,
                          "type": msg_type,
                          "text": {"body": text},
                      }]
                  }
              }]
          }]
      }).encode()


  class TestWebhookMeta:

      def _post(self, client, body: bytes, signature: str = ""):
          return client.post(
              "/webhook/meta",
              data=body,
              content_type="application/json",
              headers={"X-Hub-Signature-256": signature},
          )

      def _get(self, client, mode="subscribe", token=META_VERIFY, challenge="abc123"):
          return client.get(
              "/webhook/meta",
              query_string={
                  "hub.mode": mode,
                  "hub.verify_token": token,
                  "hub.challenge": challenge,
              },
          )

      # ── GET: verificación de webhook ──────────────────────────

      def test_get_verify_token_correcto_retorna_challenge(self, client):
          """GET con token correcto → 200 con el challenge."""
          with patch("blueprints.webhook.config") as mock_cfg:
              mock_cfg.META_VERIFY_TOKEN = META_VERIFY
              resp = self._get(client)
          assert resp.status_code == 200
          assert resp.data == b"abc123"

      def test_get_verify_token_incorrecto_retorna_403(self, client):
          """GET con token incorrecto → 403."""
          with patch("blueprints.webhook.config") as mock_cfg:
              mock_cfg.META_VERIFY_TOKEN = META_VERIFY
              resp = self._get(client, token="token-malo")
          assert resp.status_code == 403

      # ── POST: validación de firma ─────────────────────────────

      def test_post_sin_firma_retorna_401(self, client):
          """POST sin X-Hub-Signature-256 → 401."""
          body = meta_body()
          with patch("blueprints.webhook.config") as mock_cfg:
              mock_cfg.META_APP_SECRET = META_SECRET
              resp = self._post(client, body, signature="")
          assert resp.status_code == 401

      def test_post_firma_incorrecta_retorna_401(self, client):
          """POST con HMAC incorrecto → 401."""
          body = meta_body()
          with patch("blueprints.webhook.config") as mock_cfg:
              mock_cfg.META_APP_SECRET = META_SECRET
              resp = self._post(client, body, signature="sha256=firma-mala")
          assert resp.status_code == 401

      # ── POST: parseo de payload ───────────────────────────────

      def test_post_sin_messages_retorna_200_sin_procesar(self, client):
          """Notificación de estado (sin messages) → 200, no llama a manejar_registro."""
          body = json.dumps({"entry": [{"changes": [{"value": {}}]}]}).encode()
          sig = make_meta_signature(META_SECRET, body)
          with patch("blueprints.webhook.config") as mock_cfg:
              mock_cfg.META_APP_SECRET = META_SECRET
              with patch("blueprints.webhook.manejar_registro") as mock_reg:
                  resp = self._post(client, body, signature=sig)
          assert resp.status_code == 200
          mock_reg.assert_not_called()

      def test_post_mensaje_no_texto_retorna_200_sin_procesar(self, client):
          """Mensaje de tipo imagen/audio → 200, no procesa."""
          body = meta_body(msg_type="image")
          sig = make_meta_signature(META_SECRET, body)
          with patch("blueprints.webhook.config") as mock_cfg:
              mock_cfg.META_APP_SECRET = META_SECRET
              with patch("blueprints.webhook.manejar_registro") as mock_reg:
                  with patch("blueprints.webhook.redismanager") as mock_redis:
                      mock_redis.esta_bloqueado.return_value = False
                      resp = self._post(client, body, signature=sig)
          assert resp.status_code == 200
          mock_reg.assert_not_called()

      def test_post_payload_malformado_retorna_200_sin_procesar(self, client):
          """Payload sin clave 'entry' → 200, no procesa."""
          body = json.dumps({"unexpected": "structure"}).encode()
          sig = make_meta_signature(META_SECRET, body)
          with patch("blueprints.webhook.config") as mock_cfg:
              mock_cfg.META_APP_SECRET = META_SECRET
              with patch("blueprints.webhook.manejar_registro") as mock_reg:
                  resp = self._post(client, body, signature=sig)
          assert resp.status_code == 200
          mock_reg.assert_not_called()

      # ── POST: routing a lógica de negocio ────────────────────

      def test_post_usuario_no_registrado_llama_manejar_registro(self, client):
          """Mensaje válido de usuario no registrado → llama a manejar_registro."""
          body = meta_body(from_number="34600000000", text="hola")
          sig = make_meta_signature(META_SECRET, body)
          with patch("blueprints.webhook.config") as mock_cfg:
              mock_cfg.META_APP_SECRET = META_SECRET
              with patch("blueprints.webhook.redismanager") as mock_redis:
                  mock_redis.esta_bloqueado.return_value = False
                  with patch("blueprints.webhook.gestor_usuarios") as mock_gu:
                      mock_gu.verificar_usuario.return_value = None
                      with patch("blueprints.webhook.manejar_registro", return_value=("ok", 200)) as mock_reg:
                          resp = self._post(client, body, signature=sig)
          assert resp.status_code == 200
          mock_reg.assert_called_once()
          # Verificar que el número se normaliza correctamente
          args = mock_reg.call_args.args
          assert args[0] == "whatsapp:+34600000000"

      def test_post_usuario_registrado_llama_manejador(self, client):
          """Mensaje válido de usuario registrado → llama a ManejadorMensajesRegistrados."""
          body = meta_body(from_number="34600000001", text="ver pedido")
          sig = make_meta_signature(META_SECRET, body)
          usuario_mock = MagicMock()
          with patch("blueprints.webhook.config") as mock_cfg:
              mock_cfg.META_APP_SECRET = META_SECRET
              with patch("blueprints.webhook.redismanager") as mock_redis:
                  mock_redis.esta_bloqueado.return_value = False
                  with patch("blueprints.webhook.gestor_usuarios") as mock_gu:
                      mock_gu.verificar_usuario.return_value = usuario_mock
                      with patch(
                          "blueprints.webhook.ManejadorMensajesRegistrados.manejar_mensajes_registrados",
                          return_value=("ok", 200)
                      ) as mock_man:
                          resp = self._post(client, body, signature=sig)
          assert resp.status_code == 200
          mock_man.assert_called_once()
  ```

- [ ] **Step 2: Verificar que los tests fallan (endpoints no existen aún)**

  ```bash
  venv/bin/pytest tests/test_webhook.py::TestWebhookMeta -v
  ```

  Expected: todos en FAIL con 404 (ruta no existe)

- [ ] **Step 3: Implementar los endpoints en `blueprints/webhook.py`**

  Añadir justo después de los imports existentes al principio del fichero, dentro de la sección de imports:

  > No añadir nuevos imports — `hmac`, `hashlib`, `json`, `config`, `redismanager`, `gestor_usuarios`, `manejar_registro`, `ManejadorMensajesRegistrados`, `limpiar_texto`, `jsonify`, `request` ya están importados.

  Añadir al **final** del fichero (después de `webhook_monei`):

  ```python

  @blueprint_webhook.route('/webhook/meta', methods=['GET'])
  def webhook_meta_verify():
      """Verificación del webhook en el panel de Meta."""
      mode = request.args.get('hub.mode')
      token = request.args.get('hub.verify_token')
      challenge = request.args.get('hub.challenge', '')
      if mode == 'subscribe' and token == config.META_VERIFY_TOKEN:
          return challenge, 200
      return jsonify({"error": "Forbidden"}), 403


  @blueprint_webhook.route('/webhook/meta', methods=['POST'])
  def webhook_meta():
      """Recepción de mensajes desde Meta WhatsApp Cloud API."""
      raw_body = request.get_data()

      # Verificar firma
      if not config.META_APP_SECRET:
          logger.warning("META_APP_SECRET not configured — rejecting webhook")
          return jsonify({"error": "Invalid signature"}), 401

      sig_header = request.headers.get('X-Hub-Signature-256', '')
      if not sig_header.startswith('sha256='):
          logger.warning("Meta webhook sin X-Hub-Signature-256")
          return jsonify({"error": "Invalid signature"}), 401

      received_sig = sig_header[len('sha256='):]
      computed = hmac.HMAC(config.META_APP_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
      if not hmac.compare_digest(computed, received_sig):
          logger.warning("Meta webhook signature mismatch")
          return jsonify({"error": "Invalid signature"}), 401

      # Parsear payload
      data = request.get_json()
      try:
          messages = data['entry'][0]['changes'][0]['value'].get('messages', [])
      except (KeyError, IndexError, TypeError):
          return jsonify({"ok": True}), 200

      if not messages:
          return jsonify({"ok": True}), 200

      message = messages[0]
      if message.get('type') != 'text':
          return jsonify({"ok": True}), 200

      # Normalizar número al formato interno whatsapp:+XXXXXXXXX
      numero_cliente = f"whatsapp:+{message['from']}"
      mensaje_cliente = limpiar_texto(message['text']['body'].lower())

      logger.info("Mensaje Meta recibido de %s: %s", numero_cliente, mensaje_cliente)

      # Rate limiting
      if redismanager.esta_bloqueado(numero_cliente):
          return "Número bloqueado", 403
      redismanager.bloquear_usuario(numero_cliente, duracion=4)

      # Routing a lógica de negocio
      try:
          usuario = gestor_usuarios.verificar_usuario(numero_cliente)
      except RetryError as re:
          logger.error("Error de conexión tras varios intentos: %s", re)
          enviar_mensaje_whatsapp(
              "Lo sentimos, se presentó un error en el sistema. Por favor, intente más tarde.",
              numero_cliente,
          )
          return jsonify({"error": "Error en la base de datos"}), 500
      except SQLAlchemyError as e:
          logger.error("Error al verificar el usuario: %s", e)
          enviar_mensaje_whatsapp(
              "Lo sentimos, se presentó un error en el sistema. Por favor, intente más tarde.",
              numero_cliente,
          )
          return jsonify({"error": "Error en la base de datos"}), 500
      except Exception as e:
          logger.exception("Error inesperado:")
          enviar_mensaje_whatsapp(
              "Lo sentimos, se presentó un error inesperado. Por favor, intente más tarde.",
              numero_cliente,
          )
          return jsonify({"error": "Error inesperado"}), 500

      try:
          if not usuario:
              return manejar_registro(numero_cliente, mensaje_cliente, redismanager)
          else:
              return ManejadorMensajesRegistrados.manejar_mensajes_registrados(
                  numero_cliente, mensaje_cliente
              )
      except Exception as e:
          logger.exception("Error procesando el mensaje del usuario:")
          enviar_mensaje_whatsapp(
              "Se presentó un problema al procesar su mensaje. Intente nuevamente.",
              numero_cliente,
          )
          return jsonify({"error": "Error procesando el mensaje"}), 500
  ```

  > Verificar que `RetryError` y `SQLAlchemyError` están ya importados en la cabecera del fichero. Si no, añadir:
  > ```python
  > from sqlalchemy.exc import SQLAlchemyError
  > from tenacity import RetryError
  > ```
  > (Ambos ya existen en el fichero actual, no necesitan añadirse.)

- [ ] **Step 4: Verificar que los tests de Meta pasan**

  ```bash
  venv/bin/pytest tests/test_webhook.py::TestWebhookMeta -v
  ```

  Expected: todos en PASS

- [ ] **Step 5: Verificar suite completa sin regresiones**

  ```bash
  venv/bin/pytest -v --tb=short
  ```

  Expected: 162+ pass (153 anteriores + 9 nuevos de TestWebhookMeta), 1 fail pre-existente en test_health

- [ ] **Step 6: Mostrar comando de commit al usuario**

  ```
  git add blueprints/webhook.py tests/test_webhook.py
  git commit -m "feat: añadir endpoints /webhook/meta (GET verificación, POST mensajes)"
  ```

---

## Criterios de aceptación finales

1. `WHATSAPP_PROVIDER=twilio` (default) — comportamiento 100% idéntico al actual.
2. `WHATSAPP_PROVIDER=meta` — mensajes salen via Meta Cloud API con Bearer token.
3. `GET /webhook/meta` con token correcto → 200 con challenge.
4. `POST /webhook/meta` con firma válida + mensaje de texto → misma lógica de negocio.
5. `POST /webhook/meta` con firma inválida → 401.
6. `POST /webhook/meta` con payload sin messages o tipo no-texto → 200 sin procesar.
7. Con `WHATSAPP_PROVIDER=meta` en arranque sin las 4 vars de Meta → `EnvironmentError`.
8. Suite completa: sin regresiones en ningún test existente.
