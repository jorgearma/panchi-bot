# Auditoría de `managers/dashboard/gestor_turnos_mixin.py`

> Auditoría técnica estricta. Fecha: 2026-04-08.
> Archivos analizados: `managers/dashboard/gestor_turnos_mixin.py`, `managers/empleado/turnos_mixin.py`, `managers/dashboard/_base.py`, `managers/gestor_dashboard.py`.

---

## 1. Rol del archivo

**Responsabilidad principal:** Actualmente, ninguna. El archivo contiene solo un comentario de redirección de una línea.

**Qué debería hacer (histórico):** Servía como punto de entrada para la lógica de gestión de turnos (consulta, creación, edición, cancelación, historial de check-ins) dentro del mixin de dashboard.

**Qué no debería hacer:** Su estado actual es correcto como marcador de migración, pero el comentario no es accionable ni verificable automáticamente.

**Dependencias clave:** Ninguna — el archivo tiene una única línea que es un comentario docstring.

**Nivel de criticidad:** Bajo como archivo individual. La lógica que antes vivía aquí ahora está en `managers/empleado/turnos_mixin.py`, que tiene criticidad Alta (gestiona fichajes, horarios y disponibilidad operativa de empleados).

---

## 2. Lo que hace bien

- **Migración completada:** La lógica de turnos fue correctamente extraída a `managers/empleado/turnos_mixin.py`, que sí forma parte del assembler `GestorEmpleado`. El mixin de dashboard no necesita duplicar esta lógica.
- **El archivo no exporta nada roto:** No hay importaciones fallidas, clases vacías con métodos stub, ni referencias a módulos inexistentes.

---

## 3. Hallazgos

### Hallazgo 1

**Tipo:** diseño
**Severidad:** Media

**Problema:** El archivo existe como un stub de una línea con un comentario de redirección. No hay ningún mecanismo que garantice que el comentario sea correcto (la clase referenciada podría haberse renombrado o eliminado), ni ningún test que verifique que `GestorDashboard` no expone una API de turnos. El comentario actúa como documentación, pero es opaco para las herramientas de análisis estático y para los desarrolladores nuevos.

**Evidencia:**
```python
# línea 1 (único contenido)
"""Turno management moved to managers/empleado/turnos_mixin.GestorEmpleadoTurnosMixin."""
```

**Impacto real:** Un desarrollador nuevo que busque la gestión de turnos en `managers/dashboard/` encontrará este archivo, leerá el comentario, irá a `managers/empleado/turnos_mixin.py`, y podrá seguir correctamente. El riesgo es bajo. Sin embargo, si el archivo referenciado se renombra en el futuro, el comentario queda obsoleto sin ninguna advertencia.

**Recomendación mínima concreta:** Eliminar el archivo completamente si ningún módulo lo importa, o convertir el comentario en un assertion importable que falle en el momento de carga si la clase referenciada no existe:
```python
# Verificación de que la clase destino existe (falla en import si hay refactor roto)
from managers.empleado.turnos_mixin import GestorEmpleadoTurnosMixin  # noqa: F401
__all__ = []  # este módulo no exporta nada; lógica movida a managers/empleado/turnos_mixin.py
```
Esto convierte el comentario muerto en una dependencia verificable.

---

### Hallazgo 2

**Tipo:** diseño
**Severidad:** Baja

**Problema:** `GestorDashboard` (en `managers/gestor_dashboard.py`) **no incluye** `GestorEmpleadoTurnosMixin` ni `GestorEmpleadoTurnosMixin` en su cadena de herencia múltiple. Los métodos de turnos (`turno_hoy`, `turnos_hoy`, `crear_turno`, etc.) están disponibles a través de `GestorEmpleado`, no de `GestorDashboard`. Si el blueprint de dashboard necesita acceder a `turnos_hoy()`, debe hacerlo a través de `gestor_empleado` (del container), no de `gestor_dashboard`.

**Evidencia:**
```python
# managers/gestor_dashboard.py líneas 20-33
class GestorDashboard(
    GestorPedidosMixin,
    GestorPickingBasicoMixin,
    GestorPickingFlujoMixin,
    GestorRepartoAsignacionMixin,
    GestorRepartoTrackingMixin,
    GestorRepartoCobroMixin,
    GestorEmpleadosListaMixin,
    GestorEmpleadosMonitorMixin,
    GestorEmpleadosRendimientoMixin,
    GestorEstadisticasMixin,
    GestorDashboardBase,
):
    # GestorEmpleadoTurnosMixin NO está aquí
```

**Impacto real:** Si algún blueprint de dashboard llama `gestor_dashboard.turnos_hoy()` en vez de `gestor_empleado.turnos_hoy()`, obtendrá un `AttributeError`. No es un bug activo (el código funciona), pero es una inconsistencia arquitectural: el archivo de migración dice que la lógica está en `GestorEmpleadoTurnosMixin`, pero ese mixin no se compone en `GestorDashboard`, lo que puede confundir sobre quién expone qué.

**Recomendación mínima concreta:** Añadir un comentario explícito en `gestor_dashboard.py` indicando que los métodos de turnos se acceden via `container.gestor_empleado`, no via `gestor_dashboard`. O documentarlo en `CLAUDE.md` en la sección de "Dependency Injection".

---

### Hallazgo 3

**Tipo:** observabilidad / testabilidad
**Severidad:** Baja

**Problema (en el archivo destino `managers/empleado/turnos_mixin.py`):** `turno_hoy` (líneas 18-69) y `puede_iniciar_turno` (líneas 104-198) usan `datetime.now()` directamente (sin UTC, sin parámetro inyectable), lo que hace que sean imposibles de testear deterministamente sin monkey-patching de `datetime`. Esto es relevante para la auditoría de `gestor_turnos_mixin.py` porque el stub apunta a ese archivo como la implementación real.

**Evidencia:**
```python
# managers/empleado/turnos_mixin.py línea 27
ahora = datetime.now()  # hora local del servidor, no UTC
# línea 178
ahora = datetime.now()  # idem
```
En contraste, `gestor_pedidos_mixin.py` y `gestor_estadisticas_mixin.py` usan consistentemente `datetime.utcnow()`.

**Impacto real:** Los cálculos de ventana de fichaje (`ventana_inicio <= ahora <= fin_dt`) operan sobre hora local del servidor. Si el servidor opera en UTC (habitual en contenedores Docker) y la hora de negocio es CET/CEST (UTC+1/+2), las ventanas de fichaje estarán desfasadas 1 o 2 horas. Un turno de 09:00 a 17:00 en España sería procesable desde 06:00 UTC en verano, no desde 08:50 UTC.

**Recomendación mínima concreta:** Unificar el uso de `datetime.utcnow()` en todo el codebase, o introducir una función `now()` inyectable en `_helpers.py`. Esta corrección debe hacerse en `managers/empleado/turnos_mixin.py`, no en el stub.

---

### Hallazgo 4

**Tipo:** diseño
**Severidad:** Baja

**Problema:** `puede_iniciar_turno` (líneas 104-198 de `managers/empleado/turnos_mixin.py`) ejecuta dos queries a la DB: primero llama a `turno_hoy()` (que lanza su propia query, línea 29), y luego hace una segunda query para recuperar el mismo `Turno` por ID (línea 124). Son dos roundtrips para obtener el mismo objeto.

**Evidencia:**
```python
# managers/empleado/turnos_mixin.py líneas 113-124
turno_data = self.turno_hoy(empleado_id)  # query 1: carga turno
# ...
turno_id = turno_data['id']
turno = self.session.query(Turno).filter_by(id=turno_id).first()  # query 2: re-carga turno
```

**Impacto real:** Dos queries en lugar de una por cada petición de fichaje. Con SQL Server, cada roundtrip adicional tiene latencia de red. En un check-in de empleado (operación frecuente en hora punta), esto suma. No es crítico pero es evitable.

**Recomendación mínima concreta:** Refactorizar `puede_iniciar_turno` para que `turno_hoy` devuelva el objeto ORM (o que `puede_iniciar_turno` haga su propia query directa y no dependa de `turno_hoy`).

---

### Hallazgo 5

**Tipo:** consistencia de estado
**Severidad:** Baja

**Problema:** `editar_turno` (líneas 536-570 de `managers/empleado/turnos_mixin.py`) permite editar un turno con `estado='completado'` (solo bloquea `'cancelado'`). Un turno completado con fichajes asociados podría tener sus horas modificadas retroactivamente, desincronizando la planificación con el registro de asistencia.

**Evidencia:**
```python
# managers/empleado/turnos_mixin.py líneas 552-553
if turno.estado == 'cancelado':
    return {'ok': False, 'error': 'No se puede editar un turno cancelado'}
# No hay guard para estado='completado'
```

**Impacto real:** Un administrador podría editar las horas de un turno completado, lo que produciría inconsistencia entre el turno planificado (ahora con horas nuevas) y los check-ins registrados (con las horas originales). Podría afectar el cálculo de `minutos_tarde` en informes históricos.

**Recomendación mínima concreta:** Añadir guard para `estado='completado'`:
```python
if turno.estado in ('cancelado', 'completado'):
    return {'ok': False, 'error': f'No se puede editar un turno {turno.estado}'}
```

---

### Hallazgo 6

**Tipo:** rendimiento
**Severidad:** Baja

**Problema:** `turnos_hoy()` (líneas 202-337 de `managers/empleado/turnos_mixin.py`) carga todos los `CheckIn` del día con `s.query(CheckIn).filter(CheckIn.fecha == hoy).all()` (línea 236) sin un join previo que filtre por empleados activos. Si hay check-ins de empleados inactivos (dado de baja pero con histórico), se cargan innecesariamente.

**Evidencia:**
```python
# línea 236
for ci in s.query(CheckIn).filter(CheckIn.fecha == hoy).all():
```
Mientras que los empleados sí se filtran por `activo=True` (línea 229), los check-ins se cargan sin ese filtro.

**Impacto real:** Menor. En la práctica, los check-ins de empleados inactivos son pocos o ninguno para el día actual. No es un riesgo operativo.

**Recomendación mínima concreta:** Añadir un join o subquery: `CheckIn.empleado_id.in_([e.EmpleadoID for e in empleados])`. Dado que `empleados` ya está cargado en memoria, el filtro puede aplicarse en Python sin query adicional.

---

## 4. Riesgos principales si no se toca

| Riesgo | Escenario concreto |
|--------|-------------------|
| Desfase UTC/local en ventanas de fichaje | El servidor corre en Docker con TZ=UTC; los empleados intentan fichar a las 09:00 hora española (07:00 UTC en verano); el sistema rechaza el fichaje porque "están fuera de la ventana". |
| Edición de turno completado | Un administrador corrige las horas de un turno del día anterior; los registros de CheckIn quedan con referencias a un turno con horas distintas; los informes de puntualidad son incorrectos. |
| Archivo stub con referencia muerta | Un refactor renombra `GestorEmpleadoTurnosMixin`; el comentario en el stub queda obsoleto; el siguiente desarrollador pierde tiempo buscando una clase que no existe con ese nombre. |

---

## 5. Refactor mínimo recomendado

### Qué tocar primero (en orden de impacto)
1. **Unificar `datetime.now()` a `datetime.utcnow()`** en `managers/empleado/turnos_mixin.py` (Hallazgo 3) — impacto operativo real si el servidor corre en UTC.
2. **Añadir guard `estado='completado'` en `editar_turno`** (Hallazgo 5) — 1 línea, previene inconsistencia de datos.
3. **Convertir el stub en un import verificable** (Hallazgo 1) — hace el comentario de migración robusto ante futuros refactors.

### Qué NO tocar todavía
- La arquitectura de dos queries en `puede_iniciar_turno` (Hallazgo 4): baja prioridad, el impacto de latencia es menor.
- La carga de CheckIns sin filtro de empleados activos (Hallazgo 6): riesgo prácticamente nulo en el día a día.
- La separación entre `GestorDashboard` y `GestorEmpleado` (Hallazgo 2): es la arquitectura correcta, solo falta documentación.

---

## 6. Tests que deberían existir

Tests para el stub (`managers/dashboard/gestor_turnos_mixin.py`):
- `test_gestor_turnos_mixin_stub_apunta_a_clase_existente` — importa `GestorEmpleadoTurnosMixin` y verifica que la clase existe y tiene los métodos esperados (`turnos_hoy`, `crear_turno`, `cancelar_turno`).

Tests para la implementación real (`managers/empleado/turnos_mixin.py`):
- `test_turno_hoy_sin_turnos_devuelve_none` — empleado sin turnos planificados → `None`.
- `test_turno_hoy_fuera_ventana_devuelve_proximo` — turno a las 14:00, llamada a las 10:00 → devuelve el turno futuro.
- `test_puede_iniciar_turno_con_checkin_abierto` — empleado con CheckIn sin `fin` → `puede=False`.
- `test_puede_iniciar_turno_fuera_ventana` — llamada antes de la ventana de fichaje → `puede=False` con mensaje de horario.
- `test_crear_turno_solapamiento_detectado` — intentar crear turno que solapa con uno existente → `ok=False` con mensaje.
- `test_editar_turno_completado_bloqueado` — editar turno con `estado='completado'` → `ok=False` (test que falla actualmente, documenta el bug).
- `test_cancelar_turno_ya_cancelado` — cancelar un turno ya cancelado → `ok=False`.
- `test_eliminar_turno_con_checkins_bloqueado` — turno con CheckIns asociados no puede eliminarse → `ok=False`.
- `test_turnos_hoy_resumen_n_con_checkin` — verifica que `resumen.con_checkin` cuenta correctamente los empleados con CheckIn abierto.
- `test_turnos_historial_paginacion` — verifica `total`, `page`, `pages` correctos con datos.

---

## 7. Veredicto final

**Estado general del archivo (`managers/dashboard/gestor_turnos_mixin.py`):** El stub es inocuo pero inútil en su forma actual. La migración de la lógica a `managers/empleado/turnos_mixin.py` es estructuralmente correcta.

**Estado general de la implementación real (`managers/empleado/turnos_mixin.py`):** Sólida en estructura general (manejo de errores con try/except en CRUD, logging de operaciones, guards de idempotencia). Los riesgos identificados son concretos pero de severidad baja-media, siendo el desfase UTC/local el de mayor impacto operativo potencial.

**¿Bloquea crecimiento?** No. La estructura de mixin en `managers/empleado/` es extensible.

**¿Bloquea testeo?** Sí, parcialmente. El uso de `datetime.now()` sin posibilidad de inyección hace que los tests de ventana de fichaje requieran monkey-patching de `datetime`, lo cual es frágil.

**¿Tiene riesgo operativo real?** Sí, uno concreto: el desfase UTC/local en `datetime.now()` puede hacer que los empleados no puedan fichar si el servidor corre en UTC (configuración estándar de Docker). Este riesgo debe verificarse contra la configuración de TZ del entorno de producción antes de descartar.
