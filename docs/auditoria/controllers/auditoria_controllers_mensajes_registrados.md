# Auditoría de `controllers/mensajes_registrados.py`

> Auditoría técnica estricta. Fecha: 2026-04-06.
> Archivos analizados: `controllers/mensajes_registrados.py`, `controllers/mensajes_registrados_notifier.py`, `controllers/pedido.py`, `states.py`, `managers/pedidos/lifecycle_mixin.py`.

---

## 1. Rol del archivo

**Responsabilidad principal:** Orquestador del flujo de mensajes de usuarios ya registrados. Determina el estado del pedido activo y enruta la respuesta al handler correcto.

**Qué debería hacer:** Leer estado del usuario y pedido desde DB, hacer avanzar la máquina de estados, delegar notificaciones al notifier y procesamiento de opciones a `pedido.py`.

**Qué no debería hacer:** Contener lógica de presentación de mensajes, hacer queries sin manejar todos los estados posibles del enum, devolver valores de tipo inconsistente.

**Dependencias clave:**
- `container.gestor_usuarios` / `gestor_pedidos` — acceso a DB
- `controllers/pedido.py` — procesado de opciones del menú y carrito
- `controllers/mensajes_registrados_notifier.py` — envío de mensajes WhatsApp
- `states.EstadoPedido` — enum de estados del pedido

**Nivel de criticidad: Crítico** — Es el punto de entrada para cada mensaje de cualquier cliente registrado. Un estado no contemplado o una excepción no capturada aquí afecta a todos los usuarios activos.

---

## 2. Lo que hace bien

- Los accesos a DB están correctamente envueltos en `try/except (SQLAlchemyError, RetryError)` con log descriptivo (líneas 47-64). No depende de que `tenacity` lo reintente silenciosamente.
- La separación entre `ManejadorMensajesRegistrados` y `mensajes_registrados_notifier` es limpia: el controlador no construye strings de mensajes.
- `_iniciar_pedido_y_enviar_menu` tiene su propio bloque de error diferenciado del flujo principal (líneas 33-41).
- El log de `logger.info` en línea 67 y `logger.info` + `logger.debug` en líneas 100-103 dan trazabilidad del estado actual del pedido en producción.
- `@staticmethod` en ambos métodos indica que no hay estado de instancia implícito — el diseño es explícito sobre sus dependencias.

---

## 3. Hallazgos

### Hallazgo 1

**Tipo:** consistencia / errores
**Severidad: Crítica**

**Problema:** `_enviar_estado_en_curso` en el notifier puede retornar `None` (línea 124 del notifier), y ese `None` se propaga directamente como valor de retorno de `manejar_mensajes_registrados` (línea 104). El blueprint que llama a este método espera una tupla `(str, int)`. Si recibe `None`, Flask intentará construir una `Response` con `None` y lanzará un `TypeError` o devolverá una respuesta vacía con status 200, dependiendo de la versión de Flask.

**Evidencia:**
```python
# mensajes_registrados_notifier.py:119-124
else:
    logger.warning(
        "_enviar_estado_en_curso llamado con estado inesperado: %s (pedido %s)",
        estado, pedido_activo.PedidoID,
    )
    return None  # ← se propaga

# mensajes_registrados.py:104
return _enviar_estado_en_curso(pedido_activo, numero_cliente)
```

**Impacto real:** Si la DB devuelve el estado del pedido como string no normalizado (ej: `"Pagado"` en lugar de `"pagado"`) o si se añade un nuevo estado al enum sin actualizar el notifier, la función devuelve `None` al blueprint y el webhook falla con un error 500. Meta reintenta, el ciclo se repite.

**Recomendación mínima concreta:** No propagar el retorno del notifier ciegamente. Añadir guardia en el caller:
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

### Hallazgo 2 ~~(invalidado)~~

> **Nota de corrección:** Este hallazgo era incorrecto. Se asumió que `obtener_pedido_mas_reciente` devolvía el pedido más reciente sin importar su estado. Verificado en `managers/pedidos/lifecycle_mixin.py:97-101`: la query **excluye explícitamente** los estados terminales (`ENTREGADO`, `CANCELADO`, `REEMBOLSADO`) usando `notin_(estados_excluidos)`. El comportamiento real es correcto: cuando el pedido del usuario está entregado, la query devuelve `None` y el controlador inicia un pedido nuevo. No hay bug.

---

### Hallazgo 3

**Tipo:** consistencia / rendimiento
**Severidad: Alta**

**Problema:** No hay guardia de idempotencia al crear un pedido nuevo. Si dos mensajes llegan concurrentemente (Meta puede reintentar) con `pedido_activo == None`, ambos pasan por las líneas 66-68 y llaman a `_iniciar_pedido_y_enviar_menu`, que llama a `gestor_pedidos.iniciar_pedido`. Resultado: dos pedidos activos para el mismo usuario.

**Evidencia:**
```python
# líneas 66-68 — sin lock ni verificación de concurrencia
if not pedido_activo:
    logger.info("Usuario %s sin pedido activo — iniciando nuevo pedido.", numero_cliente)
    return ManejadorMensajesRegistrados._iniciar_pedido_y_enviar_menu(numero_cliente, usuario_datos)
```

**Impacto real:** El usuario tiene dos pedidos en estado `PENDIENTE`. Cuando avanza con uno, el otro queda huérfano en DB indefinidamente. Si no hay índice único en `(id_usuario, Estado='Pendiente')`, la tabla acumula pedidos basura con el tiempo.

**Recomendación mínima concreta:** Verificar de nuevo dentro de `_iniciar_pedido_y_enviar_menu` con un `SELECT FOR UPDATE` o equivalente antes del insert, o usar un lock de Redis por usuario con TTL corto (`bloqueo:<numero_cliente>` ya existe en el proyecto para anti-spam — el mismo patrón aplica aquí).

---

### Hallazgo 4

**Tipo:** errores
**Severidad: Media**

**Problema:** `procesar_pedido` (línea 75) se llama sin ningún `try/except`. La función internamente captura `ValidationError` y algunos `SQLAlchemyError`, pero cualquier excepción no contemplada (ej: `KeyError` en el menú, `AttributeError` en `usuario_datos`) se propaga sin capturar hacia el caller, que tampoco la captura, y finalmente llega al blueprint del webhook.

**Evidencia:**
```python
# línea 75 — sin protección
mensaje = procesar_pedido(mensaje_cliente, numero_cliente, id_pedido_actual, usuario_datos)
```

**Impacto real:** Un error inesperado en el procesado de un mensaje causa un 500 en el webhook. Meta reintenta. El usuario no recibe respuesta.

**Recomendación mínima concreta:**
```python
try:
    mensaje = procesar_pedido(mensaje_cliente, numero_cliente, id_pedido_activo, usuario_datos)
except Exception as e:
    logger.error("ERROR_PROCESAR_PEDIDO usuario=%s error=%s", numero_cliente, e, exc_info=True)
    _enviar_error_generico(numero_cliente)
    return "error procesando pedido", 200
```

---

### Hallazgo 5

**Tipo:** observabilidad
**Severidad: Media**

**Problema:** El fallthrough final (línea 106) envía `_enviar_error_generico` sin ningún log previo. Si un usuario llega a esta línea, no hay trazabilidad de por qué: qué estado tenía el pedido, cuál era el mensaje del usuario, nada.

**Evidencia:**
```python
# línea 106 — sin log
_enviar_error_generico(numero_cliente)
return " mensaje enviado", 200
```

**Impacto real:** En producción, si el Hallazgo 2 no se corrige, hay usuarios llegando a esta línea silenciosamente. No hay forma de detectarlo en logs.

**Recomendación mínima concreta:**
```python
logger.warning(
    "ESTADO_NO_CONTEMPLADO pedido=%s estado=%s usuario=%s mensaje=%r",
    id_pedido_activo, estado_del_pedido, numero_cliente, mensaje_cliente,
)
_enviar_error_generico(numero_cliente)
```

---

### Hallazgo 6

**Tipo:** observabilidad
**Severidad: Baja**

**Problema:** Los branches `ENLACE`, `ENLACE2` y `CONFIRMANDO_PAGO` (líneas 80-90) no tienen ningún log. No es posible saber en producción con qué frecuencia los usuarios piden que se les reenvíe el enlace.

**Evidencia:**
```python
# líneas 80-90 — sin logger
if estado_del_pedido == EstadoPedido.ENLACE or estado_del_pedido == EstadoPedido.ENLACE2:
    enlace = pedido_activo.enlace
    if not enlace:
        _enviar_enlace_caducado(numero_cliente)
        return " mensaje enviado", 200
    _enviar_enlace_pedido(enlace, numero_cliente)
    return " mensaje enviado", 200
```

**Impacto real:** Imposible detectar si hay una tasa alta de "enlace caducado" que indique un problema con el TTL de los tokens.

**Recomendación mínima concreta:**
```python
if not enlace:
    logger.info("ENLACE_CADUCADO pedido=%s usuario=%s", id_pedido_activo, numero_cliente)
    _enviar_enlace_caducado(numero_cliente)
```

---

### Hallazgo 7

**Tipo:** errores
**Severidad: Baja**

**Problema:** `logger.error` en línea 50 para "usuario no encontrado". Un usuario registrado que no existe en DB es una inconsistencia de datos, no un error del sistema. Usar `logger.error` provoca falsas alarmas en sistemas de alertas basados en nivel de log.

**Evidencia:**
```python
# línea 50
logger.error("Error: No se encontraron datos para el usuario %s.", numero_cliente)
```

**Impacto real:** Bajo individualmente, pero ensucia las alertas de error en producción si el sistema de monitorización agrupa por nivel.

**Recomendación mínima concreta:** Cambiar a `logger.warning`.

---

### Hallazgo 8 — Posible riesgo no confirmado

**Tipo:** seguridad / observabilidad
**Severidad: Baja (no confirmada)**

**Problema:** `numero_cliente` (número de teléfono del cliente) se registra en logs en múltiples líneas (50, 67, 100, 102). No se puede confirmar sin revisar la configuración del stack de logging si estos logs van a sistemas externos (Sentry, ELK, CloudWatch). Si van, los números de teléfono son datos personales bajo GDPR.

**Recomendación:** Verificar la configuración de `SENTRY_DSN` y el handler de logging. Si los logs van a servicios externos, considerar truncar o anonimizar el número en el log (ej: `numero_cliente[-4:]`).

---

## 4. Riesgos principales si no se toca

| Riesgo | Escenario concreto |
|--------|-------------------|
| Crash del blueprint con `TypeError` | DB devuelve estado de pedido como string no normalizado → `_enviar_estado_en_curso` retorna `None` → Flask explota |
| Pedidos duplicados | Meta reintenta mensaje cuando el primer proceso tarda → dos llamadas a `iniciar_pedido` → dos pedidos `PENDIENTE` para el mismo usuario |
| Error 500 silencioso | Excepción no contemplada en `procesar_pedido` → se propaga al blueprint → Meta reintenta → loop |

---

## 5. Refactor mínimo recomendado

### Qué tocar primero (en orden de impacto)

1. **Guardar el retorno de `_enviar_estado_en_curso` y verificar `None`** (Hallazgo 1). Cuatro líneas. Evita crash silencioso en producción.

2. **Wrappear `procesar_pedido` en try/except** (Hallazgo 4). Seis líneas. Evita que errores inesperados lleguen al webhook.

4. **Añadir log al fallthrough de `_enviar_error_generico`** (Hallazgo 5). Una línea. Da visibilidad a un path completamente ciego.

5. **Cambiar `logger.error` a `logger.warning`** en usuario no encontrado (Hallazgo 7). Un cambio de palabra. Limpia las alertas.

### Qué NO tocar todavía

- La estructura de `ManejadorMensajesRegistrados` como clase con métodos estáticos — funciona.
- La separación notifier/controller — está bien.
- El manejo de errores de DB en líneas 47-64 — es correcto y completo.
- `pedido.py` — tiene problemas propios (mezcla de responsabilidades entre `procesar_pedido` y `confirmar_carrito`) pero es un audit separado.

---

## 6. Tests que deberían existir

- `test_estado_terminal_inicia_nuevo_pedido`: pedido con estado `ENTREGADO` → debe iniciar un nuevo pedido, no devolver error genérico.
- `test_estado_en_curso_none_no_crashea`: `_enviar_estado_en_curso` devuelve `None` → el controlador debe responder con 200 y error genérico, no propagar `None`.
- `test_procesar_pedido_excepcion_no_se_propaga`: `procesar_pedido` lanza `RuntimeError` → el controlador devuelve 200 con mensaje de error.
- `test_sin_pedido_activo_inicia_pedido`: `obtener_pedido_mas_reciente` devuelve `None` → se llama a `iniciar_pedido` una sola vez.
- `test_enlace_caducado_cuando_enlace_es_none`: pedido en estado `ENLACE` sin URL → se envía mensaje de enlace caducado.
- `test_usuario_no_encontrado_devuelve_404`: `obtener_usuario_completo` devuelve `None` → status 404, sin crash.
- `test_usuario_db_error_devuelve_500`: `obtener_usuario_completo` lanza `SQLAlchemyError` → status 500, mensaje de error al usuario.

---

## 7. Veredicto final

**Estado general del archivo:** Bien estructurado y más limpio que `registro.py`. Hallazgo 2 invalidado tras verificar la query en el manager — la lógica de estados terminales es correcta. Quedan dos bugs reales activos (Hallazgos 1 y 3) y mejoras de observabilidad y robustez (4, 5, 6, 7).

**¿Bloquea crecimiento?** No directamente. Pero añadir nuevos estados al enum `EstadoPedido` sin actualizar el notifier es fácil de olvidar y provoca el crash del Hallazgo 1.

**¿Bloquea testeo?** Parcialmente. El import de `gestor_pedidos` y `gestor_usuarios` desde `container` a nivel de módulo requiere parchear `container` en los tests — patrón funcional pero no idiomático.

**¿Tiene riesgo operativo real?** Sí. El Hallazgo 1 (crash si el estado devuelto por DB no coincide exactamente con el enum) y el Hallazgo 3 (pedidos duplicados ante reintentos) son los riesgos operativos reales restantes.
