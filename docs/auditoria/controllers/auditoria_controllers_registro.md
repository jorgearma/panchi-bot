# Auditoría de `controllers/registro.py`

> Auditoría técnica estricta. Fecha: 2026-04-06.
> Archivos analizados: `controllers/registro.py`, `controllers/registro_notifier.py`, `managers/estado_usuario.py`, `states.py`.

---

## 1. Rol del archivo

**Responsabilidad principal:** Orquestador de la máquina de estados del registro conversacional de usuarios nuevos vía WhatsApp.

**Qué debería hacer:** Leer estado desde Redis, hacer avanzar la máquina de estados, delegar notificaciones al notifier, delegar persistencia a los managers.

**Qué no debería hacer:** Importar dependencias en el cuerpo de funciones, mezclar funciones sueltas con la clase orquestadora, dejar estados inconsistentes en Redis al terminar.

**Dependencias clave:**
- `managers/estado_usuario.py` — lectura/escritura de estado en Redis
- `states.py` — enums y tabla de transiciones válidas
- `controllers/registro_notifier.py` — envío de mensajes WhatsApp
- `maps_module` — validación de dirección y sugerencias de calle
- `container.py` — inyección de `gestor_usuarios` y `gestor_pedidos` (importado _lazy_ dentro de una función)

**Nivel de criticidad: Crítico** — Es el único camino de alta de nuevos usuarios. Un fallo silencioso o una race condition aquí bloquea permanentemente a un cliente nuevo.

---

## 2. Lo que hace bien

- La separación entre `RegistroUsuario` (lógica) y `registro_notifier` (mensajes WhatsApp) es correcta y limpia.
- `EstadoUsuario` encapsula bien Redis con reintentos via `tenacity` y valida transiciones antes de persistir.
- El rollback `CONFIRMANDO_DIRECCION → ESPERANDO_DIRECCION` existe y funciona.
- `_es_nombre_valido` es simple y cubre los casos de uso reales (nombres españoles con tildes, guiones, apóstrofes).
- El log de `REGISTRO_COMPLETADO` en `confirmar_direccion` da trazabilidad del happy path.

---

## 3. Hallazgos

### Hallazgo 1

**Tipo:** consistencia / seguridad  
**Severidad: Crítica**

**Problema:** `confirmar_direccion` no verifica si el usuario ya existe en DB antes de llamar `guardar_usuario`. WhatsApp Meta puede entregar el mismo mensaje dos veces (reintento ante timeout). Si llegan dos mensajes idénticos con estado `CONFIRMANDO_DIRECCION` antes de que el primero termine, se ejecutan dos `guardar_usuario` + dos `iniciar_pedido` sobre el mismo número.

**Evidencia:**
```python
# registro.py:32-38
gestor_usuarios.guardar_usuario(numero_cliente, estado["nombre"], estado["direccion"])
...
usuario_info = gestor_usuarios.obtener_usuario_completo(numero_cliente)
if usuario_info:
    gestor_pedidos.iniciar_pedido(usuario_info["id"], estado["direccion"], numero_cliente)
```
No hay ningún `if usuario_ya_existe: return` antes del insert.

**Impacto real:** Usuario duplicado en DB + pedido huérfano iniciado dos veces. Si la tabla tiene una restricción `UNIQUE` sobre el número, el segundo insert lanza una excepción no capturada que aborta el flujo sin notificar al usuario. Si no hay restricción, hay dos registros activos para el mismo número.

**Recomendación mínima concreta:**
```python
def confirmar_direccion(numero_cliente, mensaje_cliente, data_redis):
    if mensaje_cliente.lower() != 'si':
        return False
    from container import gestor_usuarios, gestor_pedidos
    # Guardia de idempotencia
    if gestor_usuarios.obtener_usuario_completo(numero_cliente):
        logger.warning("REGISTRO_DUPLICADO usuario=%s — ya existe en DB", numero_cliente)
        return "Usuario ya registrado", 200
    estado = data_redis
    gestor_usuarios.guardar_usuario(numero_cliente, estado["nombre"], estado["direccion"])
    ...
```

---

### Hallazgo 2

**Tipo:** consistencia  
**Severidad: Alta**

**Problema:** Tras el registro exitoso, la clave de Redis del usuario **no se elimina**. El estado `{"estado": "confirmando_direccion", "nombre": "...", "direccion": "..."}` permanece en Redis indefinidamente. La próxima vez que el bot procese un mensaje del usuario (si el caller no verifica DB antes de llamar a `manejar_registro`), el usuario podría ser re-enviado al flujo de registro.

**Evidencia:** No hay ninguna llamada a `redismanager.delete(numero_cliente)` ni a `actualizar_estado` después de `guardar_usuario`. La tabla de transiciones en `states.py` tampoco tiene transición de salida desde `CONFIRMANDO_DIRECCION` para el caso de éxito (solo el rollback a `ESPERANDO_DIRECCION`).

**Impacto real:** Riesgo de estado fantasma en Redis. Si el TTL de la clave es largo o inexistente, el usuario registrado puede quedar atrapado en el flujo de registro en la siguiente sesión.

**Recomendación mínima concreta:** Al final del happy path de `confirmar_direccion`, limpiar la clave:
```python
self.redismanager.delete(numero_cliente)
```
O bien, hacer que `actualizar_estado` acepte un estado terminal explícito que el caller use antes de borrar.

---

### Hallazgo 3

**Tipo:** consistencia / errores  
**Severidad: Alta**

**Problema:** `manejar_registro` devuelve HTTP 400 para errores de validación de _input del usuario_ (nombre inválido, dirección inválida). El webhook de WhatsApp Meta interpreta cualquier respuesta no-2xx como fallo y **reintenta** la entrega del mensaje. Esto causa que el mismo mensaje inválido sea procesado múltiples veces, incrementando el número de mensajes de error enviados al usuario y generando ruido en los logs.

**Evidencia:**
```python
# línea 84
return "Nombre inválido", 400

# línea 98
return "Dirección inválida", 400
```

**Impacto real:** El usuario recibe el mensaje de "nombre inválido" o "dirección inválida" dos o tres veces (tantas como reintentos haga Meta). En producción esto se ve como un bug del bot.

**Recomendación mínima concreta:** Devolver `200` en todos los casos donde el mensaje fue procesado correctamente (aunque el input del usuario sea incorrecto). El 400 debería reservarse para fallos _técnicos_ del servidor, no para validación de negocio:
```python
return "Nombre inválido, solicitado reintento", 200
```

---

### Hallazgo 4

**Tipo:** consistencia  
**Severidad: Alta**

**Problema:** El estado `ESPERANDO_CONFIRMACION` no tiene salida cuando el usuario responde algo distinto de las palabras clave de confirmación. El estado no se actualiza — el usuario queda permanentemente atrapado recibiendo el mensaje de `_enviar_registro_pendiente` en cada mensaje que envíe.

**Evidencia:**
```python
# líneas 68-75
elif estado_actual == EstadoRegistro.ESPERANDO_CONFIRMACION:
    if mensaje_cliente.lower() in {"sí", "si", "quiero", "adelante"}:
        ...
    else:
        _enviar_registro_pendiente(self.numero_cliente)
        return "Registro cancelado", 200
        # ← estado no cambia; próximo mensaje vuelve aquí
```

**Impacto real:** Un usuario que responde "no quiero" o "mejor luego" queda atrapado. Cada mensaje suyo dispara `_enviar_registro_pendiente`. No hay forma de salir del flujo sin intervención manual en Redis.

**Recomendación mínima concreta:** Añadir un estado `REGISTRO_RECHAZADO` (o simplemente borrar la clave de Redis) cuando el usuario no confirma, permitiéndole comenzar de nuevo en el futuro:
```python
else:
    self.redismanager.delete(self.numero_cliente)  # reset limpio
    _enviar_registro_pendiente(self.numero_cliente)
    return "Registro cancelado", 200
```

---

### Hallazgo 5

**Tipo:** errores / consistencia  
**Severidad: Alta**

**Problema:** `confirmar_direccion` no tiene manejo de excepciones. Si `guardar_usuario` lanza una excepción (timeout de SQL Server, violación de constraint), la excepción sube sin capturar. El usuario queda con estado Redis en `CONFIRMANDO_DIRECCION` y sin registro en DB. El siguiente mensaje del usuario intentará confirmar de nuevo, pero ahora `obtener_usuario_completo` puede o no devolver datos dependiendo de si el insert parcial se deshizo.

**Evidencia:**
```python
# líneas 32-38 — sin try/except
gestor_usuarios.guardar_usuario(numero_cliente, estado["nombre"], estado["direccion"])
logger.info("REGISTRO_COMPLETADO usuario=%s", numero_cliente)
...
gestor_pedidos.iniciar_pedido(...)
```
El `logger.info("REGISTRO_COMPLETADO")` se ejecuta _antes_ de que `iniciar_pedido` se llame — si ese falla, el log miente.

**Impacto real:** Estado inconsistente entre Redis y DB. El usuario recibe un error 500 genérico desde el webhook (o no recibe respuesta), pero sigue registrado a medias.

**Recomendación mínima concreta:**
```python
try:
    gestor_usuarios.guardar_usuario(...)
    usuario_info = gestor_usuarios.obtener_usuario_completo(numero_cliente)
    if usuario_info:
        gestor_pedidos.iniciar_pedido(...)
    logger.info("REGISTRO_COMPLETADO usuario=%s", numero_cliente)  # mover al final
except Exception as e:
    logger.error("REGISTRO_FALLIDO usuario=%s error=%s", numero_cliente, e)
    # notificar al usuario con mensaje de error genérico
    return "Error en registro", 200  # 200 para evitar reintento Meta
```

---

### Hallazgo 6

**Tipo:** diseño  
**Severidad: Media**

**Problema:** `confirmar_direccion` es una función suelta a nivel de módulo con un **import lazy** dentro de su cuerpo. Rompe la cohesión del diseño basado en clase y oculta la dependencia real de `container`.

**Evidencia:**
```python
# línea 30
from container import gestor_usuarios, gestor_pedidos
```
Este import ocurre dentro del cuerpo de la función, en tiempo de ejecución, para evitar importación circular. El síntoma indica un problema de diseño en las capas, no que el import lazy sea la solución correcta.

**Impacto real:** Dificulta el testing (no se puede inyectar mocks a nivel de módulo antes de que la función se llame), oculta el grafo de dependencias, y convierte lo que debería ser un método de la clase en una función libre con acceso a globals implícitos.

**Recomendación mínima concreta:** Mover `confirmar_direccion` dentro de `RegistroUsuario` y recibir los managers como parámetros en `__init__` o en el método:
```python
class RegistroUsuario:
    def __init__(self, numero_cliente, redismanager, gestor_usuarios, gestor_pedidos):
        ...
```
Alternativamente, aceptar los managers como parámetros en la función suelta para poder mockearlos en tests.

---

### Hallazgo 7

**Tipo:** consistencia  
**Severidad: Media**

**Problema:** El nombre del usuario se guarda en Redis **sin `.strip()`**. `_es_nombre_valido` hace `.strip()` internamente para validar pero no modifica la variable original. Si el usuario envía `" Juan "`, pasa la validación pero se guarda `" Juan "` en Redis y luego en DB.

**Evidencia:**
```python
# línea 78-79
if _es_nombre_valido(mensaje_cliente):
    self.estado_usuario.actualizar_estado(EstadoRegistro.ESPERANDO_DIRECCION, {"nombre": mensaje_cliente})
```
```python
# _es_nombre_valido línea 45
nombre = nombre.strip()  # strip solo local, no modifica el argumento
```

**Impacto real:** Nombres con espacios iniciales/finales en la DB y en mensajes al usuario ("¡Gracias  Juan !").

**Recomendación mínima concreta:**
```python
nombre_limpio = mensaje_cliente.strip()
if _es_nombre_valido(nombre_limpio):
    self.estado_usuario.actualizar_estado(EstadoRegistro.ESPERANDO_DIRECCION, {"nombre": nombre_limpio})
```

---

### Hallazgo 8

**Tipo:** rendimiento  
**Severidad: Baja**

**Problema:** En el branch `CONFIRMANDO_DIRECCION`, Redis se lee dos veces: una en la línea 61 (solo para obtener `["estado"]`) y otra en la línea 101 (para obtener el objeto completo con nombre y dirección). La primera lectura descarta todos los datos que luego se necesitan en la segunda.

**Evidencia:**
```python
# línea 61
estado_actual = self.estado_usuario.obtener_estado()["estado"]
# ...
# línea 101
data_redis = self.estado_usuario.obtener_estado()
```

**Impacto real:** Bajo en producción con Redis local. Pero es un patrón que crea ruido innecesario en Redis y puede ser confuso en trazas.

**Recomendación mínima concreta:** Leer el estado completo una sola vez al inicio de `manejar_registro` y extraer `["estado"]` de ahí:
```python
estado_data = self.estado_usuario.obtener_estado()
estado_actual = estado_data["estado"]
```
Luego en `CONFIRMANDO_DIRECCION` usar `estado_data` directamente sin segunda lectura.

---

### Hallazgo 9

**Tipo:** errores / observabilidad  
**Severidad: Baja**

**Problema:** `sugerir_calle(mensaje_cliente)` en la línea 94 no está protegida con try/except. Si `maps_module` lanza una excepción (API de mapas caída, error de red), la excepción sube sin capturar y el usuario no recibe respuesta de error de dirección.

**Evidencia:**
```python
# línea 94
sugerencia, alta_confianza = sugerir_calle(mensaje_cliente)
```

**Impacto real:** Posible excepción no capturada que provoca un 500 en el webhook. Meta reintentará el mensaje.

**Recomendación mínima concreta:**
```python
try:
    sugerencia, alta_confianza = sugerir_calle(mensaje_cliente)
except Exception:
    logger.warning("sugerir_calle falló para usuario=%s", self.numero_cliente, exc_info=True)
    sugerencia, alta_confianza = None, None
```

---

### Hallazgo 10

**Tipo:** observabilidad  
**Severidad: Baja**

**Problema:** Los paths de validación fallida (nombre inválido, dirección inválida, respuesta inválida en confirmación) no tienen logging. Solo el happy path tiene `logger.info`. No es posible saber en producción con qué frecuencia fallan las validaciones ni cuáles son las entradas que las provocan.

**Evidencia:** Líneas 83, 93-98, 104 — ninguna tiene `logger.warning` ni `logger.info`.

**Impacto real:** Imposible detectar si `validar_direccion` tiene una tasa de rechazo alta o si hay un bug en el regex de nombres.

**Recomendación mínima concreta:**
```python
logger.info("NOMBRE_INVALIDO usuario=%s input=%r", self.numero_cliente, mensaje_cliente)
logger.info("DIRECCION_INVALIDA usuario=%s motivo=%s input=%r", self.numero_cliente, motivo, mensaje_cliente)
```

---

### Hallazgo 11 — Posible riesgo no confirmado

**Tipo:** diseño  
**Severidad: Media (no confirmada)**

**Problema:** `validar_direccion(mensaje_cliente)` en línea 87 se llama con un solo argumento. La firma documentada en CLAUDE.md es `validar_direccion(address, territory)`. No se puede confirmar sin leer `maps_module/__init__.py` si `territory` tiene valor por defecto o si falta el argumento obligatorio.

**Recomendación:** Verificar la firma real de `validar_direccion` en `maps_module`. Si `territory` es obligatorio, la llamada fallará en runtime con `TypeError`.

---

## 4. Riesgos principales si no se toca

| Riesgo | Escenario |
|--------|-----------|
| Usuario duplicado en DB | Meta reintenta el mensaje de confirmación → dos llamadas a `guardar_usuario` |
| Estado Redis fantasma | Usuario registrado pero Redis sigue con estado de registro → posible bucle en próxima sesión |
| Usuario atrapado en `ESPERANDO_CONFIRMACION` | Cualquier respuesta negativa → loop infinito de mensajes de "registro pendiente" |
| Doble mensaje de error al usuario | `return 400` en validación → Meta reintenta → usuario recibe el mensaje dos veces |
| Registro a medias sin notificación | Exception en `guardar_usuario` → Redis queda en `confirmando_direccion`, DB vacía, usuario no notificado |

---

## 5. Refactor mínimo recomendado

### Qué tocar primero (en orden de impacto)

1. **Añadir guardia de idempotencia** en `confirmar_direccion` (chequeo de usuario existente antes del insert). Una línea. Máximo impacto.

2. **Cambiar los `return 400` a `return 200`** en los paths de validación de usuario (líneas 84 y 98). Dos cambios de un carácter. Elimina los reintentos de Meta.

3. **Borrar la clave de Redis** al completar el registro. Una línea. Elimina el estado fantasma.

4. **Añadir un `try/except` en `confirmar_direccion`** alrededor de `guardar_usuario` + `iniciar_pedido`. Log del error, respuesta 200, notificación al usuario.

5. **Reset de estado en cancelación** de `ESPERANDO_CONFIRMACION`. Una línea (`redismanager.delete`).

### Qué NO tocar todavía

- La separación `RegistroUsuario` / `registro_notifier` — está bien diseñada.
- `_es_nombre_valido` — funciona, no vale la pena integrar spaCy aquí todavía.
- La estructura de `EstadoUsuario` — bien encapsulada con `tenacity`.
- El rollback de dirección — funciona correctamente.

---

## 6. Tests que deberían existir

- `test_registro_idempotente`: enviar mensaje "si" dos veces en estado `CONFIRMANDO_DIRECCION` — solo debe crearse un usuario.
- `test_registro_cancelacion_no_queda_atrapado`: responder "no" en `ESPERANDO_CONFIRMACION` — el estado debe limpiarse, no permanecer.
- `test_registro_nombre_con_espacios`: enviar `" Juan "` — el nombre guardado debe ser `"Juan"`.
- `test_registro_400_no_retornado`: validar que ningún path de `manejar_registro` devuelve 400 ante input de usuario inválido.
- `test_registro_excepcion_guardar_usuario`: simular excepción en `guardar_usuario` — debe devolver 200 y loguear el error.
- `test_validar_direccion_llamada_correcta`: verificar que `validar_direccion` recibe los argumentos correctos.
- `test_sugerir_calle_falla`: simular excepción en `sugerir_calle` — debe degradar a `sugerencia=None` sin explotar.

---

## 7. Veredicto final

**Estado general del archivo:** Funcional en el happy path, frágil en los edge cases. El diseño de base es correcto pero hay errores de implementación concretos que ya están causando o causarán problemas en producción.

**¿Bloquea crecimiento?** No en lo inmediato, pero el import lazy y la función suelta `confirmar_direccion` dificultan añadir lógica futura (p.ej. soporte multi-territorio, validación de dirección alternativa).

**¿Bloquea testeo?** Sí. El import lazy de `container` dentro de `confirmar_direccion` hace imposible inyectar mocks estándar. Los tests deben parchear `container` a nivel de módulo o usar `importlib.reload`, lo cual es frágil.

**¿Tiene riesgo operativo real?** Sí. Los hallazgos 1 (duplicados), 3 (reintentos Meta), 4 (usuario atrapado) y 5 (registro a medias) pueden y probablemente están ocurriendo en producción con baja frecuencia. Con crecimiento de usuarios, la frecuencia de reintentos de Meta aumenta y los duplicados se vuelven más probables.
