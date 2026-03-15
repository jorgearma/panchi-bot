# Plan de Refactorización — panchi-bot
**Versión:** 1.0 | **Fecha:** 2026-03-15 | **Rama base:** `refactorizar-estructura`

---

## Resumen ejecutivo

El sistema funciona en producción pero tiene vulnerabilidades de seguridad bloqueantes antes de cualquier exposición pública real, corrupción silenciosa de datos en la columna `TelefonoEntrega`, y deuda técnica acumulada que encarece el mantenimiento. El plan se divide en cuatro fases ordenadas de mayor a menor riesgo. Cada tarea incluye la referencia exacta al fichero y línea afectada.

---

## Qué NO tocar

Estos componentes están bien diseñados y no deben modificarse durante el refactor salvo que una fase lo exija explícitamente:

- **`states.py`** — La máquina de estados y los mapas de transición están correctamente modelados. Los tests en `test_states.py` validan todos los casos. No cambiar los valores de los enums (están en la BD).
- **`controllers/pago.py`** — La lógica de re-validación de precios contra BD es la protección anti-fraude más importante del sistema. Bien implementada con inyección de dependencias.
- **`controllers/pedido.py::confirmar_carrito`** — Transición de estado bien guardada, lógica de carrito correcta.
- **`managers/gestor_pedidos.py::actualizar_estado`** — Validación de transición + rollback en error, patrón correcto.
- **`managers/estado_usuario.py`** — El uso de `transicion_valida_registro` como guard antes de cada write es el patrón correcto a replicar.
- **`blueprints/webhook.py::webhook_monei`** — La verificación HMAC con `hmac.compare_digest` es correcta.
- **El sistema de sesión por request** en `database.py` (`get_db` + `teardown_appcontext`) — Manejo de sesión limpio y correcto para Flask.
- **La inicialización lazy de singletons** (Twilio, spaCy, Monei) — Patrón deliberado documentado, no romperlo.

---

## Fase 1 — Bloqueos de Seguridad (antes de producción)

**Objetivo:** Eliminar vectores de ataque que permiten inyectar pedidos falsos, cancelar pagos ajenos y filtrar datos personales.

**Criterio de aceptación:** `pytest` pasa al 100%. No existe ninguna ruta HTTP que modifique estado de pedido o usuario sin autenticación verificada.

---

### SEC-1: Verificación de firma de webhooks de Twilio
**Fichero:** `blueprints/webhook.py`, línea 23–29

El endpoint acepta cualquier POST que incluya los campos `From` y `Body`. Un atacante puede enviar mensajes falsos de cualquier número de WhatsApp sin que el servidor lo detecte.

```python
# Añadir antes del rate-limit check (línea 36):
REQUEST_VALIDATOR = RequestValidator(config.TWILIO_AUTH_TOKEN)
signature = request.headers.get("X-Twilio-Signature", "")
url = config.PUBLIC_URL + "/webhook"
if not REQUEST_VALIDATOR.validate(url, request.form, signature):
    return jsonify({"error": "Firma inválida"}), 403
```

En tests con `TESTING=True`, desactivar condicionalmente o usar `unittest.mock.patch`.

**Esfuerzo:** M | **Dependencia:** Ninguna

---

### SEC-2: Autenticación del endpoint `/api/cambiar_estado_a_enlace`
**Fichero:** `blueprints/api.py`, líneas 88–104

El endpoint está totalmente abierto. Cualquiera que conozca un `pedidoID` puede cancelar el proceso de pago de un cliente.

**Opción A (corto plazo):** Header `X-Internal-Token` leído de `config.INTERNAL_API_TOKEN`.
**Opción B:** Integrar la lógica en `confirmar_carrito` (que ya valida el token JWT) y eliminar el endpoint.

**Esfuerzo:** S | **Dependencia:** Ninguna

---

### SEC-3: DSN de Sentry hardcodeado en código fuente
**Fichero:** `main.py`, línea 23

```python
# Cambiar:
dsn=os.environ.get("SENTRY_DSN"),
```

Añadir `SENTRY_DSN` al `.env`.

**Esfuerzo:** S | **Dependencia:** Ninguna

---

### SEC-4: `send_default_pii=True` en Sentry (RGPD)
**Fichero:** `main.py`, línea 24

Envía IPs, headers completos y números de teléfono WhatsApp a servidores de Sentry. Infracción del RGPD para un negocio español.

Cambiar a `send_default_pii=False`. Si se necesita contexto, usar `sentry_sdk.set_user({"id": hash_anonimo})` con datos pseudoanonimizados.

**Esfuerzo:** S | **Dependencia:** Ninguna

---

### SEC-5: Email placeholder en datos del cliente de Monei
**Fichero:** `controllers/pago.py`, línea 66

`"email": "john.doe@monei.com"` se envía como email real del cliente a Monei.

Solución inmediata: `f"whatsapp_{numero_cliente.replace('+', '')}@noreply.panchibot.internal"`. El campo email real puede añadirse al flujo de registro en la Fase 3.

**Esfuerzo:** S | **Dependencia:** Ninguna

---

### SEC-6: CORS wildcard en endpoints financieros + headers duplicados
**Fichero:** `main.py` línea 30, `blueprints/api.py` líneas 19–23, 50–54

Flask-CORS ya configura los headers; los bloques `OPTIONS` manuales en `api.py` generan headers duplicados.

1. En `main.py`: `"origins": os.environ.get("ALLOWED_ORIGIN", "*")`
2. Eliminar los bloques `if request.method == 'OPTIONS'` de ambas rutas en `blueprints/api.py`.

**Esfuerzo:** S | **Dependencia:** Ninguna

---

## Fase 2 — Corrección de Bugs (integridad de datos)

**Objetivo:** Eliminar la corrupción silenciosa de datos, los crashes en producción y los estados inconsistentes.

**Criterio de aceptación:** Ningún pedido puede tener `TelefonoEntrega` con un nombre. Ningún enlace de menú puede generar una URL rota. El webhook de Monei puede recibir cualquier `orderId` sin lanzar excepción.

---

### BUG-CRÍTICO: Nombre almacenado en columna `TelefonoEntrega`
**Fichero:** `controllers/mensajes_registrados.py`, línea 24

```python
# Actual (roto):
gestor_pedidos.iniciar_pedido(id_usuario, direccion_usuario, nombre_usuario)
# Correcto:
gestor_pedidos.iniciar_pedido(id_usuario, direccion_usuario, numero_cliente)
```

La firma del método es `iniciar_pedido(self, id, direccion, telefono)`. Se está pasando `nombre_usuario` como `telefono`.

**Migración de datos necesaria tras el fix:**
```sql
UPDATE pedidos
SET TelefonoEntrega = (
    SELECT numero_cliente FROM usuarios WHERE usuarios.id = pedidos.ClienteID
)
WHERE TelefonoEntrega NOT LIKE 'whatsapp:%'
```

**Esfuerzo:** S | **Dependencia:** Ninguna

---

### BUG-1: `order_id` como string en filtro de integer en webhook de Monei
**Fichero:** `blueprints/webhook.py`, línea 97

```python
try:
    order_id = int(order_id)
except (TypeError, ValueError):
    logger.error("webhook_monei: orderId inválido: %s", order_id)
    return jsonify({"error": "orderId inválido"}), 400
```

**Esfuerzo:** S | **Dependencia:** Ninguna

---

### BUG-2: `cache` expone el cliente Redis raw
**Fichero:** `services/__init__.py`, línea 23

```python
# Actual:
cache = redismanager.client
# Correcto:
cache = redismanager
```

Permite que todos los callers usen el wrapper con retry y logging en lugar del cliente crudo.

**Esfuerzo:** S | **Dependencia:** Verificar que todos los usos de `cache` solo llamen `.get` y `.set`

---

### BUG-3: `generar_token_temporal` devuelve tupla en error en lugar de lanzar excepción
**Fichero:** `services/token_service.py`, líneas 17–18

```python
# Actual (genera URL rota como "https://domain.com/menu/Datos de usuario inválidos."):
return "Datos de usuario inválidos.", 400

# Correcto:
raise ValueError(f"Datos de usuario inválidos: {e}") from e
```

**Esfuerzo:** S | **Dependencia:** Ninguna

---

### BUG-4: `confirmar_direccion` devuelve entero `1` como centinela mágico
**Fichero:** `controllers/registro.py`, línea 36

```python
# Actual:
return 1
# Correcto:
return False
```

Y en el caller (línea 178): `if respuesta is False:`

**Esfuerzo:** S | **Dependencia:** Ninguna

---

### BUG-5 (ERR-1): Template `error.html` no existe
**Fichero:** `blueprints/menu.py`, línea 27

Referenciado pero ausente → Flask lanza `TemplateNotFound` → 500 en lugar del 403 esperado.

Crear `templates/error.html` mínimo que muestre `{{ mensaje }}`.

**Esfuerzo:** S | **Dependencia:** Ninguna

---

### BUG-6 (ERR-2): `last_pedido` usado sin comprobar `None`
**Fichero:** `blueprints/menu.py`, línea 57

```python
if last_pedido is None:
    return render_template("error.html", mensaje="No tienes ningún pedido activo."), 404
```

**Esfuerzo:** S | **Dependencia:** BUG-5

---

### ERR-4: `iniciar_pago` no valida que el pedido esté en estado `ENLACE2`
**Fichero:** `controllers/pago.py`, líneas 33–34

Sin este guard, una llamada doble puede insertar filas `PedidoDetalle` duplicadas sin error.

```python
if pedido_activo.Estado != EstadoPedido.ENLACE2:
    logger.error(
        "iniciar_pago: pedido %s en estado inesperado '%s'",
        pedido_activo.PedidoID, pedido_activo.Estado
    )
    return False, "El pedido no está listo para procesar el pago"
```

**Esfuerzo:** S | **Dependencia:** Ninguna

---

## Fase 3 — Calidad y Deuda Técnica

**Objetivo:** Eliminar código duplicado, inconsistencias y patrones que hacen el sistema difícil de mantener y depurar.

**Criterio de aceptación:** `grep -r "os.environ.get" --include="*.py"` no devuelve resultados fuera de `config.py` y `database.py`. `grep -r "print(" --include="*.py"` no devuelve resultados en ningún módulo de la aplicación.

---

### TD-1: Consolidar acceso a variables de entorno en `config.py`

Módulos que bypass `config.py` directamente con `os.environ.get`:
- `services/twilio_service.py` líneas 7–9
- `services/token_service.py` línea 34
- `blueprints/api.py` líneas 39, 74
- `managers/gestor_redis.py` líneas 84–86
- `services/maps_service.py` línea 13

Reemplazar cada `os.environ.get(X)` por `config.X`. `database.py` puede mantenerse como excepción por su inicialización temprana.

**Esfuerzo:** S | **Dependencia:** Ninguna

---

### TD-2: Eliminar `limpiar_texto` duplicada

`utils/menu_opciones.py` (usa `unidecode`) y `utils/text_utils.py` (usa `unicodedata`) tienen implementaciones distintas con comportamiento diferente. El webhook y el menú normalizan texto de forma inconsistente.

1. Adoptar `unidecode` como canónica (más robusta para español).
2. Mover a `utils/text_utils.py`, eliminar de `menu_opciones.py`.
3. Actualizar todos los imports.

**Esfuerzo:** S | **Dependencia:** Ninguna

---

### TD-3: Eliminar clases wrapper estáticas innecesarias
**Fichero:** `controllers/registro.py`

`Mensajeria` (línea 39), `ValidacionNombre` (línea 102), `ValidacionDireccion` (línea 114) son clases con solo `@staticmethod`. Sin estado, sin polimorfismo, sin valor.

Convertir cada método estático en función de módulo.

**Esfuerzo:** M | **Dependencia:** TD-13

---

### TD-5: Importaciones diferidas → inyección de dependencias explícita

Controllers con imports diferidos dentro de funciones:
- `controllers/mensajes_registrados.py` líneas 17, 38
- `controllers/pedido.py` línea 29
- `controllers/registro.py` línea 26

El patrón correcto ya existe en `controllers/pago.py` y `confirmar_carrito`. Extenderlo al resto: los singletons se pasan como parámetros desde los blueprints.

**Esfuerzo:** M | **Dependencia:** Ninguna

---

### TD-6/7: Singletons de `services/__init__.py` → lazy init

`GestorPedidos()`, `GestorUsuarios()`, `ProductoManager()` y `redismanager` se instancian al importar. Esto obliga a tener Redis disponible en cualquier contexto de test.

Convertir a lazy singletons siguiendo el patrón de `get_monei()`:

```python
_gestor_pedidos = None
def get_gestor_pedidos():
    global _gestor_pedidos
    if _gestor_pedidos is None:
        _gestor_pedidos = GestorPedidos()
    return _gestor_pedidos
```

**Esfuerzo:** M | **Dependencia:** TD-5

---

### TD-12: `logging.basicConfig` llamado dos veces

Centralizar la configuración de logging únicamente en `create_app()` antes de los imports de blueprints. Ningún otro módulo debe llamar a `basicConfig`.

**Esfuerzo:** S | **Dependencia:** Ninguna

---

### TD-13: `print()` en lugar de `logger`

Ficheros afectados:
- `controllers/mensajes_registrados.py` (múltiples líneas)
- `controllers/pedido.py` líneas 22, 57
- `managers/gestor_redis.py` líneas 74, 79
- `managers/gestor_usuarios.py` líneas 34, 35, 37, 61, 62
- `database.py` líneas 59, 61

Reemplazar cada `print(...)` por `logger.*`. Añadir `logger = logging.getLogger(__name__)` donde falte.

**Esfuerzo:** S | **Dependencia:** Ninguna

---

### TD-14: f-string en llamada a `logger.info`
**Fichero:** `blueprints/webhook.py`, línea 34

```python
# Actual (evalúa el string aunque el log esté desactivado):
logger.info(f"Mensaje recibido de {numero_cliente}: {mensaje_cliente}")

# Correcto:
logger.info("Mensaje recibido de %s: %s", numero_cliente, mensaje_cliente)
```

**Esfuerzo:** S | **Dependencia:** Ninguna

---

### TD-16: Clasificación de errores por inspección de string
**Fichero:** `blueprints/api.py`, líneas 78–80

```python
# Actual (frágil — el código HTTP cambia si el mensaje de error cambia):
return jsonify({"error": result}), 400 if "Producto" in result else 500
```

Cambiar `iniciar_pago` y `confirmar_carrito` para devolver `(success: bool, message: str, http_code: int)`. El blueprint usa directamente el código HTTP devuelto.

**Esfuerzo:** M | **Dependencia:** Los tests de `test_api_pedido.py` necesitan actualización

---

### TD-10: Limpiar templates y código huérfano

- `templates/map_orders.html` — no referenciado desde ningún blueprint
- `templates/piking.html` — idem
- `cocina/comandas.py` — fichero vacío

Verificar con `git log --all -- templates/map_orders.html` antes de eliminar.

**Esfuerzo:** S | **Dependencia:** Ninguna

---

### TD-11: `requirements.txt` incompleto

Paquetes importados en producción pero ausentes del fichero:
- `shapely`
- `spacy`
- `sentry-sdk`
- `tenacity`
- `Monei`

Además hay entrada duplicada: `dotenv==0.9.9` y `python-dotenv==1.0.1` son el mismo paquete — eliminar `dotenv==0.9.9`.

Ejecutar `pip freeze > requirements.txt` con el venv activo.

**Esfuerzo:** S | **Dependencia:** Ninguna

---

### TD menor: Ruta legacy del webhook de Monei
**Fichero:** `blueprints/webhook.py`, línea 80

La ruta `/webhoo/monei` (typo) existe solo para compatibilidad con la configuración anterior del dashboard de Monei. Eliminar una vez que el dashboard apunte a `/webhook/monei`.

**Esfuerzo:** S | **Dependencia:** Coordinación con el dashboard de Monei

---

## Fase 4 — Cobertura de Tests

**Objetivo:** Tests automatizados para todos los flujos críticos de negocio.

**Criterio de aceptación:** `pytest --cov=. --cov-report=term` muestra cobertura superior al 70% en `blueprints/`, `controllers/` y `managers/`. Tests de HMAC de Monei y de firma de Twilio presentes.

---

### TEST-1: Mock de Redis en `conftest.py`

La fixture `app` actual requiere Redis disponible. Añadir fixture con `fakeredis` o `unittest.mock.patch`:

```python
@pytest.fixture(scope="session", autouse=True)
def mock_redis():
    with patch("managers.gestor_redis.redis.Redis") as mock:
        mock.return_value.ping.return_value = True
        mock.return_value.get.return_value = None
        mock.return_value.set.return_value = True
        yield mock
```

**Esfuerzo:** M | **Dependencia:** TD-6 (lazy init facilita enormemente)

---

### TEST-2: Tests del webhook de Twilio con firma válida e inválida

Nuevo `tests/test_webhook.py`:
1. POST con firma Twilio válida + usuario registrado → 200
2. POST con firma Twilio inválida → 403
3. POST con número bloqueado por rate-limit → 403
4. POST con payload malformado (sin `From`) → 400

**Esfuerzo:** M | **Dependencia:** SEC-1, TEST-1

---

### TEST-3: Tests del webhook de Monei con HMAC

En `tests/test_webhook.py`:
1. POST con HMAC correcto + `status=SUCCEEDED` → 200, pedido marcado como pagado
2. POST con HMAC incorrecto → 401
3. POST sin header `MONEI-SIGNATURE` → 401
4. POST con `orderId` no numérico → 400 (tras BUG-1)

**Esfuerzo:** M | **Dependencia:** BUG-1, TEST-1

---

### TEST-4: Tests de `GET /menu/<token>`

Nuevo `tests/test_menu.py`:
1. Token válido + pedido en `ENLACE` → renderiza `quiniela.html` (200)
2. Token expirado → 403
3. Token válido + pedido en `ENLACE2` → redirect a `/confirmacion_pago`
4. Token válido + `last_pedido` es `None` → 404 (tras BUG-6)

**Esfuerzo:** M | **Dependencia:** BUG-5, BUG-6, TEST-1

---

### TEST-5: Tests de `token_service`

Nuevo `tests/test_token_service.py`:
1. `generar_token_temporal` con datos válidos → devuelve string
2. `generar_token_temporal` con datos inválidos → lanza `ValueError` (tras BUG-3)
3. `generar_enlace` → devuelve URL con formato correcto

**Esfuerzo:** S | **Dependencia:** BUG-3, TEST-1

---

### TEST-6: Tests de `gestor_usuarios` con BD simulada

Nuevo `tests/test_gestor_usuarios.py`:
- `verificar_usuario`, `obtener_usuario_completo`, `guardar_usuario`
- Usar `unittest.mock.patch` en la sesión SQLAlchemy

**Esfuerzo:** M | **Dependencia:** TEST-1

---

### TEST-7: Tests del endpoint `/api/cambiar_estado_a_enlace`

En `tests/test_api_pedido.py`:
1. Sin token de autenticación → 401 (tras SEC-2)
2. Con token válido + pedido en `CONFIRMANDO_PAGO` → 400
3. Con token válido + pedido en `ENLACE2` → 200

**Esfuerzo:** S | **Dependencia:** SEC-2

---

## Tabla resumen

| ID | Fase | Fichero principal | Esfuerzo | Dependencias |
|----|------|------------------|----------|--------------|
| SEC-1 | 1 | `blueprints/webhook.py` | M | — |
| SEC-2 | 1 | `blueprints/api.py:88` | S | — |
| SEC-3 | 1 | `main.py:23` | S | — |
| SEC-4 | 1 | `main.py:24` | S | — |
| SEC-5 | 1 | `controllers/pago.py:66` | S | — |
| SEC-6 | 1 | `main.py:30`, `blueprints/api.py:19-54` | S | — |
| BUG-CRÍTICO | 2 | `controllers/mensajes_registrados.py:24` | S | — |
| BUG-1 | 2 | `blueprints/webhook.py:97` | S | — |
| BUG-2 | 2 | `services/__init__.py:23` | S | — |
| BUG-3 | 2 | `services/token_service.py:17` | S | — |
| BUG-4 | 2 | `controllers/registro.py:36` | S | — |
| BUG-5 | 2 | crear `templates/error.html` | S | — |
| BUG-6 | 2 | `blueprints/menu.py:57` | S | BUG-5 |
| ERR-4 | 2 | `controllers/pago.py:33` | S | — |
| TD-1 | 3 | múltiples | S | — |
| TD-2 | 3 | `utils/` | S | — |
| TD-3 | 3 | `controllers/registro.py` | M | TD-13 |
| TD-5 | 3 | controllers | M | — |
| TD-6/7 | 3 | `services/__init__.py` | M | TD-5 |
| TD-12 | 3 | `main.py` | S | — |
| TD-13 | 3 | múltiples | S | — |
| TD-14 | 3 | `blueprints/webhook.py:34` | S | — |
| TD-16 | 3 | `blueprints/api.py:78` | M | — |
| TD-10 | 3 | templates huérfanas | S | — |
| TD-11 | 3 | `requirements.txt` | S | — |
| TEST-1 | 4 | `tests/conftest.py` | M | TD-6 |
| TEST-2 | 4 | `tests/test_webhook.py` | M | SEC-1, TEST-1 |
| TEST-3 | 4 | `tests/test_webhook.py` | M | BUG-1, TEST-1 |
| TEST-4 | 4 | `tests/test_menu.py` | M | BUG-5/6, TEST-1 |
| TEST-5 | 4 | `tests/test_token_service.py` | S | BUG-3 |
| TEST-6 | 4 | `tests/test_gestor_usuarios.py` | M | TEST-1 |
| TEST-7 | 4 | `tests/test_api_pedido.py` | S | SEC-2 |

---

## Orden de commits recomendado

Cada commit debe ser atómico (un issue = un commit) para poder usar `git bisect` si algo rompe.

```
fix(sec): mover DSN de Sentry a variable de entorno SENTRY_DSN
fix(sec): desactivar send_default_pii en Sentry (RGPD)
fix(sec): eliminar handlers OPTIONS manuales y restringir CORS
fix(sec): autenticar endpoint /api/cambiar_estado_a_enlace
fix(data): corregir argumento telefono en iniciar_pedido
fix(data): convertir orderId a int en webhook Monei
fix(data): exponer redismanager en lugar de cliente raw en services
fix(data): generar_token_temporal lanza ValueError en vez de devolver tupla
fix(data): confirmar_direccion retorna False en vez de 1
fix(data): añadir guard de estado ENLACE2 en iniciar_pago
fix(ui): crear templates/error.html
fix(ui): comprobar None en last_pedido antes de acceder a .Estado
fix(sec): añadir verificación de firma Twilio en POST /webhook
fix(sec): reemplazar email placeholder en Monei
refactor: consolidar acceso a env vars en config.py
refactor: unificar limpiar_texto en text_utils
refactor: sustituir print() por logger en todos los módulos
refactor: eliminar clases wrapper estáticas en registro.py
refactor: eliminar importaciones diferidas — inyección explícita
refactor: convertir singletons de services a lazy init
refactor: clasificación de errores API con código HTTP en tupla
chore: completar requirements.txt con dependencias faltantes
chore: eliminar templates y ficheros huérfanos
test: añadir fixture mock_redis en conftest
test: tests webhook Twilio con y sin firma
test: tests webhook Monei con y sin HMAC
test: tests GET /menu/<token>
test: tests token_service
test: tests gestor_usuarios
test: tests /api/cambiar_estado_a_enlace
```
