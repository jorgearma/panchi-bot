# Auditoría de `managers/pedidos/workflow_mixin.py`

> Auditoría técnica estricta. Fecha: 2026-04-09.
> Archivos analizados: `managers/pedidos/workflow_mixin.py`, `managers/pedidos/base.py`, `states.py`, `models.py` (clases Pago, Pedido, PickingPedido, PickingItem).

---

## 1. Rol del archivo

**Responsabilidad principal:** Motor de la máquina de estados del pedido — valida y ejecuta transiciones, crea registros de picking como side-effect, y persiste registros de pago.

**Qué debería hacer:** Centralizar todas las transiciones de estado de pedido, garantizar su validez, registrarlas en `HistorialEstadoPedido`, y crear los artefactos operativos derivados (PickingPedido, Pago).

**Qué no debería hacer:** Importar configuración de forma lazy dentro de métodos (pertenece al nivel de módulo). Exponer métodos de escritura sin manejo de errores.

**Dependencias clave:**
- `base.py` → `self.session` (MRO implícito)
- `states.py` → `EstadoPedido`, `EstadoPicking`, `transicion_valida_pedido`
- `models.py` → `HistorialEstadoPedido`, `Pago`, `Pedido`, `PickingItem`, `PickingPedido`
- `config` → `APP_MODE` (import lazy en l.113)

**Nivel de criticidad:** Crítico — es el único punto que impide transiciones de estado inválidas. Un bug aquí corrompe el flujo operativo completo.

---

## 2. Lo que hace bien

- **`_set_estado` como staging limpio** (l.13-35): no hace commit, solo prepara la transición y delega el commit al caller. Permite composición en operaciones atómicas más grandes.
- **Guard de transición inválida con log detallado** (l.16-22): `logger.error` incluye estado actual, nuevo estado y pedido_id — suficiente contexto para diagnosticar en producción.
- **`procesar_pago_confirmado` es atómico** (l.161-197): PAGADO + insert Pago en un único commit. Previene el caso de un pedido en PAGADO sin registro de pago.
- **Idempotencia en `_asegurar_picking_si_procede`** (l.104-108): verifica si ya existe un `PickingPedido` antes de crear uno nuevo — seguro ante reintentos del worker RQ.
- **`procesar_pago_confirmado` protegido por máquina de estados** (l.174): si se llama dos veces, `_set_estado` rechaza la segunda transición PAGADO→PAGADO antes de insertar el segundo `Pago`.
- **`registrar_pago` protegido por constraint DB** (l.125 en models.py): `referencia_externa` tiene `unique=True` — un segundo insert con la misma referencia Monei falla a nivel DB.

---

## 3. Hallazgos

### Hallazgo 1

**Tipo:** errores / consistencia  
**Severidad:** Media

**Problema:** `guardar_forma_pago`, `guardar_coordenadas` y `guardar_redis_id` (l.133-159) hacen `session.commit()` sin try/except y sin rollback. Un fallo de SQL Server en cualquiera de estas operaciones deja la sesión en estado sucio y la excepción se propaga sin log.

**Evidencia:**
```python
# líneas 133-140 — sin try/except
def guardar_forma_pago(self, pedido_id, forma_pago: str):
    pedido = self.session.query(Pedido).filter_by(PedidoID=pedido_id).first()
    if pedido:
        pedido.forma_pago = forma_pago
        self.session.commit()   # ← sin protección
        return True
    return False

# líneas 142-159 — mismo patrón en guardar_coordenadas y guardar_redis_id
```

**Impacto real:** Un corte transitorio de SQL Server al guardar `forma_pago` o coordenadas propaga la excepción al controller sin rollback explícito. El caller puede quedar con una sesión en estado inválido para la siguiente operación. Además, ninguno de los tres métodos tiene `@retry`, a diferencia del resto del mixin.

**Recomendación mínima concreta:** Envolver en try/except con rollback y re-raise, igual que los métodos adyacentes. Alternativamente, añadir `@retry` con el mismo decorador estándar del proyecto.

---

### Hallazgo 2

**Tipo:** consistencia / observabilidad  
**Severidad:** Media

**Problema:** `registrar_pago` (l.199-232) puede insertar registros de Pago duplicados cuando `referencia_externa` es `None`. El unique constraint de la columna (`unique=True` en models.py l.125) protege contra duplicados con la misma referencia Monei, pero no cuando se pasa `None` — SQL Server permite múltiples NULLs en una columna unique.

**Evidencia:**
```python
# workflow_mixin.py líneas 199-207
def registrar_pago(self, pedido_id, importe_euros, referencia_externa=None, datos_raw=None):
    pago = Pago(
        pedido_id=pedido_id,
        ...
        referencia_externa=referencia_externa,   # ← puede ser None
        ...
    )
```
```python
# models.py línea 125
referencia_externa = Column(String(255), nullable=True, unique=True)
# nullable=True + unique=True → múltiples NULLs son posibles en SQL Server
```

**Impacto real:** Si `registrar_pago` se llama con `referencia_externa=None` (pago en efectivo sin referencia Monei), un reintento inserta un segundo registro de Pago para el mismo pedido sin que el constraint lo rechace. No afecta a pagos Monei (tienen referencia), pero sí a flujos de efectivo o tests que omiten la referencia.

**Recomendación mínima concreta:** Añadir un guard previo al insert en `registrar_pago`:
```python
if referencia_externa is not None:
    existe = s.query(Pago).filter_by(referencia_externa=referencia_externa).first()
    if existe:
        logger.warning("registrar_pago: pago duplicado ignorado ref=%s", referencia_externa)
        return True
```
Para el caso `None`, es posible riesgo no confirmado si se usa en producción con pagos en efectivo — requiere verificar el caller.

---

### Hallazgo 3

**Tipo:** errores / consistencia  
**Severidad:** Media

**Problema:** `procesar_pago_confirmado` (l.161-197) captura `SQLAlchemyError` y devuelve `False` en lugar de re-lanzar la excepción, a diferencia de `actualizar_estado` y `fijar_carrito_confirmado` que sí re-lanzan. Un caller que no compruebe el valor de retorno no sabrá que el pago no se procesó.

**Evidencia:**
```python
# líneas 192-197 — retorna False, no re-lanza
except SQLAlchemyError as error:
    self.session.rollback()
    logger.error("Error al procesar pago confirmado del pedido %s: %s", pedido_id, error)
    return False   # ← el caller puede ignorar este False

# comparar con actualizar_estado líneas 56-60 — re-lanza
except SQLAlchemyError as error:
    self.session.rollback()
    logger.error(...)
    raise   # ← el caller está forzado a manejarlo
```

**Impacto real:** Posible riesgo no confirmado — depende de si el caller del webhook de Monei verifica el `bool` de retorno o asume que el método lanzará si falla. Si no verifica, el webhook devuelve 200 a Monei, el estado no cambia a PAGADO y el pedido queda en CONFIRMANDO_PAGO indefinidamente sin alerta.

**Recomendación mínima concreta:** Cambiar `return False` por `raise` en el bloque except de `procesar_pago_confirmado`, consistente con el resto del mixin. El `logger.error` ya registra el evento antes de relanzar.

---

### Hallazgo 4

**Tipo:** testabilidad / acoplamiento  
**Severidad:** Baja

**Problema:** `import config as app_config` (l.113) es un import lazy dentro de `_asegurar_picking_si_procede`. Para testear el comportamiento diferenciado warehouse/restaurant de esta función hay que parchear `managers.pedidos.workflow_mixin.config` en el momento de la llamada, no al importar el módulo — lo que es menos intuitivo que un import a nivel de módulo.

**Evidencia:**
```python
# línea 113 — dentro del método
def _asegurar_picking_si_procede(self, pedido, nuevo_estado) -> None:
    ...
    import config as app_config   # ← lazy
    modo = app_config.APP_MODE
```

**Impacto real:** Bajo. El import lazy funciona correctamente en producción. Solo dificulta el setup de tests para los dos modos de APP_MODE.

**Recomendación mínima concreta:** Mover `import config` a la cabecera del archivo. Si el import lazy existe para evitar un import circular, documentarlo con un comentario.

---

### Hallazgo 5

**Tipo:** observabilidad  
**Severidad:** Baja

**Problema:** `actualizar_estado` (l.37-60) — la función que gestiona TODAS las transiciones de estado del sistema — no tiene `logger.info` en el path de éxito. `_asegurar_picking_si_procede` tampoco registra cuándo crea un `PickingPedido`.

**Evidencia:**
- `actualizar_estado`: `logger.warning` (l.46) y `logger.error` (l.58) cubren los paths de fallo. Cero logs en éxito.
- `_asegurar_picking_si_procede`: ningún log en ningún path.
- Contraste: `procesar_pago_confirmado` sí tiene `logger.info` en éxito (l.188).

**Impacto real:** Al depurar por qué un pedido está en un estado inesperado no se puede reconstruir la cadena de transiciones desde los logs — solo desde `HistorialEstadoPedido` en DB. Si la DB está degradada durante el incidente, no hay trazabilidad.

**Recomendación mínima concreta:**
```python
# en actualizar_estado, tras el commit
logger.info("ESTADO_ACTUALIZADO pedido_id=%s %s→%s", pedido_id, pedido.Estado, nuevo_estado)

# en _asegurar_picking_si_procede, tras el flush
logger.info("PICKING_CREADO pedido_id=%s modo=%s", pedido.PedidoID, modo)
```

---

## 4. Riesgos principales si no se toca

| Riesgo | Escenario concreto |
|---|---|
| Sesión sucia en setter sin try/except | SQL Server cae durante `guardar_forma_pago`; la sesión queda en estado inválido y la siguiente operación del mismo request falla con error críptico de SQLAlchemy |
| Pago duplicado con referencia None | `registrar_pago(referencia_externa=None)` llamado dos veces inserta dos registros de Pago para el mismo pedido sin que el constraint lo rechace |
| Pago procesado silenciosamente fallido | Monei webhook recibe 200, el caller de `procesar_pago_confirmado` no comprueba el False, el pedido queda en CONFIRMANDO_PAGO y el cliente no recibe confirmación |
| Tests frágiles para APP_MODE | El import lazy de `config` dentro del método requiere un patrón de patch no obvio que puede llevar a tests que no verifican realmente el comportamiento restaurant/warehouse |

---

## 5. Refactor mínimo recomendado

### Qué tocar primero (en orden de impacto)

1. **Hallazgo 3 (procesar_pago_confirmado):** Cambiar `return False` por `raise` en el except — una palabra. Elimina el riesgo de pago silenciosamente fallido.
2. **Hallazgo 1 (setters sin try/except):** Añadir try/except + rollback + raise a `guardar_forma_pago`, `guardar_coordenadas`, `guardar_redis_id`. Tres bloques idénticos.
3. **Hallazgo 5 (observabilidad):** Añadir `logger.info` en `actualizar_estado` y `_asegurar_picking_si_procede`. Cuatro líneas.

### Qué NO tocar todavía

- La lógica de `_asegurar_picking_si_procede`: warehouse/restaurant branch es correcto, no tocar.
- La separación `procesar_pago_confirmado` vs `registrar_pago`: requiere verificar callers antes de consolidar.
- El Hallazgo 2 (duplicado con None): confirmar primero si `registrar_pago` se llama con `None` en producción.

---

## 6. Tests que deberían existir

- `test_set_estado_transicion_invalida_devuelve_false` — verifica que `_set_estado` rechaza PAGADO→PENDIENTE sin modificar `pedido.Estado`.
- `test_actualizar_estado_reintenta_en_sqlerror` — mockea `session.commit` para fallar en el primer intento y verifica que tenacity reintenta.
- `test_asegurar_picking_idempotente` — llamar `_asegurar_picking_si_procede` dos veces sobre el mismo pedido crea exactamente un `PickingPedido`.
- `test_asegurar_picking_warehouse_crea_items` — en `APP_MODE=warehouse`, verifica que se crean `PickingItem` por cada `PedidoDetalle`.
- `test_asegurar_picking_restaurant_no_crea_items` — en `APP_MODE=restaurant`, verifica que NO se crean `PickingItem`.
- `test_procesar_pago_confirmado_atomico` — si `session.commit` falla, ni el estado ni el Pago quedan persistidos.
- `test_procesar_pago_confirmado_segunda_llamada_rechazada` — segunda llamada devuelve False por transición inválida, sin insertar segundo Pago.
- `test_registrar_pago_duplicado_referencia_none` — dos llamadas con `referencia_externa=None` no crean dos registros de Pago.
- `test_guardar_forma_pago_rollback_en_error` — mockea commit para lanzar SQLAlchemyError y verifica que se llama rollback.

---

## 7. Veredicto final

**Estado general del archivo:** El núcleo de la máquina de estados está bien implementado. Los problemas son periféricos: tres métodos auxiliares sin protección de errores, una inconsistencia en el manejo de excepciones de `procesar_pago_confirmado`, y falta de logging en el path de éxito de las transiciones.

**¿Bloquea crecimiento?** No.

**¿Bloquea testeo?** Parcialmente — el import lazy de `config` y la ausencia de try/except en los setters dificultan el setup de tests.

**¿Tiene riesgo operativo real?** Sí: `procesar_pago_confirmado` retornando `False` silenciosamente puede dejar pedidos bloqueados en CONFIRMANDO_PAGO si el caller del webhook de Monei no verifica el retorno.
