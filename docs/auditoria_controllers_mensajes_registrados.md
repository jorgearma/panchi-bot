# Auditoría de `controllers/mensajes_registrados.py`

> Auditoría técnica estricta. Fecha: 2026-04-07.
> Archivos analizados: `controllers/mensajes_registrados.py`, `controllers/mensajes_registrados_notifier.py`, `controllers/pedido.py`, `states.py`, `managers/pedidos/lifecycle_mixin.py` (métodos `iniciar_pedido`, `obtener_pedido_mas_reciente`), `managers/gestor_redis.py` (método `adquirir_lock`), `utils/menu_opciones.py`.

---

## 1. Rol del archivo

**Responsabilidad principal:** Orquestar la respuesta del bot para usuarios ya registrados, bifurcando según el estado del pedido activo.

**Qué debería hacer:** Leer estado de pedido → decidir qué rama ejecutar → delegar a notifier o a `procesar_pedido`. Nada más.

**Qué no debería hacer:** Acceder directamente a DB o Redis (lo hace a través de managers), construir mensajes WhatsApp (delegado al notifier). Actualmente respeta estos límites.

**Dependencias clave:** `gestor_pedidos`, `gestor_usuarios`, `redismanager` (singletons de container), `procesar_pedido`, `mensajes_registrados_notifier`, `states`.

**Nivel de criticidad:** Alto — es el punto de entrada de todo mensaje de un cliente registrado. Un fallo aquí afecta a todos los pedidos en curso.

---

## 2. Lo que hace bien

- Separación limpia entre orquestación (este archivo) y mensajes WhatsApp (notifier). Ninguna llamada directa a `enviar_mensaje_whatsapp`.
- Manejo de errores DB con `tenacity.RetryError` capturado explícitamente junto a `SQLAlchemyError` (líneas 60, 67).
- Lock atómico Redis (`SET NX`) en `_iniciar_pedido_y_enviar_menu` para prevenir pedidos duplicados en ráfagas de mensajes (línea 30).
- `ESTADO_NO_CONTEMPLADO` al final actúa como red de seguridad para estados inválidos genuinos sin propagar excepciones.
- El log de `ESTADO_NO_CONTEMPLADO` incluye `mensaje_cliente` con `%r` — seguro, no inyectable.
- Los errores de DB notifican al cliente (tras los fixes de esta sesión).

---

## 3. Hallazgos

### Hallazgo 1

**Tipo:** consistencia de estado
**Severidad:** Media

**Problema:** En `_iniciar_pedido_y_enviar_menu`, `_enviar_bienvenida_menu` se llama fuera del bloque `try/except` que guarda `iniciar_pedido`. Si la API de WhatsApp falla tras crear el pedido en DB, el pedido queda en estado `PENDIENTE` en DB pero el cliente nunca recibió el menú.

**Evidencia:**
```python
# línea 38-46
try:
    gestor_pedidos.iniciar_pedido(id_usuario, direccion_usuario, numero_cliente)
except (SQLAlchemyError, OperationalError) as error:
    ...

menu_texto = mostrar_menu()
_enviar_bienvenida_menu(nombre_usuario, menu_texto, numero_cliente)  # ← fuera del try
```

**Impacto real:** El cliente manda otro mensaje y cae en la rama `PENDIENTE`, donde `procesar_pedido` procesa su nuevo texto como si fuera una selección de menú, sin contexto previo. No es un estado de bloqueo permanente (el cliente puede escribir "1" y avanzar) pero es una experiencia confusa.

**Recomendación mínima concreta:** Este es el comportamiento inherente cuando un envío de WhatsApp falla — no hay forma limpia de rollback del pedido desde aquí. La mitigación real es que la rama `PENDIENTE` ya re-muestra el menú cuando recibe un comando no reconocido (en `procesar_pedido`). Documentar este edge case con un comentario en el código.

---

### Hallazgo 2

**Tipo:** diseño / errores
**Severidad:** Media

**Problema:** `usuario_datos` es un dict accedido con claves literales (`["id"]`, `["direccion"]`, `["nombre"]`) en líneas 34-36 y 59 sin guard de `KeyError`. Si `obtener_usuario_completo` devuelve un dict con estructura diferente a la esperada (bug en el manager, cambio de schema), el `KeyError` burbujea sin log específico.

**Evidencia:**
```python
# línea 34-36
id_usuario = usuario_datos["id"]
direccion_usuario = usuario_datos["direccion"]
nombre_usuario = usuario_datos["nombre"]
```

**Impacto real:** El `KeyError` es capturado por el `except Exception` de `enrutar_mensaje` en `inbound_whatsapp.py` y logueado como "Error procesando mensaje de X" — sin indicar que la causa es un campo faltante en `usuario_datos`. Diagnóstico difícil en producción.

**Recomendación mínima concreta:** Usar `.get()` o añadir una validación con log específico antes de acceder:
```python
if not all(k in usuario_datos for k in ("id", "direccion", "nombre")):
    logger.error("usuario_datos incompleto para %s: claves=%s", numero_cliente, list(usuario_datos))
    _enviar_error_sistema(numero_cliente)
    return "error datos usuario", 500
```

---

### Hallazgo 3

**Tipo:** diseño
**Severidad:** Baja

**Problema:** El bloque `if estado_del_pedido in ESTADOS_TERMINALES_PEDIDO` añadido en línea 134 es código muerto. `obtener_pedido_mas_reciente` ya excluye estados terminales en la query (confirmado en `lifecycle_mixin.py:97`):
```python
estados_excluidos = [e.value for e in ESTADOS_TERMINALES_PEDIDO]
.filter(Pedido.Estado.notin_(estados_excluidos))
```

**Evidencia:** Líneas 134-139 del archivo. Líneas 97-101 de `lifecycle_mixin.py`.

**Impacto real:** Ninguno en producción — el código nunca se ejecuta. Pero confunde al lector: sugiere que `pedido_activo` puede tener estado terminal, lo que no es posible dado el manager.

**Recomendación mínima concreta:** Eliminar el bloque y añadir un comentario explicando por qué no es necesario:
```python
# ESTADOS_TERMINALES_PEDIDO no llegan aquí: obtener_pedido_mas_reciente los excluye en DB.
# Si pedido_activo es None (único resultado posible tras ENTREGADO/CANCELADO/REEMBOLSADO),
# el bloque anterior (línea 72) ya inicia un pedido nuevo.
```

---

### Hallazgo 4

**Tipo:** diseño / testabilidad
**Severidad:** Baja

**Problema:** `ManejadorMensajesRegistrados` es una clase con únicamente métodos `@staticmethod`. No hay estado de instancia, no hay `__init__`, no hay razón para ser una clase. Es un módulo disfrazado de clase. Adicionalmente, sus dependencias (`gestor_pedidos`, `gestor_usuarios`, `redismanager`) son singletons de módulo importados en el top-level — no son inyectables sin monkey-patching.

**Evidencia:** Líneas 23-146 — ningún método de instancia, ningún `self`.

**Impacto real:** Los tests deben hacer `mock.patch("controllers.mensajes_registrados.gestor_pedidos")` en lugar de pasar dependencias. Es el patrón ya establecido en el proyecto (no es una regresión), pero lo bloquea crecer hacia tests más limpios.

**Recomendación mínima concreta:** Por ahora no cambiar — sería un refactor sin beneficio inmediato. Registrar como deuda técnica.

---

### Hallazgo 5

**Tipo:** observabilidad
**Severidad:** Baja

**Problema:** El path de éxito de creación de pedido (línea 47) no tiene `logger.info`. Solo el path de error tiene logging. En producción, no hay forma de saber desde los logs cuántos pedidos se iniciaron correctamente sin leer la DB.

**Evidencia:**
```python
# línea 45-47
menu_texto = mostrar_menu()
_enviar_bienvenida_menu(nombre_usuario, menu_texto, numero_cliente)
return "mensaje enviado", 200  # ← sin log de éxito
```

**Impacto real:** Métricas y debugging limitados. No es operacionalmente crítico porque el lock sí se loguea (línea 31) pero el éxito de `iniciar_pedido` es silencioso.

**Recomendación mínima concreta:**
```python
logger.info("PEDIDO_INICIADO usuario=%s id_usuario=%s", numero_cliente, id_usuario)
```

---

### Hallazgo 6

**Tipo:** diseño
**Severidad:** Baja

**Problema:** La condición en línea 94 usa `or` en lugar de `in`:
```python
if estado_del_pedido == EstadoPedido.ENLACE or estado_del_pedido == EstadoPedido.ENLACE2:
```
Inconsistente con el estilo del bloque de línea 113 que sí usa `in (...)`.

**Evidencia:** Línea 94 vs línea 113.

**Impacto real:** Ninguno funcional. Peor legibilidad.

**Recomendación:**
```python
if estado_del_pedido in (EstadoPedido.ENLACE, EstadoPedido.ENLACE2):
```

---

## 4. Riesgos principales si no se toca

| Riesgo | Escenario concreto |
|---|---|
| `usuario_datos` con clave faltante | Manager cambia el nombre de un campo → `KeyError` silencioso logueado como error genérico → diagnóstico de producción muy difícil |
| Código muerto `ESTADOS_TERMINALES_PEDIDO` | Futuro dev asume que el bloque es activo → introduce lógica condicional dentro de él → nunca se ejecuta, bug silencioso |
| Pedido creado sin menú enviado | WhatsApp API down en el momento exacto de `iniciar_pedido` → cliente en PENDIENTE sin saber que tiene que escribir "1" |

---

## 5. Refactor mínimo recomendado

### Qué tocar primero (en orden de impacto)

1. **Eliminar el bloque muerto** `ESTADOS_TERMINALES_PEDIDO` (líneas 134-139) y añadir el comentario explicativo — 5 minutos, cero riesgo.
2. **Añadir guard de `usuario_datos`** antes de las líneas 34-36 — previene diagnósticos opacos en producción.
3. **Añadir `logger.info` en path de éxito** de `_iniciar_pedido_y_enviar_menu` — observabilidad básica.
4. **Normalizar condición ENLACE** a `in (...)` — consistencia de estilo.

### Qué NO tocar todavía

- La estructura de clase estática — refactor grande sin beneficio inmediato.
- El mecanismo de lock — funciona correctamente, `adquirir_lock` es `fail-open` por diseño documentado.
- La separación notifier/controlador — está bien establecida.

---

## 6. Tests que deberían existir

- `test_iniciar_pedido_db_error_notifica_cliente` — verifica que un `SQLAlchemyError` en `iniciar_pedido` envía mensaje de error al cliente (no silencio).
- `test_confirmando_pago_enlace_nulo_envia_caducado` — verifica que `enlace=None` en estado `CONFIRMANDO_PAGO` envía `_enviar_enlace_caducado` y no el string "None".
- `test_lock_activo_retorna_sin_mensaje` — verifica que con lock activo se retorna 200 sin enviar ningún mensaje WhatsApp.
- `test_estado_no_contemplado_envia_error_generico` — verifica que un estado desconocido (e.g., string inválido en DB) no propaga excepción.
- `test_usuario_datos_incompleto_no_lanza_keyerror` — verifica que un dict sin clave `"id"` retorna 500 con mensaje al cliente, no KeyError.
- `test_terminal_state_inicia_nuevo_pedido` — verifica (posible riesgo no confirmado) que si por alguna razón `obtener_pedido_mas_reciente` devuelve un pedido terminal, el flujo inicia uno nuevo en lugar de caer al error genérico.

---

## 7. Veredicto final

**Estado general del archivo:** Sólido tras los fixes de esta sesión. La lógica de bifurcación es clara y completa para todos los estados del ciclo de vida del pedido.

**¿Bloquea crecimiento?** No. La adición de nuevos estados de pedido requeriría añadir una rama — sencillo.

**¿Bloquea testeo?** Parcialmente. Los singletons de `container` obligan a monkey-patching, patrón ya establecido en el proyecto.

**¿Tiene riesgo operativo real?** Sí, dos: (1) el acceso sin guard a `usuario_datos` puede producir errores opacos difíciles de diagnosticar; (2) el bloque muerto `ESTADOS_TERMINALES_PEDIDO` puede inducir a error a futuros desarrolladores. Ambos son corregibles en menos de 30 minutos.
