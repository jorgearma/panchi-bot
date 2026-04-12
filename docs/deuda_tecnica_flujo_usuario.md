# Deuda técnica — Flujo de usuario (primer mensaje → confirmación de pedido)

Auditoría del camino completo: webhook → worker → registro → menú → enlace → carrito → pago.
Cada punto es un hallazgo **verificado leyendo el código actual** (no caché, no memoria).
Incluye ubicación exacta, por qué es problema y remedio concreto.

---

## 🔴 Dead-ends — el cliente se queda sin salida

### 1. ENLACE / ENLACE2 no admiten "cancelar"
**Dónde:** `controllers/mensajes_registrados.py:105-112`

**Problema:** Solo la rama `CONFIRMANDO_PAGO` (línea 128) interpreta "cancelar". Un usuario con pedido en `ENLACE` o `ENLACE2` que quiera abortar y empezar de cero no tiene forma de hacerlo: cada mensaje le devuelve el mismo enlace hasta que el cron horario lo cancele. Incoherente con el commit `7d7cd41` que habilitó el "cancelar" en pago.

**Remedio:**
- Añadir detección temprana del comando `cancelar` en la rama `ENLACE/ENLACE2`.
- Llamar `gestor_pedidos.actualizar_estado(id, CANCELADO)`, comprobar el retorno, y notificar con `_enviar_pedido_cancelado`.
- Si falla, `_enviar_error_sistema` y devolver 200 para evitar reintentos.

---

### 2. `ESPERANDO_CONFIRMACION` cancela el registro con "ok" o "vale"
**Dónde:** `controllers/registro.py:150`

**Problema:** El set de positivas aquí es `{"sí","si","quiero","adelante"}`, pero en `CONFIRMANDO_DIRECCION` se usa `RESPUESTAS_POSITIVAS` (línea 24), que incluye "ok","vale","claro","perfecto"… Si un usuario responde "vale" al saludo, se le borra el estado Redis y recibe `_enviar_registro_pendiente`. Asimetría sin justificación.

**Remedio:** Unificar con `RESPUESTAS_POSITIVAS` en ambas ramas. Un solo set de confirmaciones positivas para toda la conversación.

---

## 🟠 Silent bugs — fallan sin que nadie se entere

### 3. Monei: envío de WhatsApp sin try/except
**Dónde:** `services/inbound_whatsapp.py:236`

**Problema:** `enviar_mensaje_whatsapp(mensaje, pedido.TelefonoEntrega)` fuera de cualquier try. Si lanza (timeout Twilio/Meta, credenciales caducadas), la excepción sube, la función no devuelve 200 y Monei reintenta. La idempotencia por `referencia_externa` salva los datos pero el cliente nunca recibe la confirmación.

**Remedio:**
```python
try:
    enviar_mensaje_whatsapp(mensaje, pedido.TelefonoEntrega)
except Exception as e:
    logger.error("MONEI_NOTIFICACION_FALLIDA pedido=%s error=%s", order_id, e, exc_info=True)
    # Opcional: encolar reintento en RQ como en controllers/pago.py
```
Devolver 200 en todo caso: el pago ya está registrado, no queremos que Monei reintente el webhook por un fallo de WA.

---

### 4. Monei: eventos no-SUCCEEDED completamente silenciosos
**Dónde:** `services/inbound_whatsapp.py:189` + `239`

**Problema:** Solo se procesa si `status == 'SUCCEEDED'` o `type == 'charge.succeeded'`. Cualquier otro evento (`FAILED`, `PENDING`, `CANCELED`, `REFUNDED`, `charge.failed`, etc.) cae al return final con 200 sin un solo log. No hay manera de investigar pagos fallidos ni de detectar reembolsos.

**Remedio:**
```python
status = data.get('object', {}).get('status')
evento = data.get('type')
if status == 'SUCCEEDED' or evento == 'charge.succeeded':
    ...
else:
    logger.warning(
        "MONEI_EVENTO_NO_PROCESADO pedido=%s status=%s type=%s",
        order_id, status, evento,
    )
return jsonify({'message': 'Webhook recibido correctamente'}), 200
```

---

### 5. `amount` de Monei sin validación de tipo
**Dónde:** `services/inbound_whatsapp.py:187`

**Problema:** `data.get('object', {}).get('amount', 0) / 100`. Si `amount` viene `None` o como string, lanza `TypeError` → 500 al webhook → Monei reintenta innecesariamente.

**Remedio:**
```python
amount_raw = data.get('object', {}).get('amount')
try:
    importe_euros = int(amount_raw) / 100
except (TypeError, ValueError):
    logger.error("procesar_pago_monei: amount inválido pedido=%s amount=%r", order_id, amount_raw)
    return jsonify({"error": "amount inválido"}), 400
```

---

### 6. `procesar_pago_confirmado` confunde `Total` NULL con "importe incorrecto"
**Dónde:** `managers/pedidos/workflow_mixin.py:199-206`

**Problema:** `(pedido.Total or Decimal('0.00'))` hace que un pedido con `Total` NULL compare `importe_recibido != 0.00` y loguee "importe recibido X != total pedido 0.00 — pago rechazado". El operador no distingue entre un importe mal calculado y un pedido que nunca pasó por `confirmar_pago_online`.

**Remedio:**
```python
if pedido.Total is None:
    logger.error(
        "procesar_pago_confirmado: pedido %s sin Total fijado — flujo inconsistente, pago rechazado",
        pedido_id,
    )
    return False
total_pedido = pedido.Total.quantize(Decimal('0.01'))
```

---

### 7. `adquirir_lock` fail-open cuando Redis falla
**Dónde:** `managers/gestor_redis.py:103-115`

**Problema:** Cuando `client.set` lanza `RedisError`, devuelve `True` — el lock se considera adquirido. Si Redis cae, *todos* los locks se conceden y las race conditions vuelven sin aviso. `esta_bloqueado` también falla-open → cae en cascada.

**Remedio (dos opciones según criticidad):**
- **Conservador:** subir el log a `critical` y emitir una métrica/alerta (Sentry) en vez de `error`.
- **Estricto:** cambiar a fail-closed (`return False`) y propagar una excepción controlada que el caller traduce a un mensaje "servicio temporalmente no disponible". Más seguro pero corta el servicio si Redis está caído.

La decisión actual (fail-open) es deliberada según el comentario; como mínimo debe alertar con severidad `critical`.

---

### 8. Twilio sin dedupe de webhooks duplicados
**Dónde:** `services/inbound_whatsapp.py:158-169` + `blueprints/webhook.py:15-32`

**Problema:** `ya_procesado_wamid` solo actúa cuando el proveedor es Meta (que sí envía `wamid`). Twilio envía `MessageSid` pero no se usa, así que si Twilio reintenta el webhook (timeout, 5xx de nuestro lado), el mensaje se procesa dos veces.

**Remedio:**
- En `blueprints/webhook.py:webhook()`, leer `request.form.get("MessageSid")` y pasarlo a `encolar_mensaje` como `wamid` (reutilizamos la misma clave Redis `wamid:<id>`).
- La lógica de `ya_procesado_wamid` ya es atómica con SET NX, no necesita cambios.

---

### 9. Rate-limit 4s vs lock de pedido 10s
**Dónde:** `services/inbound_whatsapp.py:120`, `controllers/mensajes_registrados.py:32`, `controllers/pedido.py:44`

**Problema:** El `bloquear_usuario` de 4s puede dejar pasar el segundo mensaje mientras el primero aún tiene el lock de 10s de `pedido_lock:{numero}`. Además, `_iniciar_pedido_y_enviar_menu` y `procesar_pedido` comparten la misma clave de lock — intencional o no, no está documentado.

**Remedio:**
- Alinear duraciones: rate-limit ≥ duración del lock de pedido, o lock de pedido = TTL corto (1-2 s) y documentar que es best-effort.
- Añadir un comentario en ambos callers explicando que `pedido_lock:{numero}` protege a los dos flujos como una sola sección crítica.

---

### 10. `cancelar_pedidos_caducados` usa `FechaCreacion`, no última actividad
**Dónde:** `managers/pedidos/lifecycle_mixin.py:314-347`

**Problema:** El filtro es `FechaCreacion < corte`. Un usuario que pasó 55 minutos navegando y entró en `ENLACE2` se cancela 5 minutos después aunque esté activo en el menú web.

**Remedio:**
- Añadir columna `FechaActualizacion` al modelo `Pedido` con `onupdate=datetime.utcnow`.
- Cambiar el filtro a `Pedido.FechaActualizacion < corte`.
- Alternativa sin migración: hacer join con el `MAX(HistorialEstadoPedido.creado_en)` por pedido.

---

## 🟡 Logs faltantes — cosas que ocurren sin rastro

### 11. `actualizar_estado` devuelve `False` silencioso — callers lo ignoran
**Dónde:** `managers/pedidos/workflow_mixin.py:44-54` + callers en `mensajes_registrados.py:119,130`, `cart.py:98,131`

**Problema:** Si `_set_estado` rechaza la transición, `actualizar_estado` devuelve `False` sin lanzar excepción. Los callers envuelven en `try/except Exception` y **no comprueban el retorno** — al usuario se le dice que se canceló cuando no se canceló nada.

**Remedio:**
```python
ok = gestor_pedidos.actualizar_estado(id_pedido_activo, EstadoPedido.CANCELADO)
if not ok:
    logger.error("CANCELACION_RECHAZADA pedido=%s estado_actual=%s", id_pedido_activo, pedido_activo.Estado)
    _enviar_error_sistema(numero_cliente)
    return "error cancelando pedido", 200
```
Aplicar el patrón a todos los sitios que hacen `actualizar_estado` y hoy tiran el valor de retorno.

---

### 12. `cancelar_pedidos_caducados` no loguea por-pedido qué falló
**Dónde:** `managers/pedidos/lifecycle_mixin.py:336-342`

**Problema:** Si `_set_estado` devuelve False en el bulk, el loop continúa sin saber qué pedido concreto se saltó ni por qué. Solo imprime el total cancelado.

**Remedio:**
```python
for pedido in pedidos:
    if self._set_estado(pedido, EstadoPedido.CANCELADO, notas="caducado_automatico"):
        cancelados += 1
    else:
        logger.warning(
            "CADUCIDAD_NO_APLICADA pedido=%s estado=%s — transición inválida",
            pedido.PedidoID, pedido.Estado,
        )
```

---

## 🔵 Queries — rendimiento

### 13. N+1 en `obtener_seguimiento`
**Dónde:** `managers/pedidos/lifecycle_mixin.py:285-312`

**Problema:** Cada llamada hace la query del `Pedido`, luego accede a `pedido.reparto` (segunda query lazy) y `r.repartidor` (tercera query). Endpoint público de tracking = tráfico alto.

**Remedio:**
```python
from sqlalchemy.orm import joinedload
pedido = (
    self.session.query(Pedido)
    .options(joinedload(Pedido.reparto).joinedload(Reparto.repartidor))
    .filter_by(redisID=redis_id)
    .first()
)
```

---

### 14. `obtener_pedido_mas_reciente` sin índice compuesto
**Dónde:** `managers/pedidos/lifecycle_mixin.py:91-112`

**Problema:** Query más caliente del bot (se llama en cada mensaje WhatsApp). Filtra por `ClienteID`, descarta estados terminales, ordena por `FechaCreacion DESC` y toma el primero. Sin índice compuesto sobre `(ClienteID, FechaCreacion DESC)` hace sort en runtime.

**Remedio:**
- Añadir `Index('ix_pedido_cliente_fecha', 'ClienteID', 'FechaCreacion')` en `models.py`.
- Crear migración.

---

### 15. `cancelar_pedidos_caducados` hace full scan
**Dónde:** `managers/pedidos/lifecycle_mixin.py:329-335`

**Problema:** Filtro `Estado IN (...) AND FechaCreacion < corte`. Sin índice compuesto se degrada conforme crece la tabla.

**Remedio:** `Index('ix_pedido_estado_fecha', 'Estado', 'FechaCreacion')`.

---

## Prioridad sugerida

| # | Problema | Severidad | Esfuerzo |
|---|---|---|---|
| 1 | Cancelar en ENLACE/ENLACE2 | Alta — único dead-end real | Bajo |
| 2 | Positivas en `ESPERANDO_CONFIRMACION` | Alta — fricción de onboarding | Trivial |
| 3 | Monei: try/except en envío WA | Alta — el cliente no se entera del pago | Bajo |
| 4 | Monei: logs de eventos no-SUCCESS | Alta — ceguera operativa | Trivial |
| 11 | Callers ignoran retorno de `actualizar_estado` | Alta — falsos positivos al usuario | Bajo |
| 5 | Validar `amount` de Monei | Media | Trivial |
| 6 | Distinguir `Total is None` en `procesar_pago_confirmado` | Media | Trivial |
| 8 | Dedupe Twilio por `MessageSid` | Media | Bajo |
| 7 | Alertar `adquirir_lock` fail-open | Media | Trivial |
| 13 | N+1 en `obtener_seguimiento` | Media — endpoint caliente | Bajo |
| 10 | `cancelar_pedidos_caducados` usa `FechaCreacion` | Media | Medio (migración) |
| 14 | Índice `(ClienteID, FechaCreacion)` | Media | Bajo |
| 15 | Índice `(Estado, FechaCreacion)` | Baja | Bajo |
| 9 | Coherencia rate-limit / lock pedido | Baja | Trivial |
| 12 | Log por-pedido en caducados | Baja | Trivial |
