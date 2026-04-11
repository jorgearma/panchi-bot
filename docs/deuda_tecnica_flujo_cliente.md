# Deuda tecnica: Flujo de cliente (registro -> pedido -> pago)

Fecha: 2026-04-10
Estado: Pendiente de resolucion

---

## BUG 1 -- CRITICO: "si" con tilde se trata como "no" en confirmacion de direccion

**Archivos:** `controllers/registro.py:44`, `controllers/registro.py:183`

El filtro en linea 183 permite "si", "si" (con tilde) y "no":
```python
if mensaje_cliente.lower() not in {"si", "si", "no"}:
```

Pero `_confirmar_direccion` en linea 44 solo acepta "si" sin tilde:
```python
if mensaje_cliente.lower() != 'si':
    return False
```

**Resultado:** Un usuario que escribe "si" (con tilde, lo mas natural en espanol) pasa el filtro pero `_confirmar_direccion` devuelve `False`. El sistema lo manda de vuelta a ESPERANDO_DIRECCION como si hubiera dicho "no". El usuario no entiende por que le piden la direccion otra vez.

**Impacto:** Confusion del usuario; no bloquea pero degrada la experiencia.

---

## BUG 2 -- CRITICO (DEADLOCK): Token de menu caduca y usuario atrapado en ENLACE

**Archivos:** `services/token_service.py:29`, `controllers/mensajes_registrados.py:103-110`

El token de Redis que alimenta el enlace del menu caduca en 24h (`ex=86400`). Pero la URL se guarda en `pedido.enlace` en la BD y nunca caduca. Despues de 24h:

1. Usuario hace clic en el enlace -> `resolver_sesion_menu` -> Redis devuelve `None` -> "Enlace caducado"
2. Usuario escribe en WhatsApp -> estado es ENLACE -> handler reenvia el mismo enlace muerto (`pedido.enlace`)
3. `_enviar_enlace_caducado` le dice "Escribe 1 para generar un nuevo enlace" -> no existe logica que regenere un enlace desde ENLACE. Escribir "1" reenvia el mismo enlace muerto.

No hay transicion ENLACE -> PENDIENTE implementada en ningun controller aunque `TRANSICIONES_PEDIDO` la permite.

**Impacto:** El usuario queda bloqueado permanentemente. Solo intervencion manual desde dashboard o BD lo desbloquea.

---

## BUG 3 -- CRITICO (DEADLOCK): Cache del carrito caduca y usuario atrapado en ENLACE2

**Archivos:** `controllers/carrito.py:153` (TTL 3600s), `blueprints/menu/sesion.py:17-23`

El carrito se guarda en Redis con TTL de 1 hora (`ex=3600`). Despues de 1h:

1. `/confirmacion_pago?pedido_id=...` -> `leer_sesion_confirmacion` devuelve `None` -> 404
2. Usuario hace clic en el enlace del menu -> `resolver_sesion_menu` -> estado ENLACE2 -> redirige a `/confirmacion_pago?pedido_id=...` -> 404 otra vez
3. `volver_al_menu` (boton "atras") requiere la web funcionando -> no se puede usar
4. WhatsApp -> handler reenvia el enlace -> mismo ciclo muerto

**Impacto:** El usuario no puede avanzar ni retroceder. Deadlock permanente.

---

## BUG 4 -- ALTO: Pago abandonado en Monei y usuario atrapado en CONFIRMANDO_PAGO

**Archivo:** `controllers/mensajes_registrados.py:112-119`

Si el usuario abandona el pago en Monei (cierra la ventana, falla la tarjeta), queda en CONFIRMANDO_PAGO. Las unicas transiciones son: PAGADO (webhook Monei) o CANCELADO (dashboard).

- El usuario escribe en WhatsApp -> recibe el enlace de Monei otra vez
- Si el enlace de Monei ha expirado -> Monei muestra error -> el usuario no puede pagar
- No hay mecanismo de autoservicio para cancelar o reiniciar

**Impacto:** Bloqueado hasta intervencion manual del operador.

---

## BUG 5 -- MEDIO: Fallo de Redis en confirmar_carrito y usuario bloqueado silenciosamente

**Archivo:** `controllers/carrito.py:155-159`

Si `cache.set()` falla DESPUES de que la BD haya commiteado la transicion ENLACE -> ENLACE2, el pedido esta en ENLACE2 en BD pero no hay datos del carrito en Redis. `/confirmacion_pago` devuelve 404.

El propio comentario del codigo reconoce el deadlock:
```
"CARRITO_REDIS_FALLIDO pedido=%s -- cliente bloqueado en /confirmacion_pago hasta intervencion"
```

**Impacto:** Deadlock hasta intervencion manual.

---

## BUG 6 -- MEDIO: Recuperacion parcial de registro sin respuesta al usuario

**Archivo:** `controllers/registro.py:92-94`

Si durante la recuperacion de un registro parcial (usuario existe en BD pero sin pedido), `iniciar_pedido` falla:

```python
except Exception as e:
    logger.error("RECUPERACION_FALLIDA usuario=%s error=%s", ...)
    return "Error en registro", 200
```

Se devuelve a Flask sin enviar ningun mensaje WhatsApp al usuario. El usuario envio "si" y recibe silencio total.

**Impacto:** No bloquea (puede reintentar), pero experiencia confusa.

---

## BUG 7 -- BAJO: Mensaje enganoso de enlace caducado en CONFIRMANDO_PAGO

**Archivo:** `controllers/mensajes_registrados.py:115-116`

Si `enlace_pago` es `None` en estado CONFIRMANDO_PAGO, se llama `_enviar_enlace_caducado` que dice "Escribe 1 para generar un nuevo enlace". Desde CONFIRMANDO_PAGO no se puede generar nada nuevo. El mensaje es enganoso.

**Impacto:** Confusion; no bloquea pero genera expectativa falsa.

---

## Tabla resumen

| # | Severidad | Bug | Deadlock? |
|---|-----------|-----|-----------|
| 2 | CRITICO | Token caduca en ENLACE | Si, permanente |
| 3 | CRITICO | Cache caduca en ENLACE2 | Si, permanente |
| 1 | CRITICO | "si" con tilde = retroceso silencioso | No |
| 4 | ALTO | Pago abandonado sin salida | Si, hasta intervencion |
| 5 | MEDIO | Redis fallo post-commit | Si, hasta intervencion |
| 6 | MEDIO | Registro parcial sin respuesta | No |
| 7 | BAJO | Mensaje enganoso en CONFIRMANDO_PAGO | No |

---

## Mitigacion propuesta

### BUG 1 -- "si" con tilde

Cambiar la condicion en `_confirmar_direccion` para aceptar ambas formas:

```python
if mensaje_cliente.lower() not in ('si', 'si'):  # con y sin tilde
    return False
```

Archivos a tocar: `controllers/registro.py`
Riesgo: Bajo. Solo amplia la condicion de aceptacion.

### BUG 2 -- Token caduca en ENLACE

**Opcion A (recomendada):** En `mensajes_registrados.py`, cuando el estado es ENLACE y el enlace ya no es valido (el token de Redis caduco), ejecutar rollback a PENDIENTE y regenerar enlace automaticamente.

Flujo propuesto:
1. Detectar que el token embebido en `pedido.enlace` ya no existe en Redis
2. Ejecutar `actualizar_estado(pedido_id, EstadoPedido.PENDIENTE)`
3. Tratar el mensaje como si el usuario estuviera en PENDIENTE (entra en `procesar_pedido`)

**Opcion B:** Un job periodico (cron o RQ scheduler) que limpie pedidos estancados en ENLACE mas de X horas haciendo rollback a PENDIENTE.

Archivos a tocar: `controllers/mensajes_registrados.py`, posiblemente `services/menu_session.py`
Archivos a revisar: `managers/pedidos/workflow_mixin.py` (transicion ENLACE -> PENDIENTE ya existe en `TRANSICIONES_PEDIDO`)

### BUG 3 -- Cache caduca en ENLACE2

**Opcion A (recomendada):** Misma estrategia que BUG 2. Detectar que `redisID` del pedido ya no existe en Redis y hacer rollback ENLACE2 -> ENLACE.

Flujo propuesto:
1. En `mensajes_registrados.py`, cuando estado es ENLACE2, verificar que `cache.get(pedido.redisID)` existe
2. Si no existe, ejecutar `actualizar_estado(pedido_id, EstadoPedido.ENLACE)`
3. Continuar como si estuviera en ENLACE (reenviar enlace del menu si el token sigue vivo, o encadenar con la mitigacion del BUG 2)

**Opcion complementaria:** Subir el TTL del carrito en Redis de 3600s a algo mas razonable (ej. 86400s como el token del menu).

Archivos a tocar: `controllers/mensajes_registrados.py`, `controllers/carrito.py` (TTL)
Archivos a revisar: `managers/pedidos/workflow_mixin.py`, `services/menu_session.py`, `blueprints/menu/sesion.py`

### BUG 4 -- Pago abandonado en CONFIRMANDO_PAGO

**Opcion A:** Permitir al usuario cancelar desde WhatsApp con un comando (ej. "cancelar"). Detectar la palabra en `mensajes_registrados.py` cuando el estado es CONFIRMANDO_PAGO y ejecutar CONFIRMANDO_PAGO -> CANCELADO -> crear nuevo pedido.

**Opcion B:** TTL de expiracion. Si el pedido lleva mas de X horas en CONFIRMANDO_PAGO sin webhook de Monei, un job lo mueve a CANCELADO y notifica al usuario.

Archivos a tocar: `controllers/mensajes_registrados.py`
Archivos a revisar: `managers/pedidos/workflow_mixin.py`, `states.py` (transiciones)

### BUG 5 -- Redis fallo post-commit en confirmar_carrito

Invertir el orden: escribir en Redis primero y commitear BD despues. Si Redis falla, no se commitea la BD y el estado no cambia. Si la BD falla despues de Redis, el dato de Redis caduca solo (TTL) y el usuario sigue en ENLACE con la posibilidad de reintentar.

Archivos a tocar: `controllers/carrito.py`
Archivos a revisar: `managers/pedidos/workflow_mixin.py`

### BUG 6 -- Registro parcial sin respuesta

Anadir un `enviar_mensaje_whatsapp` antes del return para que el usuario sepa que hubo un error y puede reintentar.

Archivos a tocar: `controllers/registro.py`
Riesgo: Bajo.

### BUG 7 -- Mensaje enganoso

Crear un mensaje especifico para cuando el enlace de pago no esta disponible, diferente al de "enlace caducado". Ej: "Tu pago esta pendiente. Si tienes problemas, contacta con soporte al {STORE_PHONE}."

Archivos a tocar: `controllers/mensajes_registrados.py`, `controllers/mensajes_registrados_notifier.py`
Riesgo: Bajo.

---

## Archivos a revisar antes de hacer cambios (prevencion de regresiones)

### Archivos que se van a modificar

| Archivo | Bugs que resuelve |
|---------|-------------------|
| `controllers/registro.py` | 1, 6 |
| `controllers/mensajes_registrados.py` | 2, 3, 4, 7 |
| `controllers/mensajes_registrados_notifier.py` | 7 |
| `controllers/carrito.py` | 3 (TTL), 5 |
| `services/menu_session.py` | 2, 3 |

### Archivos que hay que leer y entender antes de tocar nada

| Archivo | Por que |
|---------|---------|
| `states.py` | Mapa maestro de transiciones. Verificar que las nuevas transiciones (rollbacks) estan permitidas |
| `managers/pedidos/workflow_mixin.py` | `_set_estado` y `actualizar_estado` son los que validan y ejecutan transiciones. Asegurar que rollbacks funcionan con historial |
| `managers/pedidos/lifecycle_mixin.py` | `obtener_pedido_mas_reciente`, `iniciar_enlace`. Entender que devuelve y que excluye |
| `services/token_service.py` | Entender como se genera y almacena el token para poder regenerarlo |
| `controllers/pedido.py` | `procesar_pedido` es el handler de PENDIENTE. Si hacemos rollback a PENDIENTE, el siguiente mensaje entrara aqui |
| `services/inbound_whatsapp.py` | `enrutar_mensaje` — punto de entrada. Asegurar que el rate-limit no interfiere con los rollbacks |
| `blueprints/menu/navegacion.py` | `resolver_sesion_menu` — decide que pantalla mostrar segun el estado |
| `blueprints/menu/sesion.py` | Paginas de confirmacion y pago confirmado — afectadas por cambios en TTL |
| `blueprints/api/cart.py` | `volver_al_menu` y `cambiar_estado_a_enlace` — mecanismos de rollback existentes que no deben romperse |
| `blueprints/api/payments.py` | `agregar_pedido` y `agregar_pedido_efectivo` — flujo de pago que depende de ENLACE2 |

### Tests existentes que deben pasar

```bash
pytest tests/ -v --tb=short
```

Tests especificos a vigilar:
- `tests/test_webhook.py` — flujo de mensajes entrantes
- `tests/test_registro.py` — maquina de estados de registro (si existe)
- `tests/test_carrito.py` — confirmacion de carrito (si existe)
- Cualquier test que toque `mensajes_registrados` o `procesar_pedido`

### Orden recomendado de implementacion

1. **BUG 1** (tilde) — cambio minimo, sin riesgo, resolucion inmediata
2. **BUG 6** (mensaje faltante) — cambio minimo, sin riesgo
3. **BUG 7** (mensaje enganoso) — cambio minimo, sin riesgo
4. **BUG 2** (deadlock ENLACE) — cambio medio, requiere rollback + regeneracion
5. **BUG 3** (deadlock ENLACE2) — depende de que BUG 2 este resuelto primero
6. **BUG 5** (Redis post-commit) — cambio de orden de operaciones, requiere testing cuidadoso
7. **BUG 4** (CONFIRMANDO_PAGO) — requiere decision de producto (comando "cancelar" vs TTL automatico)
