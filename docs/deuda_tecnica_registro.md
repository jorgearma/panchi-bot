# Deuda técnica — `controllers/registro.py`

Revisión del flujo de registro tras los fixes 1-5. Cada ítem lista archivo:línea de referencia al estado actual del código.

---

## Bugs reales

### B1. `"no"` se acepta como nombre válido en `ESPERANDO_NOMBRE`
**Dónde:** `controllers/registro.py:50-55` (`_es_nombre_valido`) y `controllers/registro.py:225-236` (rama `ESPERANDO_NOMBRE`).

Un usuario que escriba `"no"` intentando rechazar queda registrado con nombre `"no"`:
- `_es_nombre_valido("no")` → `len == 2 ≥ 2` ✓ → regex `[A-Za-z...]+` matchea → `True`.

Lo mismo con `"si"`, `"sí"`, `"ok"`, `"ed"`, etc. El comando `cancelar` sí funciona (guard superior), pero las respuestas negativas cortas no.

**Impacto:** usuarios reales quedan con nombres basura en BD.

**Propuesta:** en `_es_nombre_valido`, rechazar si el normalizado pertenece a `RESPUESTAS_POSITIVAS ∪ RESPUESTAS_NEGATIVAS`.

---

### B2. `REGISTRO_FALLIDO_GUARDAR` deja al usuario en silencio
**Dónde:** `controllers/registro.py:171-175`.

```python
try:
    usuario_id = gestor_usuarios.guardar_usuario(...)
except Exception as e:
    logger.error("REGISTRO_FALLIDO_GUARDAR ...")
    return "Error en registro", 200  # ← sin mensaje al usuario
```

Si `guardar_usuario` lanza, se loguea y se retorna 200, pero **nunca se envía mensaje al usuario**. El usuario dijo `"sí"`, no recibe nada, no sabe si funcionó o no. Comparar con `ERROR_BD_CONFIRMACION` (línea 136-140) y `RECUPERACION_FALLIDA` (línea 153-160) que sí avisan. Inconsistencia con impacto real.

**Propuesta:** enviar `enviar_mensaje_whatsapp("Ha ocurrido un problema técnico con tu registro. Por favor, inténtalo de nuevo.", self.numero_cliente)` antes del return.

---

### B3. Orden "mensaje-antes-de-persistir-estado" inconsistente
**Dónde:**
- `controllers/registro.py:89-93` (dirección validada)
- `controllers/registro.py:207-210` (SALUDO_INICIAL)
- `controllers/registro.py:213-216` (ESPERANDO_CONFIRMACION → nombre)

En las tres ramas se **envía el mensaje WhatsApp antes de persistir el estado en Redis**. Si `actualizar_estado` falla (el `@retry` de `managers/estado_usuario.py:61-67` puede agotarse tras 3 intentos), el usuario ya recibió el mensaje pero el estado no avanzó → su siguiente respuesta cae en la rama incorrecta.

Caso opuesto correcto: `controllers/registro.py:228-232` (ESPERANDO_NOMBRE → ESPERANDO_DIRECCION) actualiza primero y envía después.

**Impacto:** raro en producción (Redis es estable), pero el patrón inconsistente invita a errores al leer el código.

**Propuesta:** unificar a "actualizar_estado primero, enviar mensaje después". Si el envío WhatsApp falla, Meta reintenta y el estado ya es consistente.

---

## Seguridad / GDPR

### S1. PII en logs
**Dónde:**
- `controllers/registro.py:96-99` — `logger.info("DIRECCION_INVALIDA ... input=%r", mensaje)` → dirección completa.
- `controllers/registro.py:234` — `logger.info("NOMBRE_INVALIDO ... input=%r", mensaje)` → nombre.
- `controllers/registro.py:242` — `logger.debug("data redis: %s", estado_data)` → **nombre + dirección + estado completo** al log.

El `logger.debug` de línea 242 es el más grave:
1. Si DEBUG se activa en producción, es leak directo de PII.
2. Sólo se emite en la rama `CONFIRMANDO_DIRECCION` → inconsistente.
3. No aporta valor diagnóstico real (la información ya está en los otros logs).

**Impacto:** riesgo GDPR si los logs se comparten con terceros (Sentry, Datadog…).

**Propuesta:**
- Eliminar la línea 242 completa.
- En `NOMBRE_INVALIDO` y `DIRECCION_INVALIDA`, loguear sólo longitud y/o hash truncado en vez del `input=%r`: ej. `input_len=%d`.

---

### S2. Dirección sin límite de longitud antes de persistir a Redis
**Dónde:** `controllers/registro.py:238-239` → `_procesar_direccion` → `actualizar_estado(..., {"direccion": direccion_resultante})`.

El nombre se limita a 60 caracteres (`_es_nombre_valido`). La dirección **no tiene límite explícito** antes de llegar a `validar_direccion`. Un mensaje de 10 KB se persiste en Redis bajo la clave `<phone>`. Multiplicado por N usuarios maliciosos → consumo de memoria.

Mitigación actual: `maps_module.validar_direccion` probablemente rechaza textos largos, pero dependemos de un contrato no verificado en este archivo.

**Propuesta:** guard de defensa en profundidad al inicio de `_procesar_direccion`:

```python
if len(mensaje_cliente) > 200:
    _enviar_direccion_invalida(self.numero_cliente, None, None)
    return "Dirección demasiado larga", 200
```

---

## Inconsistencias menores

### I1. `_parece_direccion` demasiado laxa
**Dónde:** `controllers/registro.py:58-60`.

```python
def _parece_direccion(mensaje):
    return bool(re.search(r"\d", mensaje or ""))
```

Cualquier texto con un dígito se considera dirección. Ejemplos que disparan falso positivo:
- `"no tengo 2 casas"` → re-ejecuta validación → "inválida" → confunde al usuario.
- `"1"` solo → mismo problema.

**Impacto:** edge cases raros, UX degradada sólo cuando ocurren.

**Propuesta:** regla más robusta — dígito **Y** (al menos una palabra ≥ 4 letras **O** empieza por `calle|avenida|avda|c/|plaza|paseo|carretera`).

---

### I2. `RESPUESTAS_POSITIVAS` mezcla contextos
**Dónde:** `controllers/registro.py:24-28`.

Palabras como `"correcto"`, `"exacto"` son naturales en `CONFIRMANDO_DIRECCION` pero raras en `ESPERANDO_CONFIRMACION` (nadie responde `"exacto"` a `"¿quieres registrarte?"`). No es un bug, sólo ruido semántico en el set unificado.

**Valoración:** aceptable. Separar en dos sets añade complejidad sin beneficio real.

---

### I3. `except Exception` genérico en múltiples puntos
**Dónde:**
- `controllers/registro.py:80` (`validar_direccion`)
- `controllers/registro.py:104` (`sugerir_calle`)
- `controllers/registro.py:135` (`obtener_usuario_completo`)
- `controllers/registro.py:173` (`guardar_usuario`)
- `controllers/registro.py:179` (`iniciar_pedido`)

Captura demasiado amplia: enmascara `AssertionError` en tests y cualquier bug de programación.

**Valoración:** trade-off aceptable dado que es un endpoint de bot que no puede caer. Considerar estrechar a `(SQLAlchemyError, OperationalError, RetryError, requests.RequestException)` en una iteración futura.

---

## Temas verificados que NO son bugs

- **Race "doble sí" de Meta retry:** cubierto por `redismanager.bloquear_usuario(duracion=4)` en `services/inbound_whatsapp.py:120` y por el enrutamiento posterior a `ManejadorMensajesRegistrados` tras el alta.
- **`_normalizar` con `.strip(chars)` bidireccional:** funciona correctamente para los casos de uso (`"¿sí?"` → `"sí"`, `"Sí."` → `"sí"`, `"VALE!!"` → `"vale"`).
- **Comparación `estado_actual == EstadoRegistro.X`:** funciona porque `EstadoRegistro(str, Enum)` hace al enum comparable con strings.
- **Import diferido de `container` en `_confirmar_direccion`** (`controllers/registro.py:115`): evita circular import, coste trivial (Python cachea módulos).
- **Rama de "recuperación" por usuario parcial en `_confirmar_direccion:142-168`:** en la práctica casi nunca se activa porque `services/inbound_whatsapp.py:140-142` enruta a `mensajes_registrados` cuando el usuario ya está en DB. Se mantiene como red de seguridad para carreras raras. No es código muerto en el sentido estricto.

---

## Recomendación de priorización

| Ítem | Gravedad | Esfuerzo | Prioridad |
|------|----------|----------|-----------|
| B1   | Alta (datos corruptos en BD) | Bajo | **1** |
| B2   | Media (UX rota en fallo) | Bajo | **2** |
| S1   | Media (GDPR) | Bajo | **3** |
| S2   | Baja (mitigado externamente) | Bajo | **4** |
| B3   | Baja (raro en prod) | Medio | 5 |
| I1   | Muy baja (edge case) | Bajo | 6 |
| I2   | Cosmético | — | — |
| I3   | Cosmético | Medio | — |
