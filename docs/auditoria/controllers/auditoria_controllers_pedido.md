# Auditoría de `controllers/pedido.py`

> Auditoría técnica estricta. Fecha: 2026-04-06.
> Archivos analizados: `controllers/pedido.py`, `schemas/twilio.py`, `services/token_service.py`, `utils/menu_opciones.py`, `utils/es_pregunta.py`, `utils/text_utils.py`, `states.py`.

---

## 1. Rol del archivo

**Responsabilidad principal:** Ninguna clara — el archivo mezcla dos flujos completamente independientes que no comparten lógica ni caller.

**Qué debería hacer:** Dado el estado actual, aloja la lógica de parseo de mensajes del bot WhatsApp (`procesar_pedido`) y la lógica de validación y confirmación del carrito web (`confirmar_carrito` + `_validar_productos`).

**Qué no debería hacer:** Contener dos flujos con callers distintos (bot vs. API web), usar globals de `container` mezclados con parámetros inyectables, escribir a Redis antes de confirmar en DB.

**Dependencias clave:**
- `container.gestor_pedidos` — global de módulo para `procesar_pedido`
- `services/token_service.py` — generación de token Redis + enlace de menú
- `utils/menu_opciones.py` — diccionario `menu` (global hardcodeado)
- `maps_module.geocodificar_direccion` — llamada API externa en `confirmar_carrito`
- `gestor_pedidos`, `gestor_productos`, `cache` — inyectados como parámetros en `confirmar_carrito`

**Nivel de criticidad: Crítico** — `confirmar_carrito` es el punto donde el carrito pasa de "en sesión" a "pedido real en DB". Un fallo silencioso o un carrito vacío aceptado aquí tiene impacto económico directo.

---

## 2. Lo que hace bien

- `confirmar_carrito` recibe sus dependencias de DB, Redis y configuración como parámetros (líneas 117-127) — correcto y testeable sin mocks de módulo.
- `_validar_productos` verifica código, cantidad y precio contra DB antes de persistir — previene manipulación client-side del precio. Implementación del control de seguridad más importante del flujo de pago.
- La guardia de estado en línea 141 (`if pedido_activo.Estado != EstadoPedido.ENLACE`) impide confirmar un carrito en el estado equivocado.
- El comentario en línea 169 documenta explícitamente la atomicidad del commit de `fijar_carrito_confirmado` — buena señal de intención.
- `procesar_pedido` delega la validación de inputs a `PedidoInput` (Pydantic) en lugar de validar manualmente.
- `logger.info("PEDIDO_INICIADO")` y `logger.info("CARRITO_CONFIRMADO")` en los happy paths dan trazabilidad de los eventos de negocio más importantes.

---

## 3. Hallazgos

### Hallazgo 1

**Tipo:** diseño
**Severidad: Alta**

**Problema:** El archivo contiene dos flujos con responsabilidades, callers y dependencias completamente distintas. `procesar_pedido` es llamado por el bot WhatsApp (worker de RQ), usa `menu` global y `gestor_pedidos` del container. `confirmar_carrito` + `_validar_productos` son llamados por la API web (`blueprints/api/`), reciben todo por parámetros y no tocan el menú. No comparten ninguna línea de lógica.

**Evidencia:**
```python
# Flujo 1: bot WhatsApp
def procesar_pedido(pedido, numero_cliente, id_pedido_actual, usuario_datos):
    from container import gestor_pedidos  # ← global, no inyectado
    for categoria, items in menu.items():  # ← global hardcodeado
        ...

# Flujo 2: API web
def confirmar_carrito(..., cache, gestor_pedidos, gestor_productos, public_url):  # ← todo inyectado
    ...
def _validar_productos(productos_recibidos, gestor_productos):  # ← helper de confirmar_carrito
    ...
```

**Impacto real:** Cualquier cambio en el flujo de carrito (ej: añadir lógica de descuento) requiere tocar un archivo que también contiene la lógica de parseo del bot. Los tests de ambos flujos viven juntos aunque requieren fixtures completamente diferentes. Dificulta encontrar el código y razonar sobre responsabilidades.

**Recomendación mínima concreta:** Mover `confirmar_carrito` y `_validar_productos` a `controllers/carrito.py`. `procesar_pedido` puede quedarse en `pedido.py` o renombrarse a `controllers/bot_menu.py`. No cambiar firmas ni lógica.

---

### Hallazgo 2

**Tipo:** consistencia / seguridad
**Severidad: Crítica**

**Problema:** `confirmar_carrito` no valida que `productos_recibidos` sea una lista no vacía. Con una lista vacía, `_validar_productos` devuelve `True, ([], 0.0)` — sin ningún error. El flujo continúa y persiste un pedido con **0 productos y total 0** en Redis y DB.

**Evidencia:**
```python
# _validar_productos líneas 65-112
def _validar_productos(productos_recibidos: list, gestor_productos) -> tuple:
    productos = []
    total = 0.0
    for p in productos_recibidos:  # ← si la lista está vacía, el for no itera
        ...
    return True, (productos, round(total, 2))  # ← True con lista vacía

# confirmar_carrito línea 129
ok, resultado = _validar_productos(productos_recibidos, gestor_productos)
if not ok:  # ← nunca se activa con lista vacía
    return False, resultado
```

**Impacto real:** Un cliente puede confirmar el carrito con 0 artículos. El pedido llega al dashboard con total 0€, confundiendo a operaciones. Si el pago se procesa (Monei), se cobra 0€. Si es contra reembolso, el repartidor llega con un "pedido" vacío.

**Recomendación mínima concreta:** Añadir al inicio de `confirmar_carrito`:
```python
if not productos_recibidos:
    logger.warning("confirmar_carrito: carrito vacío para usuario %s", user_id)
    return False, "El carrito no puede estar vacío"
```

---

### Hallazgo 3

**Tipo:** consistencia
**Severidad: Alta**

**Problema:** En `confirmar_carrito`, Redis se escribe **antes** de que la DB confirme la transición de estado. Si `fijar_carrito_confirmado` falla (excepción o timeout de SQL Server), Redis tiene el carrito con TTL 3600s pero el pedido en DB sigue en estado `ENLACE`. En el siguiente reintento del cliente, la guardia de estado en línea 141 vuelve a pasar (estado sigue siendo `ENLACE`), Redis se sobreescribe, y se reintenta la transición de DB — comportamiento finalmente idempotente. Sin embargo, durante la ventana entre ambas escrituras, el estado es inconsistente y cualquier lectura del carrito desde Redis encuentra datos sin orden correspondiente en DB.

**Evidencia:**
```python
# línea 149 — PRIMERO Redis
cache.set(pedido_id_redis, json.dumps({...}), ex=3600)

# línea 164 — luego API externa (puede fallar o tardar)
coords = geocodificar_direccion(direccion)

# línea 170 — DESPUÉS DB (sin try/except)
gestor_pedidos.fijar_carrito_confirmado(pedido_id_db, pedido_id_redis, lat=lat, lng=lng)
```

**Impacto real:** Si Maps API tarda 5s y la conexión SQL Server cae en ese intervalo, Redis tiene el carrito pero DB no ha transitado. El carrito queda "activo" en Redis 1h sin pedido correspondiente en ENLACE2.

**Recomendación mínima concreta:** Invertir el orden: primero DB, luego Redis. La transición de estado es la operación crítica; el carrito en Redis es cache recuperable:
```python
gestor_pedidos.fijar_carrito_confirmado(pedido_id_db, pedido_id_redis, lat=lat, lng=lng)
# Solo si DB confirma:
cache.set(pedido_id_redis, json.dumps({...}), ex=3600)
```

---

### Hallazgo 4

**Tipo:** errores
**Severidad: Alta**

**Problema:** `gestor_pedidos.obtener_pedido_mas_reciente` (línea 134) y `gestor_pedidos.fijar_carrito_confirmado` (línea 170) en `confirmar_carrito` no tienen try/except. Si cualquiera lanza `SQLAlchemyError` o `OperationalError`, la excepción se propaga sin capturar al blueprint que llama a `confirmar_carrito`, que probablemente devuelve un 500. En la capa del manager hay `tenacity` para reintentos, pero si todos los reintentos fallan, la excepción sube.

**Evidencia:**
```python
# línea 134 — sin try/except
pedido_activo = gestor_pedidos.obtener_pedido_mas_reciente(user_id)

# línea 170 — sin try/except
gestor_pedidos.fijar_carrito_confirmado(pedido_id_db, pedido_id_redis, lat=lat, lng=lng)
```

Contraste con el patrón correcto usado en `mensajes_registrados.py` líneas 59-64.

**Impacto real:** Una caída de SQL Server en el momento del checkout devuelve una excepción no capturada al cliente web. El blueprint probablemente la convierte en 500, el cliente ve un error genérico sin mensaje útil.

**Recomendación mínima concreta:**
```python
try:
    pedido_activo = gestor_pedidos.obtener_pedido_mas_reciente(user_id)
except (SQLAlchemyError, RetryError) as e:
    logger.error("confirmar_carrito: DB error obteniendo pedido usuario=%s: %s", user_id, e)
    return False, "Error de base de datos. Intente más tarde."
```

---

### Hallazgo 5

**Tipo:** idempotencia
**Severidad: Media**

**Problema:** En `procesar_pedido`, `generar_enlace` crea y persiste un token en Redis **antes** de que `gestor_pedidos.iniciar_enlace` lo confirme en DB. Si `iniciar_enlace` devuelve `False` (ej: segundo reintento de Meta donde el estado ya transitó a `ENLACE`), el token del segundo llamado queda huérfano en Redis con TTL 24h. Es un enlace válido que apunta a datos de usuario reales pero sin pedido activo en `ENLACE`.

**Evidencia:**
```python
# líneas 44-54
enlace = generar_enlace(item, usuario_datos)     # ← token creado en Redis aquí
if not gestor_pedidos.iniciar_enlace(...):        # ← si falla, el token ya existe
    return "❌ Ocurrió un error..."               # ← token huérfano, nunca limpiado
```
```python
# token_service.py:29
redismanager.set(token, json.dumps(datos_usuario), ex=86400)  # 24h TTL
```

**Impacto real:** En cada reintento de Meta, se acumulan tokens huérfanos válidos en Redis. El riesgo de seguridad es bajo (el token solo expone nombre, dirección y número del usuario propio), pero es un leak de información y un desperdicio de espacio en Redis.

**Recomendación mínima concreta:** Generar el token solo después de confirmar que `iniciar_enlace` puede ejecutarse, o verificar el estado del pedido antes de llamar a `generar_enlace`:
```python
# Verificar estado antes de generar token
if pedido_activo.Estado != EstadoPedido.PENDIENTE:
    return "❌ Ocurrió un error al procesar la opción."
enlace = generar_enlace(item, usuario_datos)
gestor_pedidos.iniciar_enlace(id_pedido_actual, enlace)
```

---

### Hallazgo 6

**Tipo:** rendimiento
**Severidad: Media**

**Problema:** `_validar_productos` ejecuta una query a DB por cada producto en el carrito (línea 84 dentro del loop). Para un pedido de N productos, son N queries secuenciales.

**Evidencia:**
```python
# líneas 69-110 — N queries para N productos
for p in productos_recibidos:
    ...
    producto_db = gestor_productos.obtener_producto_por_codigo(codigo)  # ← query en cada iteración
```

**Impacto real:** Bajo con el menú actual (tienda online con pocos productos), pero si el catálogo crece o si los pedidos tienen muchos ítems, el tiempo de respuesta del checkout escala linealmente con el número de productos. Con SQL Server y latencia de red de contenedor a contenedor, cada query puede sumar 10-20ms.

**Recomendación mínima concreta:** Extraer todos los códigos de `productos_recibidos` y hacer una sola query con `WHERE Codigo IN (...)` antes del loop. Solo aplicar si el catálogo o los pedidos crecen — actualmente no es urgente.

---

### Hallazgo 7

**Tipo:** diseño
**Severidad: Media**

**Problema:** El parámetro `gestor_pedidos` en `confirmar_carrito` (línea 124) tiene el mismo nombre que el import de módulo en línea 7 (`from container import gestor_pedidos`). Dentro de `confirmar_carrito`, el nombre local sombrea el global sin error. Es funcionalmente correcto (Python resuelve el local primero), pero cualquier desarrollador que lea el archivo asume que son el mismo objeto — y no lo son necesariamente.

**Evidencia:**
```python
# línea 7 — import global
from container import gestor_pedidos

# línea 124 — parámetro que sombrea el global
def confirmar_carrito(..., gestor_pedidos, ...):
    pedido_activo = gestor_pedidos.obtener_pedido_mas_reciente(user_id)  # ← ¿cuál gestor_pedidos?
```

**Impacto real:** Confusión de lectura. Un refactor descuidado que elimine el parámetro y no actualice el import haría que `confirmar_carrito` use el singleton del container en lugar del inyectado — rompiendo los tests que mockean el parámetro.

**Recomendación mínima concreta:** Renombrar el parámetro a `gp` o `pedidos_manager` en la firma de `confirmar_carrito` para que no colisione con el global.

---

### Hallazgo 8

**Tipo:** seguridad
**Severidad: Media (posible riesgo no confirmado)**

**Problema:** `nombre_producto` (línea 71) e `ingredientes_removidos` (línea 101) son campos user-supplied desde el cuerpo de la petición web, sin sanitización. Se almacenan en Redis (línea 103) y potencialmente en la tabla `pedido_detalles` vía `fijar_carrito_confirmado`. Si el dashboard o la cocina renderizan estos campos en HTML sin escapar, hay riesgo de XSS.

**Evidencia:**
```python
# línea 71 — user-supplied, sin validación de contenido
nombre_producto = p.get("nombre", "Producto desconocido")

# línea 102 — user-supplied list, unida como string
notas = f"Sin: {', '.join(removed)}" if removed else ""
```

**No confirmado:** Sin leer los templates del dashboard y cocina no es posible determinar si Jinja2 auto-escapa estos campos. Si usan `{{ notas }}` (con auto-escape activo en Flask por defecto), el riesgo es nulo. Si usan `{{ notas | safe }}`, es XSS.

**Recomendación:** Verificar los templates que renderizan `notas` y el nombre del producto. Si hay algún `| safe`, eliminar o sanitizar los datos antes de persistir.

---

### Hallazgo 9

**Tipo:** observabilidad
**Severidad: Baja**

**Problema:** En `procesar_pedido`, dos paths frecuentes no tienen logging: (a) comando no reconocido (línea 57) y (b) pregunta detectada (línea 30). No hay forma de saber en producción cuántos mensajes llegan sin coincidir con el menú ni cuántos usuarios intentan conversar con el bot.

**Evidencia:**
```python
# línea 29-30 — sin log
if es_pregunta(datos.pedido):
    return "Lo siento, no reconocí tu pregunta."

# línea 57-58 — sin log
menu_comando_no_reconocido = mostrar_menu()
return f"❌Comando no reconocido..."
```

**Impacto real:** Imposible detectar si hay un surge de comandos no reconocidos (ej: texto libre enviado por error) o si el parser de preguntas está siendo demasiado agresivo.

**Recomendación mínima concreta:**
```python
logger.info("PREGUNTA_DETECTADA usuario=%s input=%r", numero_cliente, datos.pedido)
logger.info("COMANDO_NO_RECONOCIDO usuario=%s input=%r", numero_cliente, pedido_limpio)
```

---

## 4. Riesgos principales si no se toca

| Riesgo | Escenario concreto |
|--------|-------------------|
| Pedido con 0 productos y 0€ | Cliente envía carrito vacío (bug de JS o petición manual) → pasa validación → entra en producción |
| Estado inconsistente Redis/DB | SQL Server cae tras `cache.set` y antes de `fijar_carrito_confirmado` → carrito en Redis sin pedido en ENLACE2 |
| Tokens huérfanos acumulados | Meta reintenta → `generar_enlace` crea token antes de verificar estado → tokens válidos sin pedido asociado |
| Excepción DB no capturada en checkout | `obtener_pedido_mas_reciente` o `fijar_carrito_confirmado` lanzan → excepción llega al blueprint → 500 sin log ni mensaje al usuario |
| Confusión de `gestor_pedidos` | Refactor elimina parámetro accidentalmente → `confirmar_carrito` usa singleton silenciosamente → tests pasan pero prod usa gestor diferente |

---

## 5. Refactor mínimo recomendado

### Qué tocar primero (en orden de impacto)

1. **Añadir guardia de carrito vacío** al inicio de `confirmar_carrito` (Hallazgo 2). Tres líneas. Máximo impacto, mínimo cambio.

2. **Invertir el orden Redis/DB** en `confirmar_carrito` (Hallazgo 3). Mover `cache.set` después de `fijar_carrito_confirmado`. Elimina la ventana de inconsistencia.

3. **Wrappear `obtener_pedido_mas_reciente` y `fijar_carrito_confirmado` en try/except** (Hallazgo 4). Ocho líneas. Evita que excepciones de DB lleguen al blueprint sin log.

4. **Mover `confirmar_carrito` y `_validar_productos` a `controllers/carrito.py`** (Hallazgo 1). Sin cambios de lógica. Separa las responsabilidades y facilita encontrar el código.

### Qué NO tocar todavía

- La lógica de `_validar_productos` — es correcta y es el control de seguridad más importante del flujo de pago.
- La firma de `confirmar_carrito` — está bien diseñada con parámetros inyectables.
- `procesar_pedido` — funciona correctamente para el flujo del bot.
- El N+1 en `_validar_productos` (Hallazgo 6) — no es urgente con el catálogo actual.

---

## 6. Tests que deberían existir

- `test_confirmar_carrito_vacio_rechazado`: `productos_recibidos=[]` → devuelve `False, "El carrito no puede estar vacío"`.
- `test_confirmar_carrito_db_error_capturado`: `obtener_pedido_mas_reciente` lanza `SQLAlchemyError` → devuelve `False, mensaje_error`, no propaga excepción.
- `test_confirmar_carrito_estado_incorrecto`: pedido en estado `ENLACE2` → devuelve `False` sin modificar Redis ni DB.
- `test_validar_productos_codigo_inexistente`: producto con código no en DB → devuelve `False, mensaje`.
- `test_validar_productos_precio_desde_db`: producto con precio manipulado en el request → el precio guardado viene de DB, no del request.
- `test_procesar_pedido_opcion_valida`: mensaje `"1"` → genera enlace, llama a `iniciar_enlace`, devuelve mensaje con URL.
- `test_procesar_pedido_comando_no_reconocido`: mensaje libre → devuelve menú de opciones.
- `test_procesar_pedido_enlace_fallido_no_deja_token_huerfano`: `iniciar_enlace` devuelve False → el token generado debería invalidarse (test que documenta el bug del Hallazgo 5 hasta que se corrija).

---

## 7. Veredicto final

**Estado general del archivo:** Funcionalmente correcto en el happy path, pero con un bug crítico de negocio (carrito vacío aceptado), un riesgo de inconsistencia de estado y dos flujos independientes que no deberían coexistir. La mezcla de flujos es el problema estructural principal — lo que hace bien `confirmar_carrito` (dependencias inyectables, validación de precios) queda oscurecido por convivir con `procesar_pedido`.

**¿Bloquea crecimiento?** Sí. Añadir lógica al flujo de carrito (descuentos, cupones, stock) requiere modificar el mismo archivo que maneja el parseo del bot. Los dominios se contaminan entre sí.

**¿Bloquea testeo?** Parcialmente. `confirmar_carrito` es testeable por diseño. `procesar_pedido` requiere parchear `container.gestor_pedidos` y el global `menu` — posible pero frágil.

**¿Tiene riesgo operativo real?** Sí. El Hallazgo 2 (carrito vacío aceptado) puede estar ocurriendo hoy si hay algún bug de frontend que envía el carrito antes de añadir productos. Es el único hallazgo que no requiere un escenario de fallo técnico para activarse — solo un cliente con un carrito vacío.
