# Deuda técnica — flujo de pedidos y pagos

Fecha: 2026-04-11
Branch: redimiento-colaworker-webhook-meta-tilwgo

Auditoría del flujo WhatsApp → carrito → pago → notificación. Se listan los bugs detectados, con severidad, evidencia, plan de remediación y orden recomendado para evitar regresiones.

---

## Resumen de bugs

| ID  | Severidad | Área                     | Resumen                                                                |
|-----|-----------|--------------------------|------------------------------------------------------------------------|
| I   | Crítico   | Cron limpieza            | `cancelar_pedidos_caducados` no limpia `CONFIRMANDO_PAGO` → bloqueo permanente |
| A   | Alto      | Bot                      | Si falla cancelar pedido con enlace nulo, queda en `CONFIRMANDO_PAGO`  |
| C   | Alto      | Webhook Monei            | `customer_phone` viene del payload Monei, puede ser `None`             |
| B   | Medio     | Pago efectivo            | Falla envío WhatsApp tras confirmar → usuario sin notificación chat    |
| D   | Bajo      | API carrito              | Race condition en `confirmar_carrito` (sin lock por usuario)           |
| E   | Cosmético | API cart/payments        | `userId` ausente devuelve 403 en vez de 400                            |
| F   | Medio     | Webhook Monei            | Reintento de Monei con misma `referencia_externa` reenvía WhatsApp al cliente |

---

## I — `cancelar_pedidos_caducados` no limpia `CONFIRMANDO_PAGO` (CRÍTICO)

**Archivo:** `managers/pedidos/lifecycle_mixin.py:314-341`

**Problema:** El cron solo recoge pedidos en `ENLACE` / `ENLACE2`. Un pedido que llegó a `CONFIRMANDO_PAGO` con enlace nulo (Monei caducado) y cuya cancelación falla en el bot (ver bug A) **nunca** se limpia. El usuario queda permanentemente bloqueado: cada mensaje suyo recae en `mensajes_registrados.py:114-123` y vuelve a intentar cancelar fallidamente.

**Plan de remediación:**

1. Añadir `EstadoPedido.CONFIRMANDO_PAGO` a la lista `estados` en `lifecycle_mixin.py:322`.
2. Verificar que `_set_estado(CONFIRMANDO_PAGO → CANCELADO)` es una transición válida en `states.py`. Si no lo es, añadirla.
3. Test unitario: insertar pedido en `CONFIRMANDO_PAGO` con `FechaCreacion` >1h, llamar `cancelar_pedidos_caducados`, verificar que queda en `CANCELADO`.
4. Test de no regresión: pedidos en `PAGADO`, `EN_PREPARACION`, etc. **no** deben tocarse.

**Riesgo de regresión:** Bajo. Solo amplía un filtro `IN`. Único riesgo es cancelar un pedido recién entrado en `CONFIRMANDO_PAGO` que todavía no ha llegado al webhook Monei — pero el umbral es 1h, suficiente margen.

---

## A — Bot deja pedido en `CONFIRMANDO_PAGO` si falla cancelar (ALTO)

**Archivo:** `controllers/mensajes_registrados.py:114-123`

**Problema:** Cuando un usuario escribe estando en `CONFIRMANDO_PAGO` y `pedido.enlace` es `None`, el bot intenta cancelar el pedido. Si `actualizar_estado(CANCELADO)` lanza excepción, solo se logea (línea 120-121) y se sigue ejecutando `_enviar_enlace_pago_caducado`. Resultado: usuario recibe mensaje pero el pedido sigue en `CONFIRMANDO_PAGO` en BD.

Combinado con bug I, el usuario queda bloqueado para siempre.

**Plan de remediación:**

1. Cambiar el `try/except` para que en caso de fallo:
   - Logee `ERROR_CANCELAR_ENLACE_NULO`.
   - Llame a `_enviar_error_sistema(numero_cliente)`.
   - Devuelva `("error cancelando pedido", 200)`.
   - **No** envíe `_enviar_enlace_pago_caducado` (porque la cancelación no ocurrió).
2. Test unitario con mock que hace que `actualizar_estado` lance `SQLAlchemyError`. Verificar que se llama `_enviar_error_sistema` y que **no** se llama `_enviar_enlace_pago_caducado`.
3. Test camino feliz: cancelación exitosa sigue enviando `_enviar_enlace_pago_caducado`.

**Riesgo de regresión:** Bajo. Cambio aislado a una rama de error. Bug I debe arreglarse antes para que el usuario tenga salida vía cron.

---

## C — Webhook Monei usa `customer_phone` del payload (ALTO)

**Archivo:** `services/inbound_whatsapp.py:174-222`

**Problema:** En `procesar_pago_monei` (líneas 187-188) se lee `customer.phone` y `billingDetails.address.line1` del payload Monei. Estos campos son **opcionales** en Monei: si llegan `None`, se intenta `enviar_mensaje_whatsapp(mensaje, None)` → falla silenciosamente. El pago está procesado, el usuario no recibe confirmación.

**Plan de remediación (fix raíz):**

1. Tras validar `order_id`, cargar el pedido desde BD: `pedido = gestor_pedidos.obtener_pedido(order_id)`.
2. Cargar el usuario asociado: `usuario = gestor_usuarios.obtener_usuario_por_id(pedido.UsuarioID)`.
3. Derivar `customer_phone` y `customer_address` del usuario y del pedido (la dirección ya está en `pedido.direccion` o equivalente). El payload Monei queda solo como fuente de `nombre_usuario` si se quiere, pero idealmente también del usuario.
4. Si no se encuentra pedido o usuario, logear y devolver 200 (el pago ya fue procesado por `procesar_pago_confirmado`; no romper el reintento de Monei).
5. Test unitario: payload Monei con `customer.phone = None` → mensaje se envía al teléfono real del usuario.
6. Test unitario: pedido inexistente → no peta, devuelve 200.

**Riesgo de regresión:** Medio. Hay que verificar que `obtener_usuario_por_id` existe (si no, añadirlo en `gestor_usuarios`). Verificar que la dirección que se quiere mostrar en el WhatsApp es la del pedido (no la del perfil del usuario, porque pueden divergir).

---

## B — Pago efectivo: WhatsApp falla silenciosamente (MEDIO)

**Archivo:** `controllers/pago.py:203-212`

**Problema:** `iniciar_pago_efectivo` confirma el pedido en BD y luego intenta enviar `_enviar_confirmacion_efectivo`. Si esa llamada falla, solo se logea y se devuelve `True`. Mitigado porque el cliente está en el navegador y es redirigido a `/pago_confirmado` (sí ve confirmación visual), pero pierde el mensaje de WhatsApp con el resumen.

**Plan de remediación:**

Opción A (simple, recomendada): registrar el fallo en una cola de reintentos.
1. Si `_enviar_confirmacion_efectivo` falla, encolar un job RQ que reintente el envío con backoff.
2. Logear `CONFIRMACION_EFECTIVO_WA_REINTENTO_PROGRAMADO`.

Opción B (sin infra extra): aceptar el fallo silencioso pero hacer que el endpoint devuelva una bandera `whatsapp_enviado: false` que el frontend pueda mostrar como aviso ("hemos confirmado tu pedido pero no pudimos enviarte WhatsApp, contacta a la tienda si necesitas el resumen").

**Sugerido:** Opción A si la cola RQ ya está disponible (lo está, según `message_queue.py`).

**Riesgo de regresión:** Bajo. El cambio es aditivo.

---

## D — Race condition en `confirmar_carrito` (BAJO)

**Archivo:** `controllers/carrito.py:103-157`, `managers/pedidos/workflow_mixin.py:69-93`

**Problema:** No hay lock por usuario entre el check de estado (`pedido_activo.Estado == EstadoPedido.ENLACE`) y la escritura. Dos peticiones simultáneas con sesiones SQLAlchemy distintas pueden ambas leer `ENLACE`, ambas pasar `_set_estado(ENLACE→ENLACE2)` (transición válida), y la segunda commit sobrescribe `redisID`. Resultado: una entrada Redis huérfana, BD apunta a la otra. El frontend del usuario que envió primero quedaría con un `pedido_id` desincronizado.

**Plan de remediación:**

1. Envolver `confirmar_carrito` en un lock Redis por usuario, siguiendo el patrón de `_iniciar_pedido_y_enviar_menu`:
   ```
   lock_key = f"carrito_lock:{user_id}"
   if not redismanager.adquirir_lock(lock_key, ttl=10):
       return False, "Procesando otra petición, espera unos segundos"
   try:
       # cuerpo actual
   finally:
       redismanager.liberar_lock(lock_key)  # si existe; si no, dejar que expire por TTL
   ```
2. Test concurrente con `threading` o `asyncio` que dispare dos llamadas simultáneas y verifique que solo una entra al cuerpo.
3. Alternativa más robusta (no excluyente): añadir `SELECT ... FOR UPDATE` en `fijar_carrito_confirmado` con `with_for_update()`, para que la BD sea la guardiana del lock. Esto cubre también peticiones desde instancias distintas del worker si el día de mañana se escala horizontalmente.

**Riesgo de regresión:** Bajo. El lock se libera por TTL aunque haya excepción.

---

## E — `userId`/`userID` ausente devuelve 403 (COSMÉTICO)

**Archivos:**
- `blueprints/api/cart.py:44-47`
- `blueprints/api/payments.py:27-30, 69-72`

**Problema:** `post_user_id = data.get("userId")` puede ser `None`. Luego `str(None) != str(token_user_id)` siempre → devuelve 403 "No autorizado" cuando lo correcto sería 400 "Falta userId".

**Plan de remediación:**

1. Antes del check de mismatch, validar que `post_user_id` no es `None` y devolver 400 si lo es.
2. Test: petición sin `userId` → 400, no 403.

**Riesgo de regresión:** Nulo.

---

## F — Reintentos de Monei reenvían WhatsApp duplicado (MEDIO)

**Archivo:** `services/inbound_whatsapp.py:174-222`, `managers/pedidos/workflow_mixin.py:182-191`

**Problema:** `procesar_pago_confirmado` es idempotente: si Monei reintenta el webhook con la misma `referencia_externa`, detecta el `Pago` ya existente y devuelve `True` sin mutar nada. Pero `procesar_pago_monei` no distingue ese caso del pago fresh y vuelve a llamar `enviar_mensaje_whatsapp` cada vez. Resultado: el cliente recibe N notificaciones idénticas si Monei reintenta el webhook (cosa que hace por diseño ante 5xx, timeouts, etc.).

**Plan de remediación:**

1. Cambiar la firma de `procesar_pago_confirmado` para devolver `(ok: bool, ya_existia: bool)` o un enum (`PROCESADO`, `YA_PROCESADO`, `RECHAZADO`).
2. En `procesar_pago_monei`, solo enviar el WhatsApp cuando `ya_existia=False`.
3. Test: dos llamadas consecutivas con misma `referencia_externa` → solo un envío de WhatsApp.
4. Test de no regresión: pago fresh sigue notificando.

**Riesgo de regresión:** Medio. Cambiar la firma de `procesar_pago_confirmado` afecta a otros consumidores — buscar usos antes. Si hay muchos, alternativa: dejar la firma intacta y comprobar `Pago` por `referencia_externa` desde el webhook antes de notificar (más feo pero aislado).

---

## Orden de implementación recomendado

El orden minimiza el riesgo de regresiones y resuelve primero lo que desbloquea usuarios reales.

### Fase 1 — Desbloqueo de usuarios atascados (urgente)

1. **Bug I** — Añadir `CONFIRMANDO_PAGO` al cron de limpieza.
   - Sin esto, los usuarios atrapados siguen atrapados aunque arregles A.
2. **Bug A** — Manejar correctamente el fallo de cancelación en el bot.
   - Combinado con I, garantiza que ningún pedido queda en limbo permanente.

**Validación de fase 1:** ejecutar `cancelar_pedidos_caducados` en staging contra una BD con un pedido en `CONFIRMANDO_PAGO` antiguo y verificar que se cancela. Probar el flujo del bot con `actualizar_estado` mockeado para fallar.

### Fase 2 — Notificaciones fiables

3. **Bug C** — Resolver teléfono y dirección desde BD en webhook Monei.
   - Crítico para que ningún pago confirmado quede sin notificar al cliente.
4. **Bug B** — Reintento RQ para confirmación de pago efectivo.
   - Mejora la fiabilidad pero no es bloqueante porque el cliente ve la confirmación web.

**Validación de fase 2:** test de webhook Monei con `customer.phone = None`. Test de `iniciar_pago_efectivo` con mock que hace fallar el envío y verifica encolado del reintento.

### Fase 3 — Hardening

5. **Bug D** — Lock Redis por usuario en `confirmar_carrito`.
   - Bajo riesgo en producción actual pero conveniente antes de cualquier escalado.
6. **Bug E** — Validar `userId` y devolver 400.
   - Limpieza cosmética; agruparla con D en un solo PR.

**Validación de fase 3:** test concurrente para D, test de petición sin `userId` para E.

---

## Estrategia anti-regresión

- **Un PR por bug**, excepto Fase 3 (D y E pueden ir juntos). PRs pequeños son más fáciles de revisar y revertir.
- **Tests obligatorios** antes de mergear cada PR. Mínimo: 1 test del camino feliz + 1 test del fallo concreto que se está arreglando.
- **Revisar el log de transiciones** (`historial_estados_pedido`) en staging tras cada despliegue para confirmar que no aparecen transiciones nuevas inesperadas.
- **No tocar `_set_estado` ni `transicion_valida_pedido`** salvo en el bug I (y solo si la transición `CONFIRMANDO_PAGO → CANCELADO` no existe ya). Cualquier cambio en la máquina de estados debe ir acompañado de tests de todas las transiciones afectadas.
- **No introducir features nuevas** mientras se trabaja en estos bugs. Mantener el alcance estricto.
