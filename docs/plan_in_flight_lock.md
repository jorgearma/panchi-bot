# Plan de implementación — In-flight lock por usuario

Guard que ignora/rechaza mensajes entrantes de un usuario mientras el bot
todavía está procesando un mensaje previo de ese mismo usuario. Cierra la
clase de bugs silenciosos por concurrencia que el lock temporal actual no
previene cuando el procesamiento tarda más que su TTL.

---

## 1. Contexto y problema actual

Flujo real de un mensaje entrante:

```
POST /webhook  →  blueprints/webhook  →  message_queue.encolar
                                       ↓
                                 RQ queue "whatsapp"
                                       ↓
worker.py  →  _job_procesar_mensaje  →  services/inbound_whatsapp.enrutar_mensaje
                                       ↓
                           (controllers / managers)
```

`services/inbound_whatsapp.py:118-120` ya usa un **lock temporal de 4 s**:

```python
if redismanager.esta_bloqueado(numero_cliente):
    return "Número bloqueado", 403
redismanager.bloquear_usuario(numero_cliente, duracion=4)
```

Problema: si el procesamiento tarda >4 s (API Google Maps lenta, BD lenta,
reintentos de `tenacity`), el lock expira mientras el worker sigue
trabajando. Un segundo mensaje del mismo usuario pasa el guard y entra en
el pipeline → race real: doble `guardar_usuario`, doble `iniciar_pedido`,
estados inconsistentes en Redis.

Además: al devolver `403` a Meta, Meta reintenta el webhook → bucle de
reintentos hasta que el contador de Meta se agota.

**Objetivo:** reemplazar el lock temporal por un lock cuya vida coincide
con la duración real del procesamiento, con TTL de seguridad como red.

---

## 2. Ubicación por capa de responsabilidad

Respetando la arquitectura declarada en `CLAUDE.md`:

| Capa | Responsabilidad en este feature |
|------|--------------------------------|
| `managers/gestor_redis.py` | Primitivas `adquirir_lock`/`liberar_lock` y un context manager `lock_procesamiento(numero)` con TTL. **Data access puro, sin conocer WhatsApp.** |
| `services/inbound_whatsapp.py` | Uso del context manager envolviendo `enrutar_mensaje`. Decide qué hacer cuando el lock está tomado (mensaje al usuario). **Es la capa de adapter de entrada — el lock de concurrencia de mensajes entrantes es su responsabilidad natural.** |
| `controllers/*` | Sin cambios. No deben saber del lock. |
| `blueprints/webhook.py` | Sin cambios. La blueprint sólo encola; el lock vive un nivel más abajo. |

**Por qué en `services/inbound_whatsapp.py` y no en la blueprint:**
el lock debe aplicarse en el momento del procesamiento real, no al
recibir el HTTP. Si se pusiera en la blueprint, la blueprint encolaría
igualmente, el job entraría en RQ, y el lock se habría verificado contra
un estado desfasado. Enforzarlo dentro del worker garantiza orden real.

**Por qué el primitivo va a `gestor_redis` y no a un nuevo servicio:**
`adquirir_lock` y `esta_bloqueado` ya viven allí. Coherencia con el
código existente y capa correcta.

---

## 3. Diseño

### 3.1 Primitiva — `managers/gestor_redis.py`

Añadir un método de liberación y un context manager:

```python
def liberar_lock(self, key: str) -> None:
    """Libera un lock adquirido con adquirir_lock. Idempotente."""
    try:
        self.client.delete(key)
    except redis.RedisError as e:
        logger.error("Error al liberar lock %s: %s", key, e)

@contextmanager
def lock_procesamiento(self, numero: str, ttl: int = 30):
    """Lock in-flight por usuario para serializar procesamiento de mensajes.

    Rinde True si se adquirió, False si otro procesamiento está activo.
    Siempre libera el lock al salir del bloque (vía finally interno).
    """
    key = f"procesando:{numero}"
    adquirido = self.adquirir_lock(key, ttl=ttl)
    try:
        yield adquirido
    finally:
        if adquirido:
            self.liberar_lock(key)
```

- **Clave:** `procesando:<numero>` — namespace explícito, distinto del
  `bloqueo:<numero>` del anti-spam actual y del `pedido_lock:<numero>`
  de `controllers/mensajes_registrados.py:31`.
- **TTL:** 30 s. Mayor que cualquier procesamiento razonable (maps +
  BD + Meta API), suficientemente corto como para no dejar al usuario
  tirado más de medio minuto si el worker muere.
- **Fail-open heredado:** `adquirir_lock` ya devuelve `True` ante error
  de Redis (línea 131), así que un Redis caído no bloquea a los
  usuarios — coherente con el patrón existente.

### 3.2 Enforcement — `services/inbound_whatsapp.py:enrutar_mensaje`

Reemplazar el bloque `esta_bloqueado` / `bloquear_usuario(4)` por el
context manager. Estructura objetivo:

```python
def enrutar_mensaje(numero_cliente, mensaje_cliente):
    if not redismanager.incrementar_contador_hora(numero_cliente):
        logger.warning("RATE_LIMIT_HORA usuario=%s", numero_cliente)
        return "Límite de mensajes por hora superado", 429

    with redismanager.lock_procesamiento(numero_cliente, ttl=30) as adquirido:
        if not adquirido:
            logger.info("IN_FLIGHT_LOCK usuario=%s — mensaje descartado", numero_cliente)
            enviar_mensaje_whatsapp(
                "⏳ Aún estoy procesando tu mensaje anterior. Dame un segundo…",
                numero_cliente,
            )
            return "Procesamiento en curso", 200

        logger.info("MSG_CLIENTE usuario=%s mensaje=%r", numero_cliente, mensaje_cliente)

        try:
            usuario = gestor_usuarios.verificar_usuario(numero_cliente)
        except (RetryError, SQLAlchemyError) as e:
            ...

        try:
            if not usuario:
                return manejar_registro(numero_cliente, mensaje_cliente, redismanager)
            return ManejadorMensajesRegistrados.manejar_mensajes_registrados(
                numero_cliente, mensaje_cliente
            )
        except Exception:
            logger.exception("Error procesando mensaje de %s:", numero_cliente)
            enviar_mensaje_whatsapp(_MSG_ERROR_PROCESANDO, numero_cliente)
            return jsonify({"error": "Error procesando el mensaje"}), 500
```

Puntos clave:
- **El rate limit queda FUERA del lock** — rechazar por exceso horario
  no debe ocupar el slot de procesamiento.
- **200 en vez de 403** cuando el lock está tomado. Meta no reintenta.
  El mensaje queda aceptado desde el punto de vista HTTP y simplemente
  descartado a nivel aplicación con aviso al usuario.
- **`finally` implícito en el context manager** garantiza que el lock
  se libera siempre, incluso si el controller lanza una excepción no
  capturada.

### 3.3 UX — mensaje de "espera"

Se responde con un único mensaje corto:

> ⏳ Aún estoy procesando tu mensaje anterior. Dame un segundo…

Alternativa descartada: drop silencioso. Sería más simple pero deja al
usuario sin feedback — genera exactamente la percepción de "bot roto"
que queremos evitar. El coste es 1 mensaje WhatsApp extra en casos de
carrera reales (infrecuentes).

---

## 4. Interacción con código existente

| Componente | Acción |
|------------|--------|
| `bloquear_usuario(duracion=4)` (`services/inbound_whatsapp.py:120`) | **Eliminar.** El lock in-flight lo sustituye con mejor semántica. |
| `esta_bloqueado(numero)` check (línea 118) | **Eliminar** junto con lo anterior. |
| `bloquear_usuario` en `gestor_redis.py:72` | **Mantener** — puede usarse en otros contextos (bans manuales). Sólo se retira el uso en `enrutar_mensaje`. |
| `pedido_lock:<numero>` en `mensajes_registrados.py:31` | **Mantener sin cambios.** Es un lock distinto (protege creación de pedido, no procesamiento de mensaje) y vive a nivel de controller. |
| `incrementar_contador_hora` rate limit | **Mantener.** Es otra preocupación (cuota horaria, no concurrencia). |
| Redis keys existentes | `procesando:<numero>` es un namespace nuevo. No colisiona. |

---

## 5. Archivos a tocar

1. **`managers/gestor_redis.py`**
   - Importar `contextmanager` de `contextlib`.
   - Añadir `liberar_lock(key)`.
   - Añadir `lock_procesamiento(numero, ttl=30)`.

2. **`services/inbound_whatsapp.py`**
   - Reemplazar las líneas 118-120 por el bloque `with`.
   - Reindentar el resto de `enrutar_mensaje` dentro del `with`.
   - Retornar 200 (no 403) en el caso "lock tomado".

3. **`tests/test_webhook.py`** o nuevo `tests/test_inbound_lock.py`
   - Tests del nuevo comportamiento (ver §6).

4. **`docs/deuda_tecnica_registro.md`**
   - Nota mencionando que el race B3 queda mitigado por este lock.

No hay cambios en controllers, blueprints, ni en la capa de managers
más allá de `gestor_redis.py`.

---

## 6. Plan de tests

### 6.1 Unit tests de la primitiva (`tests/test_gestor_redis.py` o similar)

- `lock_procesamiento` adquirido → yield True, clave existe en Redis.
- Al salir del `with`, clave eliminada.
- Segunda llamada concurrente → yield False, clave del primero intacta.
- Excepción dentro del `with` → clave igual se libera.
- Redis caído en `adquirir_lock` → fail-open (yield True).
- Redis caído en `liberar_lock` → no propaga excepción.

### 6.2 Integración en `enrutar_mensaje`

- Primer mensaje: lock libre → se procesa normalmente.
- Segundo mensaje **mientras el primero corre** (simular con mock que
  bloquea) → se responde con el mensaje de "espera", status 200, no
  llama a controllers.
- Tras terminar el primero, tercer mensaje → se procesa normalmente
  (lock liberado).
- Excepción en controller → lock liberado (verificar con segundo
  mensaje tras la excepción).
- Rate limit horario agotado → 429 sin entrar al lock.

### 6.3 Regresión

- `tests/test_registro.py` (93 tests) debe seguir verde.
- `tests/test_mensajes_registrados.py` debe seguir verde.
- `tests/test_webhook.py` debe seguir verde tras ajustar expectativas
  del status code (200 en vez de 403 cuando el lock está tomado).

---

## 7. Riesgos y mitigaciones

| Riesgo | Probabilidad | Mitigación |
|--------|--------------|------------|
| Worker muere con lock tomado → usuario bloqueado | Baja | TTL de 30 s cierra el lock automáticamente. |
| Usuario legítimo reciben "espera" durante una carrera real | Media en edge cases | Mensaje claro, 1 segundo después pueden reenviar. |
| Meta reintenta si devolvemos != 200 | Alta si está mal | Explícitamente devolver 200 en el caso "lock tomado". |
| Redis latencia en `lock_procesamiento` añade overhead por mensaje | Muy baja | Una operación `SET NX EX` y un `DEL` — <1 ms en Redis local. |
| `adquirir_lock` fail-open ante Redis caído anula el guard | Baja | Coherente con el patrón actual. Si Redis cae, todo el bot está degradado — no es momento de bloquear. |
| Mensaje de "espera" genera spam si el usuario escribe rápido varias veces seguidas | Media | Aceptable: cada "espera" es informativo. Si preocupa, limitar a 1 por lock vivo añadiendo una segunda clave `espera_avisada:<numero>`. |

---

## 8. Pasos de implementación (orden recomendado)

1. **Añadir primitiva** en `managers/gestor_redis.py`
   (`liberar_lock`, `lock_procesamiento`). Sin tocar nada más.
2. **Tests unit** de la primitiva.
3. **Integrar en `enrutar_mensaje`**. Eliminar `esta_bloqueado`/
   `bloquear_usuario(4)`.
4. **Ajustar tests de `test_webhook.py`** si esperan 403 en el caso
   de spam (ahora es 200).
5. **Añadir tests de integración** del lock in-flight.
6. **Suite completa** (`pytest`). Todo verde excepto los 2 fallos
   preexistentes no relacionados.
7. **Smoke test manual** en dev con ngrok: enviar 2 mensajes rápidos
   al bot con un procesamiento artificialmente lento
   (`time.sleep(5)` temporal en un controller) y verificar que el
   segundo recibe el mensaje de "espera".
8. **Actualizar `docs/deuda_tecnica_registro.md`** marcando B3 como
   mitigado.

---

## 9. Criterios de aceptación

- [ ] `lock_procesamiento` existe en `gestor_redis.py` con TTL
      configurable y libera en `finally`.
- [ ] `enrutar_mensaje` usa el context manager y ya no llama a
      `bloquear_usuario(4)`.
- [ ] Un segundo mensaje durante un procesamiento activo recibe el
      mensaje "⏳ Aún estoy procesando…" y retorna 200.
- [ ] Si el controller lanza excepción, el siguiente mensaje del
      mismo usuario puede procesarse (lock liberado correctamente).
- [ ] Suite de tests pasa (salvo los 2 fallos preexistentes no
      relacionados con este cambio).
- [ ] Smoke test manual con `time.sleep` temporal demuestra el
      comportamiento esperado end-to-end.

---

## 10. Fuera de alcance (decisiones explícitamente aplazadas)

- **Deduplicación por `wamid` de Meta** (idempotencia verdadera contra
  reintentos del mismo mensaje). Es un feature distinto y más caro —
  se trata en un plan aparte si se quiere.
- **Lock distribuido entre múltiples workers con garantía fuerte
  (Redlock)**. Innecesario: un solo Redis y `SET NX` bastan para el
  modelo actual.
- **Rate limit por ventana deslizante**. El contador horario actual
  sigue siendo suficiente.
