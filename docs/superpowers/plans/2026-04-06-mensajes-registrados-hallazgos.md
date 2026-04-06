# Corrección hallazgos mensajes_registrados Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corregir los hallazgos H1, H3, H4, H5, H6, H7 de la auditoría de `controllers/mensajes_registrados.py` para eliminar crasheos silenciosos, pedidos duplicados y puntos ciegos en observabilidad.

**Architecture:** Todos los cambios van en un único archivo (`controllers/mensajes_registrados.py`). No se modifican el notifier ni los managers. El lock de Redis sigue el patrón `SET NX EX` ya establecido en el proyecto con `bloqueo:<phone>`.

**Tech Stack:** Python, Flask, SQLAlchemy, Redis (via `redismanager` singleton de `container`), pytest.

**Spec:** `docs/superpowers/specs/2026-04-06-mensajes-registrados-hallazgos-design.md`

---

## Archivos modificados

| Archivo | Acción |
|---------|--------|
| `controllers/mensajes_registrados.py` | Modificar — todos los hallazgos |
| `managers/gestor_redis.py` | Modificar — añadir método `adquirir_lock` (H3 requiere SET NX, no soportado por `set()` actual) |
| `tests/test_mensajes_registrados.py` | Modificar — actualizar mock en test existente afectado por H3 |

---

### Task 1: H7 — Cambiar nivel de log para usuario no encontrado

**Files:**
- Modify: `controllers/mensajes_registrados.py:50`

- [ ] **Step 1: Hacer el cambio**

En `controllers/mensajes_registrados.py`, línea 50, cambiar `logger.error` por `logger.warning`:

```python
# antes
logger.error("Error: No se encontraron datos para el usuario %s.", numero_cliente)

# después
logger.warning("Error: No se encontraron datos para el usuario %s.", numero_cliente)
```

- [ ] **Step 2: Verificar que los tests existentes siguen pasando**

```bash
pytest tests/test_mensajes_registrados.py -v --tb=short
```

Expected: todos los tests en PASS (ninguno testea el nivel de log directamente).

- [ ] **Step 3: Commit**

```bash
git add controllers/mensajes_registrados.py
git commit -m "fix: logger.warning para usuario no encontrado (H7)"
```

---

### Task 2: H6 — Log cuando el enlace de pedido está caducado

**Files:**
- Modify: `controllers/mensajes_registrados.py:82-83`

- [ ] **Step 1: Añadir log antes de enviar enlace caducado**

En `controllers/mensajes_registrados.py`, dentro del bloque `if not enlace:` (líneas 82-84), añadir el log:

```python
        if estado_del_pedido == EstadoPedido.ENLACE or estado_del_pedido == EstadoPedido.ENLACE2:
            enlace = pedido_activo.enlace
            if not enlace:
                logger.info("ENLACE_CADUCADO pedido=%s usuario=%s", id_pedido_activo, numero_cliente)
                _enviar_enlace_caducado(numero_cliente)
                return " mensaje enviado", 200
            _enviar_enlace_pedido(enlace, numero_cliente)
            return " mensaje enviado", 200
```

- [ ] **Step 2: Verificar tests**

```bash
pytest tests/test_mensajes_registrados.py -v --tb=short
```

Expected: todos en PASS.

- [ ] **Step 3: Commit**

```bash
git add controllers/mensajes_registrados.py
git commit -m "fix: log ENLACE_CADUCADO para observabilidad (H6)"
```

---

### Task 3: H5 — Log en el fallthrough final

**Files:**
- Modify: `controllers/mensajes_registrados.py:106`

- [ ] **Step 1: Añadir log de warning antes del fallthrough**

En `controllers/mensajes_registrados.py`, líneas 106-107, reemplazar:

```python
        _enviar_error_generico(numero_cliente)
        return " mensaje enviado", 200
```

por:

```python
        logger.warning(
            "ESTADO_NO_CONTEMPLADO pedido=%s estado=%s usuario=%s mensaje=%r",
            id_pedido_activo, estado_del_pedido, numero_cliente, mensaje_cliente,
        )
        _enviar_error_generico(numero_cliente)
        return " mensaje enviado", 200
```

- [ ] **Step 2: Verificar tests**

```bash
pytest tests/test_mensajes_registrados.py -v --tb=short
```

Expected: todos en PASS.

- [ ] **Step 3: Commit**

```bash
git add controllers/mensajes_registrados.py
git commit -m "fix: log ESTADO_NO_CONTEMPLADO en fallthrough (H5)"
```

---

### Task 4: H1 — Guard para retorno None de `_enviar_estado_en_curso`

**Files:**
- Modify: `controllers/mensajes_registrados.py:104`

- [ ] **Step 1: Reemplazar el return directo por un guard**

En `controllers/mensajes_registrados.py`, línea 104, reemplazar:

```python
            return _enviar_estado_en_curso(pedido_activo, numero_cliente)
```

por:

```python
            resultado = _enviar_estado_en_curso(pedido_activo, numero_cliente)
            if resultado is None:
                logger.error(
                    "ESTADO_NO_MANEJADO pedido=%s estado=%s usuario=%s",
                    id_pedido_activo, estado_del_pedido, numero_cliente,
                )
                _enviar_error_generico(numero_cliente)
                return "estado no contemplado", 200
            return resultado
```

- [ ] **Step 2: Verificar tests**

```bash
pytest tests/test_mensajes_registrados.py -v --tb=short
```

Expected: todos en PASS.

- [ ] **Step 3: Commit**

```bash
git add controllers/mensajes_registrados.py
git commit -m "fix: guard para retorno None de _enviar_estado_en_curso (H1)"
```

---

### Task 5: H4 — try/except alrededor de `procesar_pedido`

**Files:**
- Modify: `controllers/mensajes_registrados.py:74-78`

- [ ] **Step 1: Envolver procesar_pedido en try/except**

En `controllers/mensajes_registrados.py`, reemplazar el bloque del estado PENDIENTE (líneas 74-78):

```python
        if estado_del_pedido == EstadoPedido.PENDIENTE:
            mensaje = procesar_pedido(mensaje_cliente, numero_cliente, id_pedido_activo, usuario_datos)
            logger.debug("Mensaje procesado para usuario: %s", numero_cliente)
            _enviar_respuesta_pedido(mensaje, numero_cliente)
            return " mensaje enviado", 200
```

por:

```python
        if estado_del_pedido == EstadoPedido.PENDIENTE:
            try:
                mensaje = procesar_pedido(mensaje_cliente, numero_cliente, id_pedido_activo, usuario_datos)
            except Exception as e:
                logger.error(
                    "ERROR_PROCESAR_PEDIDO usuario=%s error=%s",
                    numero_cliente, e, exc_info=True,
                )
                _enviar_error_generico(numero_cliente)
                return "error procesando pedido", 200
            logger.debug("Mensaje procesado para usuario: %s", numero_cliente)
            _enviar_respuesta_pedido(mensaje, numero_cliente)
            return " mensaje enviado", 200
```

- [ ] **Step 2: Verificar tests**

```bash
pytest tests/test_mensajes_registrados.py -v --tb=short
```

Expected: todos en PASS.

- [ ] **Step 3: Commit**

```bash
git add controllers/mensajes_registrados.py
git commit -m "fix: try/except alrededor de procesar_pedido (H4)"
```

---

### Task 6: H3 — Redis lock de idempotencia en `_iniciar_pedido_y_enviar_menu`

**Files:**
- Modify: `managers/gestor_redis.py` — añadir método `adquirir_lock`
- Modify: `controllers/mensajes_registrados.py:2` (import) y `:26-41` (método)
- Modify: `tests/test_mensajes_registrados.py` — actualizar mock en test existente afectado

**Contexto:** El método `set()` de `RedisManager` no acepta `nx=True`. El patrón correcto ya existe en `ya_procesado_wamid` que llama a `self.client.set(..., nx=True)` directamente. Se añade un método `adquirir_lock` para mantener la abstracción limpia, siguiendo ese mismo patrón.

- [ ] **Step 1: Añadir `adquirir_lock` a `RedisManager`**

En `managers/gestor_redis.py`, añadir el método a continuación de `ya_procesado_wamid` (línea 100, antes de `redismanager = ...`):

```python
    def adquirir_lock(self, key: str, ttl: int = 10) -> bool:
        """Intenta adquirir un lock atómico con SET NX. Devuelve True si se adquirió.

        Usa SET NX para que la comprobación y el registro sean una sola operación
        Redis — dos requests concurrentes con la misma clave no pueden adquirir ambas.
        En caso de error Redis devuelve False: mejor ignorar el lock que bloquear indefinidamente.
        """
        try:
            resultado = self.client.set(key, "1", ex=ttl, nx=True)
            return resultado is not None  # None = clave ya existía = lock no adquirido
        except redis.RedisError as e:
            logger.error("Error al adquirir lock %s: %s", key, e)
            return True  # fail-open: ante error Redis, dejar pasar para no bloquear al usuario
```

- [ ] **Step 2: Añadir redismanager al import del controlador**

En `controllers/mensajes_registrados.py`, línea 2, cambiar:

```python
from container import gestor_pedidos, gestor_usuarios
```

por:

```python
from container import gestor_pedidos, gestor_usuarios, redismanager
```

- [ ] **Step 3: Añadir lock al inicio de `_iniciar_pedido_y_enviar_menu`**

En `controllers/mensajes_registrados.py`, reemplazar el método completo `_iniciar_pedido_y_enviar_menu` (líneas 25-41):

```python
    @staticmethod
    def _iniciar_pedido_y_enviar_menu(numero_cliente, usuario_datos):
        """Abre un pedido nuevo para el usuario y le envía el menú inicial."""

        lock_key = f"pedido_lock:{numero_cliente}"
        if not redismanager.adquirir_lock(lock_key, ttl=10):
            logger.info("LOCK_PEDIDO ya activo para %s — ignorando duplicado.", numero_cliente)
            return "mensaje enviado", 200

        id_usuario = usuario_datos["id"]
        direccion_usuario = usuario_datos["direccion"]
        nombre_usuario = usuario_datos["nombre"]

        try:
            gestor_pedidos.iniciar_pedido(id_usuario, direccion_usuario, numero_cliente)
        except (SQLAlchemyError, OperationalError) as error:
            logger.error("Error al iniciar el pedido para el usuario %s: %s", id_usuario, error)
            return "Error al procesar el pedido. Inténtalo más tarde.", 500

        menu_texto = mostrar_menu()
        _enviar_bienvenida_menu(nombre_usuario, menu_texto, numero_cliente)
        return "Mensaje enviado", 200
```

- [ ] **Step 4: Actualizar el test existente que ejercita este path**

En `tests/test_mensajes_registrados.py`, el test `test_sin_pedido_activo_inicia_nuevo_pedido` (clase `TestFlujosNoBloqueados`) llama al path que ahora usa `redismanager`. Hay que añadir el mock. Reemplazar el test completo:

```python
    def test_sin_pedido_activo_inicia_nuevo_pedido(self):
        """Sin pedido activo → inicia nuevo pedido (flujo normal intacto)."""
        with patch("controllers.mensajes_registrados.gestor_usuarios") as mock_gu, \
             patch("controllers.mensajes_registrados.gestor_pedidos") as mock_gp, \
             patch("controllers.mensajes_registrados.redismanager") as mock_redis, \
             patch("controllers.mensajes_registrados_notifier.enviar_mensaje_whatsapp"), \
             patch("controllers.mensajes_registrados_notifier.config"):
            mock_gu.obtener_usuario_completo.return_value = USUARIO_DATOS
            mock_gp.obtener_pedido_mas_reciente.return_value = None
            mock_gp.iniciar_pedido.return_value = 100
            mock_redis.adquirir_lock.return_value = True  # lock adquirido
            result = ManejadorMensajesRegistrados.manejar_mensajes_registrados(NUMERO, "1")
        mock_gp.iniciar_pedido.assert_called_once()
        assert result[1] == 200
```

- [ ] **Step 5: Verificar tests**

```bash
pytest tests/test_mensajes_registrados.py -v --tb=short
```

Expected: todos en PASS.

- [ ] **Step 6: Commit**

```bash
git add managers/gestor_redis.py controllers/mensajes_registrados.py tests/test_mensajes_registrados.py
git commit -m "fix: Redis lock de idempotencia en _iniciar_pedido_y_enviar_menu (H3)"
```

---

### Task 7: Verificación final

- [ ] **Step 1: Ejecutar suite completa**

```bash
pytest -v --tb=short
```

Expected: todos los tests en PASS. Los 3 tests que fallaban antes de este trabajo (pre-existing failures documentados en memoria del proyecto) siguen fallando — son regresiones previas, no introducidas aquí.

- [ ] **Step 2: Revisar el archivo final completo**

```bash
# Verificar que el archivo tiene sentido como un todo
cat -n controllers/mensajes_registrados.py
```

Puntos a confirmar visualmente:
- Import de `redismanager` en línea 2
- Lock en las primeras líneas de `_iniciar_pedido_y_enviar_menu`
- `try/except` alrededor de `procesar_pedido`
- Guard para `None` antes del `return _enviar_estado_en_curso`
- Log `ENLACE_CADUCADO` presente en el bloque ENLACE
- Log `ESTADO_NO_CONTEMPLADO` antes del fallthrough
- `logger.warning` (no `error`) para usuario no encontrado

- [ ] **Step 3: Commit final si hubo ajustes menores**

```bash
git add controllers/mensajes_registrados.py
git commit -m "fix: ajustes menores tras revisión final"
```

Solo si hubo cambios. Si no, omitir.
