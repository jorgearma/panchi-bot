# Diseño: Corrección de hallazgos — `controllers/mensajes_registrados.py`

> Fecha: 2026-04-06  
> Auditoría base: `docs/auditoria/controllers/auditoria_controllers_mensajes_registrados.md`  
> Alcance: Hallazgos H1, H3, H4, H5, H6, H7. H8 (GDPR) queda pendiente para iteración separada. Tests en ticket separado.

---

## Archivos modificados

- `controllers/mensajes_registrados.py` — todos los cambios van aquí

---

## Hallazgos y cambios

### H7 — `logger.error` → `logger.warning` para usuario no encontrado (línea 50)

Usuario registrado no encontrado en DB es una inconsistencia de datos, no un error del sistema. `logger.error` genera falsas alarmas en sistemas de alertas agrupados por nivel.

**Cambio:** `logger.error(...)` → `logger.warning(...)` en línea 50.

---

### H5 — Log en fallthrough de `_enviar_error_generico` (línea 106)

El path final no tiene ningún log. En producción no hay forma de saber si hay usuarios llegando a esta línea ni con qué estado de pedido.

**Cambio:** Añadir `logger.warning("ESTADO_NO_CONTEMPLADO pedido=%s estado=%s usuario=%s mensaje=%r", ...)` inmediatamente antes de la llamada a `_enviar_error_generico`.

---

### H6 — Log en rama ENLACE caducado (líneas 80-84)

Sin log no es posible detectar si hay una tasa alta de enlaces caducados que indique un problema con el TTL de los tokens.

**Cambio:** Añadir `logger.info("ENLACE_CADUCADO pedido=%s usuario=%s", ...)` cuando `not enlace`, antes de llamar a `_enviar_enlace_caducado`.

---

### H1 — Guard para retorno `None` de `_enviar_estado_en_curso` (línea 104)

`_enviar_estado_en_curso` puede retornar `None` si recibe un estado inesperado (enum no normalizado, estado nuevo sin actualizar el notifier). Ese `None` se propagaba directamente como valor de retorno del controlador al blueprint, causando `TypeError` en Flask.

**Cambio:** Capturar el retorno en una variable, verificar `None`, y si es `None`: loguear con `logger.error`, enviar mensaje genérico al cliente, y devolver `("estado no contemplado", 200)`.

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

---

### H4 — try/except alrededor de `procesar_pedido` (línea 75)

`procesar_pedido` captura internamente algunos errores pero cualquier excepción no contemplada (`KeyError`, `AttributeError`, etc.) se propagaba al blueprint del webhook. Meta reintenta ante 500, creando un loop.

**Cambio:** Envolver la llamada en `try/except Exception`, loguear con `exc_info=True`, enviar error genérico al cliente, y devolver `("error procesando pedido", 200)`.

```python
try:
    mensaje = procesar_pedido(mensaje_cliente, numero_cliente, id_pedido_activo, usuario_datos)
except Exception as e:
    logger.error("ERROR_PROCESAR_PEDIDO usuario=%s error=%s", numero_cliente, e, exc_info=True)
    _enviar_error_generico(numero_cliente)
    return "error procesando pedido", 200
```

---

### H3 — Redis lock de idempotencia en `_iniciar_pedido_y_enviar_menu` (línea 66-68)

Sin guardia de concurrencia, si Meta reintenta un mensaje mientras el primer proceso aún trabaja y ambos ven `pedido_activo == None`, ambos llaman a `iniciar_pedido` y crean dos pedidos `PENDIENTE` para el mismo usuario.

**Enfoque elegido:** Lock estrecho dentro de `_iniciar_pedido_y_enviar_menu` (Opción B). Lock amplio descartado por bloquear paths sin la condición de carrera. Restricción DB descartada por requerir migración de esquema.

**Implementación:**
- Clave: `pedido_lock:<numero_cliente>` — misma convención que `bloqueo:<phone>` ya en uso.
- Operación: `SET NX EX 10` — atómica en Redis, TTL de 10 segundos.
- Si el lock ya existe: devolver `("mensaje enviado", 200)` sin crear pedido ni enviar mensaje. El primer proceso ya lo está manejando.
- Import: añadir `redismanager` al import desde `container`.

```python
from container import gestor_pedidos, gestor_usuarios, redismanager

@staticmethod
def _iniciar_pedido_y_enviar_menu(numero_cliente, usuario_datos):
    lock_key = f"pedido_lock:{numero_cliente}"
    lock_adquirido = redismanager.set(lock_key, "1", nx=True, ex=10)
    if not lock_adquirido:
        logger.info("LOCK_PEDIDO ya activo para %s — ignorando duplicado.", numero_cliente)
        return "mensaje enviado", 200

    id_usuario = usuario_datos["id"]
    # ... resto sin cambios
```

---

## Qué NO se toca

- `mensajes_registrados_notifier.py` — sin cambios.
- La estructura de `ManejadorMensajesRegistrados` como clase con métodos estáticos.
- El manejo de errores de DB en líneas 47-64 — correcto y completo.
- Tests — ticket separado.
- H8 (GDPR / números en logs) — iteración separada tras revisar el stack de logging.

---

## Orden de aplicación

1. H7 — cambio de nivel de log (1 palabra)
2. H6 — log en enlace caducado (1 línea)
3. H5 — log en fallthrough (3 líneas)
4. H1 — guard para `None` (5 líneas)
5. H4 — try/except en `procesar_pedido` (5 líneas)
6. H3 — Redis lock en `_iniciar_pedido_y_enviar_menu` (5 líneas + import)
