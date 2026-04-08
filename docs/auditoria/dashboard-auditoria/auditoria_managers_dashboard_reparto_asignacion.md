# Auditoría de `managers/dashboard/reparto_asignacion.py`

> Auditoría técnica estricta. Fecha: 2026-04-08.
> Archivos analizados: `managers/dashboard/reparto_asignacion.py`, `managers/dashboard/_helpers.py`, `managers/dashboard/_base.py`, `states.py`, `models.py` (referenciado vía imports).

---

## 1. Rol del archivo

**Responsabilidad principal:** Acceso a datos de asignación de repartos: listar repartidores con sus cargas, consultar pedidos sin asignar, asignar un repartidor a un pedido y permitir que un repartidor reclame un pedido de forma atómica.

**Qué debería hacer:** Queries de lectura y escritura sobre `Reparto`, `Pedido`, `Empleado`, `Turno`, `CheckIn`. Garantizar que las asignaciones sean atómicas y sin duplicados. Devolver datos serializables para blueprints.

**Qué no debería hacer:** Enviar notificaciones, coordinar flujos de múltiples estados de pedido (eso es del controller), calcular métricas de negocio complejas.

**Dependencias clave:** `_base.GestorDashboardBase` (sesión, `_batch_repartos`, `_actualizar_estado_operativo`), `models.Reparto/Pedido/Empleado/Turno/CheckIn`, `states.EstadoPedido/EstadoReparto`, `managers/dashboard/_helpers._iso`.

**Nivel de criticidad:** Alto — una asignación duplicada o una race condition aquí puede causar dos repartidores para el mismo pedido.

---

## 2. Lo que hace bien

- **`reclamar_reparto` (líneas 201–263):** El update atómico con `WHERE repartidor_id IS NULL` (líneas 231–239) más el catch de `IntegrityError` (líneas 252–255) forma un mecanismo de optimistic locking correcto para la race condition de dos repartidores reclamando a la vez.
- **Batch pre-load (líneas 60–63):** Se delega a `_batch_repartos` para evitar N×2 queries dentro del loop de empleados.
- **Gestión de errores consistente:** Todas las funciones de escritura tienen `try/except SQLAlchemyError` con rollback y log estructurado (líneas 139–142, 260–263).
- **`repartos_sin_asignar` (líneas 144–199):** Cubre correctamente los dos casos: Reparto PENDIENTE sin repartidor y pedidos PREPARADO sin fila Reparto.
- **`repartidores` (líneas 17–106):** Filtros de turno activo + check-in abierto son decisiones de negocio bien contenidas en la capa de datos.

---

## 3. Hallazgos

### Hallazgo 1

**Tipo:** consistencia / seguridad  
**Severidad:** Alta

**Problema:** En `asignar_repartidor` (líneas 108–142), no existe validación de que `empleado_id` pertenezca a un repartidor (rol adecuado). Un operador podría asignar como repartidor a un empleado de cocina si ambos están activos en DB.

**Evidencia:**
```python
# línea 118
empleado = s.query(Empleado).filter_by(EmpleadoID=empleado_id, activo=True).first()
```
Solo filtra por `activo=True`. No hay comprobación de `rol` o `Puesto`.

**Impacto real:** Un empleado de cocina podría aparecer como repartidor activo, corrompiendo el estado operativo y el mapa de reparto.

**Recomendación mínima concreta:** Añadir filtro de rol en la query de empleado, o validar `empleado.rol.nombre` / `empleado.Puesto` tras la consulta y devolver `(False, "Empleado no tiene rol de repartidor")`.

---

### Hallazgo 2

**Tipo:** idempotencia / consistencia  
**Severidad:** Alta

**Problema:** En `asignar_repartidor` (líneas 122–136), cuando ya existe un `Reparto`, se sobreescribe `repartidor_id` sin verificar si el pedido ya está `EN_REPARTO` o `ENTREGADO`. Un operador puede re-asignar un pedido que ya salió a reparto, dejando al estado de `Reparto` inconsistente con el de `Pedido`.

**Evidencia:**
```python
# líneas 122-128
reparto = s.query(Reparto).filter_by(pedido_id=pedido_id).first()
if reparto:
    reparto.repartidor_id = empleado_id
    reparto.estado = EstadoReparto.ASIGNADO.value
```
El comentario en línea 124 menciona "re-asignación after a failed delivery (NO_ENTREGADO)" pero no filtra ese caso — acepta cualquier estado de reparto existente.

**Impacto real:** Si el Reparto estaba en `EN_CAMINO` o `ENTREGADO`, se resetea a `ASIGNADO` sin historial, borrando información operativa.

**Recomendación mínima concreta:** Añadir guarda explícita: solo permitir sobreescritura si `reparto.estado in (EstadoReparto.PENDIENTE.value, EstadoReparto.NO_ENTREGADO.value)`.

---

### Hallazgo 3

**Tipo:** consistencia de estado  
**Severidad:** Media

**Problema:** En `asignar_repartidor`, el commit de BD (línea 136) ocurre antes de llamar a `_actualizar_estado_operativo` (línea 137). Si `_actualizar_estado_operativo` falla silenciosamente (su thread tiene solo `logger.warning`), el `Reparto` queda en `ASIGNADO` pero el empleado sigue apareciendo como `disponible`.

**Evidencia:**
```python
# líneas 136-137
s.commit()
self._actualizar_estado_operativo(empleado_id, 'ocupado')
```

**Impacto real:** La vista de repartidores puede mostrar al repartidor como disponible cuando ya tiene un pedido asignado, causando doble asignación.

**Recomendación mínima concreta:** Este es un trade-off aceptado por diseño (thread daemon). Documentarlo explícitamente en el docstring. Alternativa mínima: incrementar log a `error` cuando el thread de `_actualizar_estado_operativo` falla.

---

### Hallazgo 4

**Tipo:** rendimiento  
**Severidad:** Media

**Problema:** `repartidores()` ejecuta tres queries secuenciales antes del batch (líneas 24–58): `Turno`, `CheckIn`, `Reparto` para IDs sin repartidor. Además, la subquery de `repartos_con_repartidor_ids` en línea 49 carga todos los `pedido_id` de repartos activos en memoria como un set Python, lo que escala mal si hay muchos pedidos activos simultáneos.

**Evidencia:**
```python
# líneas 49-54
repartos_con_repartidor_ids = {
    r.pedido_id for r in s.query(Reparto.pedido_id).filter(
        Reparto.repartidor_id != None,
        Reparto.estado.in_([...]),
    ).all()
}
```

**Impacto real:** En producción con decenas de pedidos activos, sigue siendo manejable. El riesgo es que `~Pedido.PedidoID.in_(repartos_con_repartidor_ids)` en línea 57 genera un `NOT IN (...)` SQL con todos los IDs, que en SQL Server degrada el plan de ejecución con listas largas.

**Recomendación mínima concreta:** Reemplazar por un `NOT EXISTS` o `LEFT JOIN / IS NULL` subquery directamente en SQL para delegar el filtro al motor.

---

### Hallazgo 5

**Tipo:** consistencia de estado / idempotencia  
**Severidad:** Media

**Problema:** En `reclamar_reparto` (líneas 201–263), cuando no existe `Reparto` (rama `else`, líneas 244–255), se crea uno con `estado=ASIGNADO`. Sin embargo, **no se transiciona `Pedido.Estado` a `EN_REPARTO`**. El docstring documenta esto explícitamente (línea 208), pero significa que el blueprint llamador DEBE hacer esa transición. Si el blueprint falla tras recibir `(True, 'ok')`, el pedido queda en `PREPARADO` con un `Reparto` en `ASIGNADO` — estado inconsistente entre las dos tablas.

**Evidencia:**
```python
# línea 208 (docstring)
# Nota: no transiciona Pedido.Estado a EN_REPARTO — esa responsabilidad
# recae en la ruta de blueprint que llama a este método.
```

**Impacto real:** Si el blueprint falla (timeout, excepción no capturada), queda inconsistencia observable: el mapa muestra `PREPARADO` pero el repartidor tiene el pedido asignado.

**Recomendación mínima concreta:** Evaluar si `reclamar_reparto` debería ser una operación completa que también transite `Pedido.Estado`. Si no, al menos documentar el patrón de compensación esperado en caso de fallo.

---

### Hallazgo 6

**Tipo:** observabilidad  
**Severidad:** Baja

**Problema:** Las operaciones de lectura (`repartidores`, `repartos_sin_asignar`) no tienen ningún logging. Si la vista del dashboard queda vacía o incorrecta, no hay telemetría para diagnosticar la causa.

**Evidencia:** Líneas 17–106 y 144–199 — ningún `logger.info` ni `logger.debug`.

**Impacto real:** Debug en producción requiere reproducir la query manualmente.

**Recomendación mínima concreta:** Añadir al menos `logger.debug("repartidores: %d empleados, %d sin asignar", len(lista_empleados), len(preparados_sin_reparto))`.

---

### Hallazgo 7

**Tipo:** testabilidad  
**Severidad:** Baja

**Problema:** `self.session` se obtiene vía `from database import get_db` dentro de una property de `_base.py` (línea 22 de `_base.py`). Esto hace que en tests sea necesario parchear `database.get_db` globalmente en lugar de inyectar una sesión directamente, lo que acopla los tests al módulo de infraestructura.

**Evidencia:** `_base.py` líneas 19-22: `@property def session(self): from database import get_db; return get_db()`.

**Impacto real:** Tests más frágiles — un cambio en cómo se obtiene la sesión rompe todos los tests de managers a la vez.

**Recomendación mínima concreta:** Aceptable mientras los tests usen `unittest.mock.patch('database.get_db', ...)`. No es urgente cambiar si los tests ya funcionan así de forma estable.

---

## 4. Riesgos principales si no se toca

| Riesgo | Escenario concreto |
|--------|-------------------|
| Re-asignación incorrecta de pedidos activos | Un operador asigna manualmente un pedido que ya está `EN_CAMINO`; el estado del Reparto se resetea a `ASIGNADO` borrando `hora_salida` y datos de la ruta activa |
| Empleado de cocina asignado como repartidor | Sin filtro de rol, cualquier empleado activo puede ser elegido; el mapa muestra rutas incoherentes |
| Estado operativo desincronizado | Thread de `_actualizar_estado_operativo` falla silenciosamente; repartidor aparece disponible cuando tiene pedido asignado; se le asigna un segundo pedido |
| `NOT IN` lento en SQL Server | Con decenas de pedidos activos, el plan de ejecución del filtro de `preparados_sin_reparto` puede degradarse |

---

## 5. Refactor mínimo recomendado

### Qué tocar primero (en orden de impacto)
1. **Hallazgo 2:** Añadir guarda de estado en `asignar_repartidor` para no resetear repartos activos. Es la corrección con mayor impacto en integridad de datos y mínimo riesgo de regresión.
2. **Hallazgo 1:** Validar rol de repartidor en `asignar_repartidor`. Un filtro de una línea.
3. **Hallazgo 4:** Reemplazar el `NOT IN` por `LEFT JOIN / IS NULL` en `preparados_sin_reparto` para mejorar el plan de ejecución.

### Qué NO tocar todavía
- La lógica atómica de `reclamar_reparto` — funciona correctamente y cualquier cambio requiere tests de concurrencia.
- El batch pre-load de `_batch_repartos` — es correcto y bien optimizado.
- La arquitectura de `_actualizar_estado_operativo` en background — el trade-off es aceptado por diseño.

---

## 6. Tests que deberían existir

- `test_asignar_repartidor_pedido_no_existe` — devuelve `(False, "Pedido no encontrado")`
- `test_asignar_repartidor_estado_invalido` — pedido en `EN_REPARTO` devuelve error
- `test_asignar_repartidor_sobreescribe_solo_no_entregado` — no permite reset de un reparto en `EN_CAMINO`
- `test_asignar_repartidor_valida_rol` — empleado sin rol repartidor devuelve error
- `test_reclamar_reparto_atomico` — dos llamadas concurrentes solo una tiene éxito (`ya_cogido`)
- `test_reclamar_reparto_no_existe` — pedido inexistente devuelve `'no_encontrado'`
- `test_reclamar_reparto_integrity_error` — simula `IntegrityError` en insert y devuelve `'ya_cogido'`
- `test_repartos_sin_asignar_incluye_pedidos_sin_reparto` — cubre la rama del `outerjoin`
- `test_repartidores_solo_con_turno_hoy` — empleados sin turno hoy no aparecen

---

## 7. Veredicto final

**Estado general del archivo:** Sólido en la parte más crítica (`reclamar_reparto`). Tiene bugs de integridad reales en `asignar_repartidor` (re-asignación sin guarda de estado y sin validación de rol) que son prioritarios.

**¿Bloquea crecimiento?** No, pero los bugs de `asignar_repartidor` se volverán más visibles si se expone esta función en más flujos de re-asignación.

**¿Bloquea testeo?** No. La sesión inyectable vía mock es suficiente para cubrir todos los casos.

**¿Tiene riesgo operativo real?** Sí. La re-asignación de un pedido en `EN_CAMINO` puede borrar datos de ruta activa. La falta de validación de rol puede mostrar datos incoherentes en el mapa.
