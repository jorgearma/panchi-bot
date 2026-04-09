# Auditoría de `blueprints/picker.py`

> Auditoría técnica estricta. Fecha: 2026-04-07.
> Archivos analizados: `blueprints/picker.py`, `blueprints/_pwa.py`.

---

## 1. Rol del archivo

**Responsabilidad principal:** Routing HTTP para la PWA del picker — cola de pickings, asignación, actualización de ítems y cierre de picking.
**Qué debería hacer:** Validar entrada, delegar en `gestor_dashboard`, devolver respuesta HTTP. Gestionar las rutas PWA (manifest, SW, iconos).
**Qué no debería hacer:** Contener lógica de negocio ni hacer acceso directo a DB/Redis.
**Dependencias clave:** `gestor_dashboard` (god object 121 KB, singleton de container), `blueprints/_pwa` (helpers de PWA), `services.demo_state.DemoState` (5 imports lazy).
**Nivel de criticidad:** Alto — gestiona la transición de estado de los pickings (operativa en tiempo real).

---

## 2. Lo que hace bien

- Separación limpia con `_pwa.py`: manifest, service worker e iconos extraídos a un helper sin duplicación.
- Validación mínima pero correcta: `estado` requerido (línea 86), `producto_sustituto_id` validado como int (líneas 91–94), `q` con longitud mínima (línea 117).
- `coger_picking` distingue correctamente `no_encontrado` (404), `ya_cogido` (409) y errores genéricos (400) — permite al cliente tomar decisiones (líneas 176–180).
- Logging de eventos de negocio clave: `finalizar_picking` y `coger_picking` emiten `logger.info` en éxito (líneas 138, 174).
- `item_id` y `picking_id` tipados como `int` en la ruta — Flask rechaza valores no numéricos sin código adicional.
- El patrón de threading mencionado en CLAUDE.md para este archivo **no está presente** en la versión actual — positivo.

---

## 3. Hallazgos

### Hallazgo 1

**Tipo:** errores / observabilidad
**Severidad:** Media

**Problema:** `actualizar_item` no tiene try/except alrededor de la llamada al manager.
**Evidencia:**
```python
# líneas 97–107
ok, msg = gestor_dashboard.actualizar_item_picking(
    item_id=item_id,
    estado=estado,
    ...
)
if not ok:
    return jsonify({"error": msg}), 400
return jsonify({"ok": True, "mensaje": msg})
```
**Impacto real:** Si `gestor_dashboard.actualizar_item_picking` lanza una excepción (caída de SQL Server, violación de restricción), Flask devuelve 500 sin ningún `logger.error`. El error sólo aparece en los logs del framework, sin contexto de `item_id` ni `picker_id`.
**Recomendación mínima concreta:**
```python
try:
    ok, msg = gestor_dashboard.actualizar_item_picking(...)
except Exception as e:
    logger.error("Error en /picker/item/%s/estado picker_id=%s: %s", item_id, picker_id, e)
    return jsonify({"error": "Error interno"}), 500
```

---

### Hallazgo 2

**Tipo:** errores / observabilidad
**Severidad:** Media

**Problema:** `finalizar_picking` no tiene try/except alrededor de la llamada al manager.
**Evidencia:**
```python
# líneas 135–139
ok, msg = gestor_dashboard.completar_picking(picking_id, picker_id=picker_id)
if not ok:
    return jsonify({"error": msg}), 400
logger.info("[PICKING] Empleado %s finaliza picking %s", picker_id, picking_id)
return jsonify({"ok": True, "mensaje": msg})
```
**Impacto real:** Mismo patrón que Hallazgo 1 — excepción en `completar_picking` produce 500 sin log con contexto. Es especialmente relevante porque esta ruta completa una operación crítica (transición de estado del picking).
**Recomendación mínima concreta:**
```python
try:
    ok, msg = gestor_dashboard.completar_picking(picking_id, picker_id=picker_id)
except Exception as e:
    logger.error("Error en /picker/picking/%s/finalizar picker_id=%s: %s", picking_id, picker_id, e)
    return jsonify({"error": "Error interno"}), 500
```

---

### Hallazgo 3

**Tipo:** acoplamiento / testabilidad
**Severidad:** Baja

**Problema:** `from services.demo_state import DemoState` se repite como import lazy en 5 funciones distintas.
**Evidencia:**
```python
# línea 58 (mis_pedidos)
# línea 73 (actualizar_item)
# línea 131 (finalizar_picking)
# línea 147 (cola)
# línea 162 (coger_picking)
from services.demo_state import DemoState
```
**Impacto real:** El import lazy oculta la dependencia real del módulo. En tests, hay que parchear `services.demo_state.DemoState` en cada función de forma independiente en lugar de una sola vez al nivel del módulo. Si DemoState falla al importar, el error aparece en runtime dentro de la ruta, no al arrancar.
**Recomendación mínima concreta:** Mover el import al nivel superior del módulo junto con los demás imports:
```python
from services.demo_state import DemoState
```
Si el import lazy existe para evitar una importación circular, documentarlo con un comentario.

---

### Hallazgo 4

**Tipo:** diseño
**Severidad:** Baja

**Problema:** La rama `demo_mode` duplica el mismo patrón condicional en cada ruta.
**Evidencia:** Líneas 57–59, 72–83, 130–133, 146–148, 161–166 — cada handler comprueba `session.get('demo_mode')` y bifurca hacia `DemoState`.
**Impacto real:** No es un bug, pero hace que cada función tenga dos paths de código independientes. Añadir una ruta nueva requiere recordar replicar la bifurcación demo. Los tests necesitan cubrir cada ruta dos veces (modo real + demo).
**Recomendación mínima concreta:** Posible riesgo no confirmado sobre si hay un decorador o wrapper central más adecuado — este patrón parece deliberado en el proyecto. No tocar sin consenso. Documentar que es intencional.

---

### Hallazgo 5

**Tipo:** observabilidad
**Severidad:** Baja

**Problema:** `actualizar_item` no emite ningún `logger.info` en éxito, a diferencia de `finalizar_picking` y `coger_picking`.
**Evidencia:** No hay ningún log en el path de éxito de las líneas 97–107.
**Impacto real:** Las actualizaciones de ítems de picking (el evento más frecuente de la operativa) no dejan rastro en logs. Dificulta diagnosticar discrepancias entre el estado en DB y lo que reporta el picker.
**Recomendación mínima concreta:**
```python
logger.info("[PICKING] Picker %s actualiza item %s → %s", picker_id, item_id, estado)
```

---

## 4. Riesgos principales si no se toca

| Riesgo | Escenario concreto |
|--------|-------------------|
| Excepción en `actualizar_item` sin log | Caída transitoria de SQL Server durante una actualización de ítem; el picker ve un 500 sin contexto y no hay traza útil para diagnosticar |
| Excepción en `finalizar_picking` sin log | `completar_picking` falla (p.ej. picking ya en estado final); el manager lanza, el blueprint devuelve 500 sin identificar picking_id ni picker_id en logs |
| Import lazy de DemoState falla en runtime | Un error de importación en `services/demo_state.py` solo se descubre cuando un picker entra en modo demo, no al arrancar la app |

---

## 5. Refactor mínimo recomendado

### Qué tocar primero (en orden de impacto)

1. **Hallazgo 1** — Envolver la llamada a `actualizar_item_picking` en try/except con `logger.error` y contexto.
2. **Hallazgo 2** — Envolver la llamada a `completar_picking` en try/except con `logger.error` y contexto.
3. **Hallazgo 5** — Añadir `logger.info` en el path de éxito de `actualizar_item`.
4. **Hallazgo 3** — Mover los 5 imports lazy de `DemoState` al nivel del módulo (o documentar por qué son lazy).

### Qué NO tocar todavía

- El patrón de bifurcación demo (Hallazgo 4) — cambio de diseño amplio, sin impacto operativo inmediato.
- La dependencia de `gestor_dashboard` — es el god object conocido; no añadir más métodos, pero tampoco romperlo aquí.

---

## 6. Tests que deberían existir

- `test_actualizar_item_estado_valido` — POST con `estado` válido → manager devuelve `(True, msg)` → 200 `{"ok": True}`.
- `test_actualizar_item_falta_estado` — POST sin campo `estado` → 400 sin llamar al manager.
- `test_actualizar_item_manager_lanza` — manager lanza excepción → 500 con log de error (actualmente no se loguearía).
- `test_actualizar_item_producto_sustituto_invalido` — `producto_sustituto_id="abc"` → 400.
- `test_finalizar_picking_ok` — manager devuelve `(True, msg)` → 200 con log info.
- `test_finalizar_picking_manager_lanza` — manager lanza excepción → 500 con log de error (actualmente no se loguearía).
- `test_coger_picking_ya_cogido` — manager devuelve `(False, 'ya_cogido')` → 409.
- `test_coger_picking_no_encontrado` — manager devuelve `(False, 'no_encontrado')` → 404.
- `test_buscar_productos_query_corta` — `q="a"` → 200 lista vacía sin llamar al manager.
- `test_mis_pedidos_demo_mode` — sesión con `demo_mode=True` → llama a DemoState, no a gestor_dashboard.

---

## 7. Veredicto final

**Estado general del archivo:** Correcto en estructura y validaciones de entrada. Los problemas son dos paths de error sin cobertura de logging en rutas operativas críticas, y un patrón de imports ocultos que complica el testing.
**¿Bloquea crecimiento?** No.
**¿Bloquea testeo?** Parcialmente — los imports lazy de DemoState requieren patching específico por función; los paths de excepción en Hallazgos 1 y 2 no se pueden verificar sin romper el manager.
**¿Tiene riesgo operativo real?** Sí, bajo — una excepción en `actualizar_item` o `finalizar_picking` produce un 500 silencioso sin trazabilidad, lo que dificulta el diagnóstico en operativa de almacén en tiempo real.
