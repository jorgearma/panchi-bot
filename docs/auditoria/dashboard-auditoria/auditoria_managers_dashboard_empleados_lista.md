# Auditoría de `managers/dashboard/empleados_lista.py`

> Auditoría técnica estricta. Fecha: 2026-04-08.
> Archivos analizados: `managers/dashboard/empleados_lista.py`, `models.py` (clases `Empleado`, `Rol`, `Turno`, `CheckIn`).

---

## 1. Rol del archivo

**Responsabilidad principal:** Proporcionar el listado de empleados activos con información de presencia (check-in) para la asignación operativa y la creación de turnos.

**Qué debería hacer:** Consultar `Empleado`, `Turno` y `CheckIn` en DB y devolver una lista serializada lista para consumir por un controller o blueprint.

**Qué no debería hacer:** Transformar negocio (decidir quién _puede_ ser asignado a una tarea), mezclar zonas horarias de forma inconsistente, devolver datos de empleados sin acotar el alcance del eager-load.

**Dependencias clave:** `models.Empleado`, `models.Rol`, `models.Turno`, `models.CheckIn`, `self.session` (inyectado por el assembler).

**Nivel de criticidad:** Medio — alimenta la pantalla de asignación de repartidores y pickers. Un bug produce asignaciones incorrectas o ausencia de empleados en el listado.

---

## 2. Lo que hace bien

- **Eager-load selectivo** (línea 24): `joinedload(Empleado.rol)` evita N+1 al acceder a `e.rol.nombre` en el bucle del listado.
- **Filtro por estado activo** (línea 24): `Empleado.activo == True` correctamente aplicado antes de cualquier join adicional.
- **Separación por flag** (líneas 26–31): `solo_con_turno` como parámetro booleano permite reusar la misma función para dos casos de uso distintos sin duplicar código.
- **Consulta única de check-ins** (líneas 39–50): se recogen todos los check-ins en una sola query con `IN` en lugar de hacer una query por empleado.
- **Fallback de rol** (línea 57): `e.rol.nombre if e.rol else e.Puesto` tolera empleados con `rol_id` NULL (campo legacy documentado en `models.py`).
- **Docstring con semántica de los flags** (líneas 16–22): explica con claridad cuándo usar cada modo.

---

## 3. Hallazgos

### Hallazgo 1

**Tipo:** consistencia  
**Severidad:** Media

**Problema:** Se usan dos referencias temporales distintas para "hoy": `date.today()` (hora local del servidor, línea 23) para el filtro de turnos, y `datetime.utcnow().date()` (UTC, línea 42) para el filtro de check-ins. Si el servidor está en `Europe/Madrid` (UTC+1 en invierno, UTC+2 en verano), el filtro de turnos y el de check-ins pueden apuntar a días calendario diferentes, especialmente a primera hora de la madrugada.

**Evidencia:**
```python
# línea 23
hoy = date.today()                     # hora local

# línea 42
hoy_utc = datetime.utcnow().date()    # UTC
```

**Impacto real:** Entre medianoche UTC y las 01:00–02:00 hora española, `date.today()` y `datetime.utcnow().date()` devuelven días distintos. Los empleados que fichan correctamente pueden aparecer como `has_checked_in: False` en ese intervalo, generando reasignaciones incorrectas en el dashboard.

**Recomendación mínima concreta:** Unificar a UTC en todo el método. Reemplazar `hoy = date.today()` por `hoy = datetime.utcnow().date()` en línea 23, y eliminar la variable `hoy_utc` de línea 42 usando directamente `hoy`.

---

### Hallazgo 2

**Tipo:** rendimiento  
**Severidad:** Baja

**Problema:** Cuando `solo_con_turno=False` y `rol` no es None, se hace un join implícito a `Rol` para filtrar por nombre (líneas 33–34), pero el `joinedload(Empleado.rol)` de la línea 24 ya cargó la relación en memoria. El join de filtro (línea 34) es un join SQL adicional que genera una segunda lectura de la tabla `roles` en la misma consulta, aunque SQLAlchemy los resuelve en un solo SQL. El problema real es que el `joinedload` del inicio y el `join` de filtro pueden generar un producto cartesiano parcial si SQLAlchemy los combina de forma subóptima (depende del driver). La práctica recomendada es usar `contains_eager` cuando ya se ha hecho join, o filtrar por `Empleado.rol_id` si se dispone del ID.

**Evidencia:**
```python
# línea 24: carga la relación como LEFT OUTER JOIN via joinedload
query = self.session.query(Empleado).options(joinedload(Empleado.rol)).filter(...)

# líneas 33-34: añade otro JOIN a roles para filtrar
query = query.join(Rol, Empleado.rol_id == Rol.id).filter(Rol.nombre == rol)
```

**Impacto real:** Bajo en producción con pocos empleados (<100). Puede generar resultados duplicados en versiones antiguas de SQLAlchemy si el ORM une el `joinedload` JOIN con el join de filtro.

**Recomendación mínima concreta:** Reemplazar el join de filtro por una subquery o usar `Empleado.rol_id == <id>` (requiere resolver el ID previamente). Alternativa más simple: aplicar `.filter(Empleado.rol.has(Rol.nombre == rol))` que SQLAlchemy traduce como EXISTS sin join adicional.

---

### Hallazgo 3

**Tipo:** validación de inputs  
**Severidad:** Baja

**Problema:** El parámetro `rol` (línea 15) es un string libre. No se valida contra los valores permitidos ('picker', 'repartidor', etc.) antes de construir la query. Un valor arbitrario no causará inyección SQL (SQLAlchemy usa parámetros), pero retornará silenciosamente una lista vacía en lugar de comunicar un error al llamador.

**Evidencia:**
```python
# línea 15 — sin validación
def empleados_disponibles(self, rol: str = None, solo_con_turno: bool = False) -> list:
```

**Impacto real:** Si el controller o blueprint pasa un valor de `rol` incorrecto (por typo o bug), el método devuelve `[]` sin advertencia. El dashboard mostraría "sin empleados disponibles" en lugar de reportar el error, dificultando el diagnóstico.

**Recomendación mínima concreta:** Agregar al inicio del método:
```python
_ROLES_VALIDOS = {'picker', 'repartidor', 'admin', 'supervisor'}
if rol and rol not in _ROLES_VALIDOS:
    logger.warning("empleados_disponibles: rol desconocido '%s'", rol)
```
No es necesario lanzar excepción; el warning basta para observabilidad.

---

### Hallazgo 4

**Tipo:** observabilidad  
**Severidad:** Baja

**Problema:** No hay ningún `logger.info` o `logger.debug` cuando la función devuelve datos. El logger se importa (línea 10) pero nunca se usa. Si la función devuelve una lista vacía inesperadamente, no hay traza que permita distinguir entre "no hay empleados" y un bug en los filtros.

**Evidencia:**
```python
# línea 10 — importado pero sin uso en todo el archivo
logger = logging.getLogger(__name__)
```

**Impacto real:** Diagnóstico lento en incidencias operativas (ej. "el dashboard no muestra repartidores").

**Recomendación mínima concreta:** Añadir al final, antes del return:
```python
logger.debug("empleados_disponibles: rol=%s solo_con_turno=%s → %d resultados", rol, solo_con_turno, len(empleados))
```

---

### Hallazgo 5

**Tipo:** diseño  
**Severidad:** Baja

**Problema:** La lógica de check-in (líneas 39–50) está condicionada a `solo_con_turno=True`. Cuando `solo_con_turno=False`, `has_checked_in` se fija siempre a `True` (línea 58) para todos los empleados, aunque no hayan fichado. Esto puede ser intencional (para la pantalla de creación de turnos no importa el fichaje), pero el nombre del campo `has_checked_in: True` en el dict de salida es engañoso: el consumidor podría interpretar que el empleado sí ha fichado cuando simplemente no se consultó.

**Evidencia:**
```python
# línea 58
"has_checked_in": e.EmpleadoID in checked_in_ids if solo_con_turno else True,
```

**Impacto real:** Si en el futuro un blueprint consume este campo para tomar decisiones (ej. mostrar un icono de "fichado"), obtendrá `True` para todos cuando `solo_con_turno=False`, produciendo información falsa en la UI.

**Recomendación mínima concreta:** Usar `None` en lugar de `True` cuando no se comprueba el fichaje, para que el consumidor pueda distinguir "no consultado" de "sí fichado":
```python
"has_checked_in": (e.EmpleadoID in checked_in_ids) if solo_con_turno else None,
```

---

## 4. Riesgos principales si no se toca

| Riesgo | Escenario concreto |
|--------|-------------------|
| Inconsistencia de zona horaria (Hallazgo 1) | A la 01:30 AM hora española, el turno de un repartidor aparece para hoy pero su check-in se registró "ayer" en UTC; el dashboard lo muestra como no fichado y el supervisor lo reasigna innecesariamente. |
| Campo `has_checked_in: True` engañoso (Hallazgo 5) | Un developer añade lógica en el blueprint que decide mostrar "Empleado disponible" basándose en `has_checked_in`, pero obtiene `True` para todos aunque nadie haya fichado ese día. |
| Filtro de `rol` silencioso (Hallazgo 3) | Un refactor renombra el valor de rol de `'picker'` a `'preparador'`; `empleados_disponibles(rol='picker')` devuelve `[]` sin error y el panel de picking queda vacío sin alerta. |

---

## 5. Refactor mínimo recomendado

### Qué tocar primero (en orden de impacto)

1. **Unificar zona horaria** (Hallazgo 1): cambiar `date.today()` a `datetime.utcnow().date()` en línea 23. Cambio de 1 línea, sin riesgo de regresión, máximo impacto operativo.
2. **Cambiar `has_checked_in: True` a `None`** (Hallazgo 5): 1 línea, previene confusión semántica futura.
3. **Añadir warning de rol inválido** (Hallazgo 3): 2–3 líneas, sin tocar la lógica existente.
4. **Añadir log de debug al return** (Hallazgo 4): 1 línea.

### Qué NO tocar todavía

- El doble join de `Rol` (Hallazgo 2): el impacto real es despreciable con el volumen de empleados esperado. Solo optimizar si aparece en profiling.
- La estructura del dict de salida: cambiarla rompería todos los templates que lo consumen.

---

## 6. Tests que deberían existir

- `test_empleados_disponibles_sin_filtro` — verifica que devuelve todos los empleados activos cuando no se pasan filtros.
- `test_empleados_disponibles_por_rol` — verifica que el filtro `rol='picker'` solo devuelve pickers.
- `test_empleados_disponibles_solo_con_turno` — verifica que sin turno hoy el empleado no aparece.
- `test_has_checked_in_true_cuando_ficha` — verifica que `has_checked_in=True` solo cuando hay un CheckIn con `fin=None` para hoy.
- `test_has_checked_in_false_sin_checkin` — verifica `has_checked_in=False` cuando `solo_con_turno=True` y no hay CheckIn.
- `test_has_checked_in_none_sin_turno_flag` — verifica que `has_checked_in=None` (o el valor acordado) cuando `solo_con_turno=False`.
- `test_zona_horaria_consistente` — verifica que los filtros de turno y check-in usan la misma referencia de fecha (mock de `datetime.utcnow`).
- `test_rol_invalido_devuelve_lista_vacia_con_warning` — verifica el comportamiento ante un `rol` desconocido.

---

## 7. Veredicto final

**Estado general del archivo:** Sólido para su tamaño y alcance. El código es limpio, legible y sin antipatrones graves.

**¿Bloquea crecimiento?** No. La función es fácilmente extensible.

**¿Bloquea testeo?** No. Depende únicamente de `self.session` y modelos, ambos fáciles de mockear.

**¿Tiene riesgo operativo real?** Sí, uno concreto: la inconsistencia de zona horaria (Hallazgo 1) puede producir falsos negativos en el estado de fichaje durante la primera hora tras la medianoche UTC, que en España es las 01:00–02:00 AM. Si el negocio tiene turnos nocturnos, esto es un bug en producción. Si solo opera en horario diurno, el riesgo es bajo.
