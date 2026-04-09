# Auditoría de `blueprints/empleado.py`

> Auditoría técnica estricta. Fecha: 2026-04-07.
> Archivos analizados: `blueprints/empleado.py`, `blueprints/auth.py` (líneas 60–95), `managers/gestor_empleado.py`.

---

## 1. Rol del archivo

**Responsabilidad principal:** Routing HTTP para el hub de empleado — check-in, fichaje, cambio de rol, métricas y turnos.
**Qué debería hacer:** Validar entrada, llamar a `gestor_empleado`, devolver respuesta HTTP.
**Qué no debería hacer:** Tomar decisiones de negocio (p.ej. "si polivalente y sin rol, redirigir"), ni gestionar estado de sesión relacionado con roles.
**Dependencias clave:** `gestor_empleado` (container singleton), `requiere_rol`/`requiere_autenticacion` (auth), `app_config.APP_MODE`.
**Nivel de criticidad:** Medio

---

## 2. Lo que hace bien

- Routing limpio: cada ruta hace exactamente una cosa, sin lógica anidada profunda.
- Validación de presencia de campos en las rutas POST que la necesitan (`estado`, `cambiar_rol`, líneas 54 y 135).
- `fichaje_iniciar` maneja explícitamente `ValueError('ya_abierto')` con 409 (línea 186–187), evitando procesamiento doble visible al cliente.
- `fichaje_cerrar` distingue `no_abierto` de errores genéricos (línea 203–204).
- `turnos_datos` valida los query params ISO con try/except y fallback razonable (líneas 241–245).
- Todos los paths de error relevantes usan `logger.error` con el mensaje de la excepción.
- `requiere_rol` cubre todas las rutas operativas; `checkin` usa `requiere_autenticacion` de forma deliberada (correcto, es el paso previo a asignar rol).

---

## 3. Hallazgos

### Hallazgo 1

**Tipo:** observabilidad / errores
**Severidad:** Media

**Problema:** Excepción completamente silenciada en `index()`.
**Evidencia:**
```python
# línea 27–28
except Exception:
    pass  # Si falla la BD, mostrar el hub igualmente
```
**Impacto real:** Cualquier fallo de base de datos durante la comprobación de polivalente queda invisible. Un empleado polivalente sin rol activo verá el hub en lugar del check-in, y nadie sabrá que la BD falló.
**Recomendación mínima concreta:**
```python
except Exception as e:
    logger.warning("No se pudo verificar rol activo para empleado_id=%s: %s", empleado_id, e)
```

---

### Hallazgo 2

**Tipo:** errores
**Severidad:** Media

**Problema:** `capacidades()` devuelve HTTP 200 en el path de error.
**Evidencia:**
```python
# línea 113–114
except Exception as e:
    logger.error("Error en /empleado/capacidades: %s", e)
    return jsonify({'capacidades': [], 'rol_activo': None})   # sin código de estado → 200
```
**Impacto real:** El cliente no puede distinguir "este empleado no tiene capacidades" de "hubo un error de BD". Un frontend que confíe en la respuesta podría ocultar capacidades reales o permitir un check-in incompleto.
**Recomendación mínima concreta:** Añadir `, 500` al return del except, o devolver `{'error': 'Error interno'}` con 500 en lugar de datos vacíos.

---

### Hallazgo 3

**Tipo:** diseño / responsabilidad única
**Severidad:** Baja

**Problema:** Lógica de redirección de polivalente vive en el blueprint.
**Evidencia:**
```python
# líneas 25–26
if gestor_empleado.es_polivalente(empleado_id) and not gestor_empleado.tiene_rol_activo(empleado_id):
    return redirect('/empleado/checkin')
```
**Impacto real:** Dos llamadas a la BD en la ruta de la página principal del hub; la regla "polivalente sin rol → checkin" está en el blueprint en vez de en el manager. Si la lógica cambia habrá que buscarla aquí.
**Recomendación mínima concreta:** Añadir un método `gestor_empleado.necesita_checkin(empleado_id) → bool` que encapsule los dos predicados y reduzca la exposición al blueprint.

---

### Hallazgo 4

**Tipo:** errores / rendimiento
**Severidad:** Baja

**Problema:** `fichaje_iniciar` accede a `puede_result['turno_id']` sin comprobar que la clave exista.
**Evidencia:**
```python
# línea 182
check_in = gestor_empleado.iniciar_turno(empleado_id, turno_id=puede_result['turno_id'])
```
**Impacto real:** Si `puede_result` no incluye `turno_id` (p.ej. cuando `puede=True` pero el turno es libre/sin programar), se lanza `KeyError` que cae al `except Exception` de línea 189 y devuelve un 500 genérico, ocultando el origen real.
**Recomendación mínima concreta:**
```python
turno_id = puede_result.get('turno_id')
check_in = gestor_empleado.iniciar_turno(empleado_id, turno_id=turno_id)
```
O garantizar contractualmente que `puede_result` siempre incluye `turno_id` cuando `puede=True`.

---

### Hallazgo 5

**Tipo:** rendimiento
**Severidad:** Baja

**Problema:** `capacidades()` hace dos llamadas separadas a la BD para datos relacionados.
**Evidencia:**
```python
# líneas 110–111
caps = gestor_empleado.capacidades(empleado_id)
rol_activo = gestor_empleado.obtener_rol_activo(empleado_id)
```
**Impacto real:** Dos round-trips a SQL Server para una sola respuesta JSON. Menor, pero innecesario.
**Recomendación mínima concreta:** Un método `gestor_empleado.capacidades_con_rol_activo(empleado_id)` que devuelva ambos en una sola operación.

---

### Hallazgo 6

**Tipo:** observabilidad
**Severidad:** Baja

**Problema:** El log de error de `checkin` no incluye `empleado_id`.
**Evidencia:**
```python
# línea 169
logger.error("Error en /empleado/checkin: %s", e)
```
**Impacto real:** En producción, sin `empleado_id` en el log es difícil reproducir el problema o asociarlo a un usuario concreto.
**Recomendación mínima concreta:**
```python
logger.error("Error en /empleado/checkin empleado_id=%s: %s", empleado_id, e)
```

---

### Hallazgo 7

**Tipo:** diseño
**Severidad:** Baja

**Problema:** `cambiar_rol` modifica `session['rol']` directamente en el blueprint.
**Evidencia:**
```python
# línea 146
session['rol'] = nuevo_rol
```
**Impacto real:** El estado de autenticación (sesión) se modifica fuera de la capa de auth. Si en el futuro `requiere_rol` necesita más que `session['rol']`, habrá que buscar todos los sitios que lo modifican directamente.
**Recomendación mínima concreta:** Posible riesgo no confirmado sobre si hay otros blueprints que modifican `session['rol']` directamente — si es un patrón extendido, no tiene prioridad. Si es el único caso, valorar moverlo a un helper en `auth.py`.

---

## 4. Riesgos principales si no se toca

| Riesgo | Escenario concreto |
|--------|-------------------|
| BD falla en `index()` sin log | Un empleado polivalente no es redirigido al check-in; el fallo pasa desapercibido en producción hasta que alguien lo reporta manualmente |
| `capacidades()` devuelve 200 vacío en error | El frontend del check-in muestra "sin capacidades", el empleado no puede elegir rol; no hay alerta de error |
| `KeyError` en `fichaje_iniciar` | Un 500 genérico sin contexto en logs cuando el contrato del dict `puede_result` se rompa |

---

## 5. Refactor mínimo recomendado

### Qué tocar primero (en orden de impacto)

1. **Hallazgo 1** — añadir `logger.warning` en el `except` silencioso de `index()` (1 línea).
2. **Hallazgo 2** — añadir `, 500` al return del except en `capacidades()` (1 carácter).
3. **Hallazgo 4** — usar `.get('turno_id')` en `fichaje_iniciar` (1 línea).
4. **Hallazgo 6** — añadir `empleado_id` al log de `checkin` (1 línea).

### Qué NO tocar todavía

- La doble llamada a BD en `capacidades()` y `checkin()` (Hallazgos 3 y 5) — requiere cambios en el manager y no tienen impacto operativo inmediato.
- La gestión de `session['rol']` (Hallazgo 7) — cambio de patrón con bajo retorno.

---

## 6. Tests que deberían existir

- `test_index_redirige_a_checkin_si_polivalente_sin_rol` — GET `/empleado` con empleado polivalente y sin rol activo → 302 a `/empleado/checkin`.
- `test_index_muestra_hub_si_bd_falla` — GET `/empleado` cuando `es_polivalente` lanza excepción → 200 (no 500).
- `test_capacidades_devuelve_500_si_falla_bd` — GET `/empleado/capacidades` con manager lanzando excepción → 500 (actualmente devolvería 200).
- `test_fichaje_iniciar_ya_abierto` — POST `/empleado/fichaje` cuando ya hay turno abierto → 409.
- `test_fichaje_iniciar_sin_puede` — POST `/empleado/fichaje` cuando `puede=False` → 403 con `razon`.
- `test_cambiar_rol_con_bloqueantes` — POST `/empleado/cambiar-rol` con `bloqueantes` no vacíos → 409 con `pedidos_activos`.
- `test_turnos_datos_fecha_invalida` — GET `/empleado/turnos/datos?desde=notadate` → fallback a rango de 14 días sin error.

---

## 7. Veredicto final

**Estado general del archivo:** Bien estructurado para ser un blueprint. Respeta la separación de capas en la mayoría de rutas. Los problemas son localizados y de fácil corrección.
**¿Bloquea crecimiento?** No.
**¿Bloquea testeo?** No — `gestor_empleado` es un singleton inyectable y mockeable.
**¿Tiene riesgo operativo real?** Bajo. El riesgo más concreto es el `pass` silencioso en `index()` que puede ocultar fallos de BD en producción, y `capacidades()` retornando 200 en error que puede confundir al cliente.
