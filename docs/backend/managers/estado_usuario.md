# EstadoUsuario

**Archivo:** `managers/estado_usuario.py`  
**Capa:** Manager (acceso a Redis)  
**No es singleton** — se instancia por número de cliente en cada request de registro.

## Responsabilidad

Gestiona el estado conversacional de un usuario durante el flujo de registro: lee, valida, persiste y elimina su estado en Redis. **No decide lógica de negocio** — eso lo hace el controller. Su aportación específica es validar que la transición de estado sea legal antes de persistir.

Lo que **no hace**: capturar errores propios, notificar al usuario, ni coordinar pasos del flujo.

## Dependencias directas

| Dependencia | Qué aporta |
|---|---|
| `managers/gestor_redis.py` (`RedisManager`) | Operaciones `get`, `set`, `delete` sobre Redis — recibido por inyección |
| `states.py` | `EstadoRegistro` (enum de estados) y `transicion_valida_registro` (grafo de transiciones) |
| `tenacity` | Reintentos en operaciones de lectura y escritura Redis |

## Métodos

### `obtener_estado() → dict`

Lee la clave `<numero_cliente>` de Redis y deserializa el JSON.

- Si la clave no existe devuelve `{"estado": EstadoRegistro.SALUDO_INICIAL}` — estado por defecto para usuarios nuevos.
- Si Redis falla o el JSON está corrupto lanza excepción (el controller no la captura — burbujea al blueprint).
- **`@retry`:** 3 intentos, 2s entre ellos.
- **Usado por:** `controllers/registro.py:131` — una sola lectura al inicio de `manejar_registro`; el dict se reutiliza en todo el flujo sin releer Redis.

---

### `actualizar_estado(nuevo_estado, datos_adicionales=None)`

Valida la transición y persiste el nuevo estado.

1. Lee el estado actual con `obtener_estado()`.
2. Consulta `transicion_valida_registro(estado_origen, nuevo_estado)`.
3. Si la transición no es válida lanza `ValueError` — **el controller no captura este error**, por lo que burbujea al blueprint. En producción no debería ocurrir si el controller sigue las transiciones del grafo.
4. Actualiza el dict en memoria con `datos_adicionales` si se proveen (p. ej. `{"nombre": ...}` o `{"direccion": ...}`).
5. Delega en `_persistir_estado`.

**Transiciones válidas** (según `states.py`):

```
SALUDO_INICIAL → ESPERANDO_CONFIRMACION
ESPERANDO_CONFIRMACION → ESPERANDO_NOMBRE
ESPERANDO_NOMBRE → ESPERANDO_DIRECCION
ESPERANDO_DIRECCION → CONFIRMANDO_DIRECCION
CONFIRMANDO_DIRECCION → ESPERANDO_DIRECCION  ← rollback si el usuario corrige la dirección
```

**Usado por:** `controllers/registro.py` en seis puntos del flujo (líneas 136, 142, 153, 165, 188 y la transición de `CONFIRMANDO_DIRECCION → ESPERANDO_DIRECCION`).

---

### `_persistir_estado(estado: dict)` *(privado)*

Serializa el dict a JSON y lo escribe en Redis con TTL de 3600s.

- **`@retry`:** 3 intentos, 2s entre ellos.
- Si agota los reintentos lanza excepción que burbujea desde `actualizar_estado`.
- No llamar directamente — solo la invoca `actualizar_estado`.

---

### `eliminar_estado() → int`

Borra la clave `<numero_cliente>` de Redis. Sin retry.

Devuelve el resultado de `redismanager.delete` (1 si existía, 0 si no).

**Usado por** `controllers/registro.py` en tres contextos:
- Línea 60 — estado Redis corrupto (campos faltantes): reinicia al usuario.
- Línea 101 — usuario ya registrado (duplicado o recuperación): limpia estado fantasma.
- Línea 125 — registro completado correctamente: limpia el estado tras alta exitosa.
- Línea 146 — usuario cancela el registro en `ESPERANDO_CONFIRMACION`.

## Clave Redis

| Patrón | TTL | Formato del valor |
|---|---|---|
| `<numero_cliente>` | 3600s (1 hora) | JSON: `{"estado": "...", "nombre"?: "...", "direccion"?: "..."}` |

Los campos `nombre` y `direccion` se añaden al dict progresivamente conforme avanza el flujo — no están presentes en los estados iniciales.

## Contrato con su consumidor

**Único consumidor:** `controllers/registro.py` → clase `RegistroUsuario`.

| Situación | Qué lanza `EstadoUsuario` | Quién captura |
|---|---|---|
| Redis caído (lecturas) | `Exception` tras 3 reintentos | Nadie en el controller → burbujea al blueprint |
| Redis caído (escrituras) | `Exception` tras 3 reintentos | Nadie en el controller → burbujea al blueprint |
| JSON corrupto | `Exception` | Nadie en el controller → burbujea al blueprint |
| Transición inválida | `ValueError` | Nadie en el controller → burbujea al blueprint |

El controller gestiona sus propias excepciones de negocio (BD, mapas), pero no envuelve las llamadas a `EstadoUsuario` en try/except — delega el manejo de fallos Redis al retry de tenacity y a la capa superior (blueprint) si se agota.

## Notas de diseño

- `actualizar_estado` re-lee Redis antes de persistir. Esto garantiza que la validación de transición usa el estado más reciente aunque haya habido otra escritura concurrente — el retry en la lectura ya protege frente a fallos transitorios.
- El retry está en `obtener_estado` y `_persistir_estado`, no en `actualizar_estado` ni `eliminar_estado`. No hace falta: `actualizar_estado` hereda el retry de sus llamadas internas; `eliminar_estado` se usa en contextos donde un fallo es tolerable (la clave se limpia en el próximo ciclo o el TTL lo resuelve).
- El `ValueError` por transición inválida funciona como guardia de desarrollo. Si el grafo de `states.py` y el controller están sincronizados, nunca se dispara en producción.
