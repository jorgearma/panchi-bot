# Auditoría de `managers/dashboard/reparto_tracking.py`

> Auditoría técnica estricta. Fecha: 2026-04-08.
> Archivos analizados: `managers/dashboard/reparto_tracking.py`, `managers/dashboard/_helpers.py`, `managers/dashboard/_base.py`, `states.py`.

---

## 1. Rol del archivo

**Responsabilidad principal:** Tracking operativo de repartos: datos del mapa, lista de repartos de un repartidor, y transiciones de estado (salida, entrega, no entrega) con actualización simultánea de `Pedido` y `Reparto`.

**Qué debería hacer:** Queries de lectura sobre `Pedido`/`Reparto` para el mapa y la cola del repartidor. Escritura atómica de cambios de estado en `Reparto` y `Pedido` con registro en `HistorialEstadoPedido`.

**Qué no debería hacer:** Enviar notificaciones de WhatsApp (responsabilidad de un controller o service), gestionar sesiones Redis, calcular métricas de rendimiento.

**Dependencias clave:** `models.Reparto/Pedido/PedidoDetalle/HistorialEstadoPedido`, `states.EstadoPedido/EstadoReparto/transicion_valida_pedido`, `services.whatsapp_service.notificar_async`, `managers/dashboard/_helpers`, `threading.Thread`, `database.SessionLocal`.

**Nivel de criticidad:** Crítico — `marcar_entregado` es el punto final del flujo operativo. Un bug aquí deja pedidos en estado incorrecto permanentemente.

---

## 2. Lo que hace bien

- **`mapa` (líneas 27–57):** Usa `load_only` para cargar únicamente las columnas necesarias. Filtrado correcto por `_ESTADOS_OPERATIVOS`. Filtra pedidos sin coordenadas (línea 41).
- **`marcar_entregado` (línea 215):** Guarda de cobro registrado para contra reembolso (líneas 224–226) es un control de integridad correcto — impide marcar entregado sin cobro previo.
- **`transicion_valida_pedido` (líneas 170, 232):** Ambas funciones de marcado comprueban la transición antes de mutar `Pedido.Estado`. Respeta el contrato de `states.py`.
- **`HistorialEstadoPedido` (líneas 173–178, 235–240):** Registro de historial en la misma transacción que el cambio de estado — correcto y atómico.
- **Lazy import de `or_`/`and_` (línea 61):** Es el único import lazy del archivo; no es ideal pero el impacto es mínimo dado que `sqlalchemy` ya está cargado.

---

## 3. Hallazgos

### Hallazgo 1

**Tipo:** consistencia / errores  
**Severidad:** Crítica

**Problema:** En `marcar_entregado` (líneas 215–274), el `Thread` de background (líneas 247–265) llama a `self._actualizar_estado_operativo(emp_id, 'disponible')` desde dentro del thread. `self` es el mixin que expone `self.session` vía `@property` en `_base.py`, el cual a su vez llama a `get_db()`. Dentro del thread, `_actualizar_estado_operativo` también abre su propia sesión (`SessionLocal()`). Sin embargo, si `_actualizar_estado_operativo` es sobreescrita o extendida en una subclase para usar `self.session`, causaría un acceso a la sesión del hilo principal desde un hilo secundario — race condition en SQLAlchemy (las sesiones no son thread-safe).

**Evidencia:**
```python
# líneas 247-265
def _actualizar_disponibilidad(emp_id=_repartidor_id):
    from database import SessionLocal
    _s = SessionLocal()
    try:
        _activos = _s.query(Reparto).filter(...).count()
        if _activos == 0:
            self._actualizar_estado_operativo(emp_id, 'disponible')  # usa self desde hilo secundario
```

En `_base.py` líneas 36–54, `_actualizar_estado_operativo` crea correctamente su propia `SessionLocal`. Pero `self._actualizar_estado_operativo` es llamado desde el hilo, lo que abre **dos sesiones concurrentes**: `_s` (línea 249) y la que abre `_actualizar_estado_operativo` internamente. Si alguna futura modificación hace que `_actualizar_estado_operativo` acceda a `self.session` (la sesión del hilo principal), se produce corrupción silenciosa.

**Impacto real:** Actualmente funciona porque `_actualizar_estado_operativo` abre su propia sesión. Pero la dependencia de `self` desde un daemon thread es una trampa arquitectónica: cualquier refactor de `_base.py` puede introducir un bug de thread-safety difícil de detectar.

**Recomendación mínima concreta:** Extraer la función `_actualizar_disponibilidad` al nivel de módulo (función libre, no método) o pasar solo los valores primitivos necesarios (`emp_id`, `estados_activos`) en lugar de capturar `self`. Ejemplo mínimo:
```python
def _actualizar_disponibilidad(emp_id):
    from database import SessionLocal
    from managers.dashboard._base import GestorDashboardBase
    # ... o simplemente duplicar las 5 líneas de lógica aquí sin self
```

---

### Hallazgo 2

**Tipo:** consistencia de estado  
**Severidad:** Alta

**Problema:** En `marcar_salida_reparto` (líneas 158–188), el método actualiza `reparto.estado` y `reparto.hora_salida` y **luego** verifica `transicion_valida_pedido` para actualizar `Pedido.Estado`. Si la transición no es válida (por ejemplo, el pedido ya está en `EN_REPARTO` por una llamada duplicada), el Reparto se persiste en `EN_CAMINO` con `hora_salida` actualizada, pero el Pedido no se toca — sin ningún aviso al caller.

**Evidencia:**
```python
# líneas 166-179
reparto.estado = EstadoReparto.EN_CAMINO.value
reparto.hora_salida = datetime.utcnow()

pedido = reparto.pedido
if pedido and transicion_valida_pedido(pedido.Estado, EstadoPedido.EN_REPARTO.value):
    # solo actualiza Pedido si la transición es válida
    pedido.Estado = EstadoPedido.EN_REPARTO.value
    ...
s.commit()
return True, "Repartidor marcado como en camino"  # siempre True si no hay SQLAlchemyError
```

Si la transición de Pedido no es válida (pedido ya en `EN_REPARTO`), el método devuelve `(True, "Repartidor marcado como en camino")` igualmente, sin indicar que el estado de Pedido no se actualizó.

**Impacto real:** Una segunda llamada (reintento de repartidor, doble tap) actualiza `hora_salida` del Reparto a la segunda llamada, perdiendo el timestamp original. El Pedido no se toca (ya estaba en `EN_REPARTO`), pero el caller recibe `True` sin saber que hubo una discrepancia.

**Recomendación mínima concreta:** Si `transicion_valida_pedido` devuelve `False` y el pedido ya estaba en el estado correcto (idempotencia), continuar silenciosamente. Si devuelve `False` por un estado inesperado, loggear `warning`. Al menos proteger `hora_salida` con `if not reparto.hora_salida:` para no sobreescribir en retries.

---

### Hallazgo 3

**Tipo:** consistencia de estado  
**Severidad:** Alta

**Problema:** En `marcar_no_entregado` (líneas 190–213), cuando se marca como `NO_ENTREGADO`, **no se actualiza `Pedido.Estado`** (el docstring lo documenta explícitamente). Sin embargo, tampoco hay ninguna transición de retorno para el Pedido. El pedido queda en `EN_REPARTO` indefinidamente hasta que un operador intervenga manualmente. No hay logging de advertencia, ni notificación, ni ninguna marca en el Pedido que indique la situación.

**Evidencia:**
```python
# líneas 190-213
# docstring: "pedido state stays as-is so the ops team can handle it from the dashboard"
reparto.estado = EstadoReparto.NO_ENTREGADO.value
reparto.motivo_no_entrega = motivo
pedido = reparto.pedido  # se obtiene pero no se usa
s.commit()
return True, "Marcado como no entregado"
```

`pedido` se obtiene en línea 204 pero no se usa en absoluto — la variable está muerta.

**Impacto real:** El pedido queda en `EN_REPARTO` de forma silenciosa. Si el equipo de ops no monitorea el dashboard activamente, el pedido puede quedar "fantasma" en el sistema. La variable `pedido` muerta sugiere que hubo una intención de hacer algo con ella que quedó incompleta.

**Recomendación mínima concreta:**
1. Eliminar la variable `pedido` muerta (línea 204) o documentar explícitamente por qué se obtiene y no se usa.
2. Añadir `logger.warning("Reparto %s marcado NO_ENTREGADO: pedido %s queda en EN_REPARTO", reparto_id, reparto.pedido_id)` para observabilidad.
3. Evaluar si se debe añadir una nota en `Pedido` o transicionar a un estado intermedio como `PREPARADO` para re-reparto.

---

### Hallazgo 4

**Tipo:** consistencia de estado  
**Severidad:** Alta

**Problema:** En `marcar_entregado` (líneas 215–274), la guarda de cobro (líneas 224–226) accede a `reparto.pedido` que puede ser `None` si la relación no está cargada en la sesión (lazy load no garantizado en todos los contextos de sesión).

**Evidencia:**
```python
# líneas 224-226
forma_pago = reparto.pedido.forma_pago if reparto.pedido else None
if forma_pago in ('efectivo', 'tarjeta') and reparto.metodo_cobro is None:
    return False, "Debes registrar el cobro antes de marcar como entregado", None
```

Si `reparto.pedido` es `None` por un pedido huérfano (bug de datos), `forma_pago` es `None`, la condición es `False`, y el reparto se marca como entregado **sin verificar el cobro**. El guard se bypasea silenciosamente en caso de datos corruptos.

**Impacto real:** Un reparto contra reembolso con pedido huérfano en DB se marcaría como entregado sin cobro registrado, generando un hueco financiero.

**Recomendación mínima concreta:** Añadir verificación explícita si `reparto.pedido is None` y devolver error, o al menos loggar warning:
```python
if reparto.pedido is None:
    logger.error("marcar_entregado: reparto %s sin pedido asociado", reparto_id)
    return False, "Error de integridad: reparto sin pedido", None
```

---

### Hallazgo 5

**Tipo:** acoplamiento / testabilidad  
**Severidad:** Media

**Problema:** `repartos_del_repartidor` (líneas 59–156) tiene un import lazy de `sqlalchemy` dentro del cuerpo de la función (línea 61): `from sqlalchemy import or_, and_`. Esto es innecesario — `or_` y `and_` podrían importarse en el módulo.

**Evidencia:**
```python
# línea 61
def repartos_del_repartidor(self, empleado_id: int) -> list:
    from sqlalchemy import or_, and_
```

**Impacto real:** El import lazy dentro de función hace que el error de import solo se detecte en runtime al llamar la función, no al importar el módulo. En tests, puede ocultar errores de configuración del entorno.

**Recomendación mínima concreta:** Mover `from sqlalchemy import or_, and_` al nivel del módulo junto al resto de imports de SQLAlchemy (líneas 5–8).

---

### Hallazgo 6

**Tipo:** diseño / lógica de negocio  
**Severidad:** Media

**Problema:** `repartos_del_repartidor` (líneas 87–154) contiene lógica de inferencia de método de pago (líneas 93–124) idéntica a la de `reparto_cobro.py` (misma lógica duplicada). Esto viola DRY y significa que si la lógica de clasificación de pago cambia, debe actualizarse en dos lugares.

**Evidencia:** La misma secuencia `pago_completado → pagado_online / forma_pago efectivo / forma_pago tarjeta / default online` aparece en `reparto_cobro.py` líneas 90–94 y en `reparto_tracking.py` líneas 94–124 (versión más expandida).

**Impacto real:** Un cambio en la lógica de clasificación de pago (por ejemplo, añadir Bizum) requiere modificar ambos archivos. Si se actualiza uno y no el otro, el repartidor ve información de pago diferente en su lista de la que aparece en el cierre de caja.

**Recomendación mínima concreta:** Extraer la lógica de clasificación a `_helpers.py` como función `_clasificar_pago(pedido, reparto) -> dict`. Ambos mixins la importan de allí.

---

### Hallazgo 7

**Tipo:** observabilidad  
**Severidad:** Media

**Problema:** `marcar_salida_reparto` devuelve una tupla de 2 elementos `(bool, str)` según su docstring, pero el docstring dice "Returns (ok, msg, telefono_cliente)". La firma real también retorna solo 2 elementos cuando hay error (líneas 163, 188) pero el docstring promete 3. `marcar_entregado` sí devuelve 3 elementos correctamente. Esto genera asimetría que puede causar bugs en el blueprint caller si desempaqueta 3 valores.

**Evidencia:**
```python
# línea 159 — docstring
"""Returns (ok, msg, telefono_cliente). telefono_cliente is None on error."""
# línea 163 — devuelve 2 elementos
return False, "Reparto no encontrado", None  # OK, 3 elementos aquí
# línea 184 — devuelve solo 2 elementos
return True, "Repartidor marcado como en camino"  # FALTA el tercer elemento
# línea 188 — devuelve solo 2 elementos
return False, "Error de base de datos"  # FALTA el tercer elemento
```

**Impacto real:** Si el blueprint hace `ok, msg, tel = marcar_salida_reparto(...)`, las líneas 184 y 188 lanzan `ValueError: not enough values to unpack`. Es un bug latente que solo aparece en el path de éxito o error de SQLAlchemy.

**Recomendación mínima concreta:** Corregir líneas 184 y 188 para devolver 3 elementos:
```python
return True, "Repartidor marcado como en camino", None
# y
return False, "Error de base de datos", None
```

---

### Hallazgo 8

**Tipo:** rendimiento / correctitud  
**Severidad:** Baja

**Problema:** `marcar_no_entregado` permite marcar como `NO_ENTREGADO` un reparto que ya está en estado `ENTREGADO` (línea 198):
```python
if reparto.estado not in (EstadoReparto.EN_CAMINO.value, EstadoReparto.ENTREGADO.value):
```
Esto es intencionado para permitir corrección de errores, pero no hay logging ni historial de esta corrección retroactiva. Un reparto que ya estaba `ENTREGADO` y se marca como `NO_ENTREGADO` no genera ningún registro en `HistorialEstadoPedido`.

**Evidencia:** Líneas 198–209 — ningún registro de historial al cambiar estado.

**Impacto real:** En el cierre de caja, el reparto ya habría sido contado como `ENTREGADO`. Al corregirlo a `NO_ENTREGADO`, el cierre no lo incluirá si se regenera. Pero si el cierre ya fue impreso/presentado, hay una discrepancia silenciosa.

**Recomendación mínima concreta:** Añadir `logger.warning` cuando se marca `NO_ENTREGADO` desde un reparto ya `ENTREGADO`. Evaluar si se debe añadir entrada en `HistorialEstadoPedido` para trazabilidad.

---

## 4. Riesgos principales si no se toca

| Riesgo | Escenario concreto |
|--------|-------------------|
| Bug de desempaquetado en blueprint | Blueprint llama `ok, msg, tel = marcar_salida_reparto(...)` — líneas de éxito y error de DB lanzan `ValueError` silenciosamente en producción si el blueprint usa desempaquetado de 3 valores |
| Pedido `EN_REPARTO` fantasma | Repartidor marca `NO_ENTREGADO`; pedido queda en `EN_REPARTO` sin ningún aviso al equipo de ops; puede quedar así indefinidamente |
| Thread captura `self` de forma insegura | Refactor futuro de `_base.py` que haga `_actualizar_estado_operativo` usar `self.session` introduce race condition de SQLAlchemy sin ningún error visible |
| Guard de cobro bypasseada | Reparto con pedido huérfano en DB se marca entregado sin cobro; pérdida financiera sin rastro |
| Lógica de pago duplicada desincronizada | Se añade método de pago "Bizum" en `reparto_cobro.py` y se olvida en `reparto_tracking.py`; el repartidor ve "Pagado online" cuando debería ver "Cobrar Bizum" |

---

## 5. Refactor mínimo recomendado

### Qué tocar primero (en orden de impacto)
1. **Hallazgo 7 (URGENTE):** Corregir la firma de retorno de `marcar_salida_reparto` — bug real con `ValueError` en producción. Dos líneas.
2. **Hallazgo 3:** Eliminar la variable `pedido` muerta en `marcar_no_entregado` y añadir logging de warning.
3. **Hallazgo 4:** Añadir guarda explícita para `reparto.pedido is None` en `marcar_entregado`.
4. **Hallazgo 2:** Proteger `hora_salida` con `if not reparto.hora_salida` para evitar sobreescritura en retries.
5. **Hallazgo 6:** Extraer la lógica de clasificación de pago a `_helpers.py` para eliminar duplicación con `reparto_cobro.py`.

### Qué NO tocar todavía
- La lógica de `mapa` — es correcta y bien optimizada con `load_only`.
- El mecanismo de thread de `_actualizar_disponibilidad` — funciona correctamente en su forma actual; el riesgo del Hallazgo 1 es futuro y requiere un refactor más amplio de `_base.py`.
- El eager loading en `repartos_del_repartidor` — está bien configurado.

---

## 6. Tests que deberían existir

- `test_marcar_salida_devuelve_tres_elementos_en_exito` — verifica que el desempaquetado `ok, msg, tel` no falla
- `test_marcar_salida_devuelve_tres_elementos_en_error` — mismo para paths de error
- `test_marcar_entregado_requiere_cobro_en_contra_reembolso` — sin `metodo_cobro`, devuelve error
- `test_marcar_entregado_con_pedido_huerfano` — `reparto.pedido is None` devuelve error, no bypasea guard
- `test_marcar_no_entregado_deja_pedido_en_reparto` — estado de `Pedido` no cambia
- `test_marcar_no_entregado_transicion_invalida` — reparto en PENDIENTE devuelve error
- `test_marcar_salida_idempotente_no_sobreescribe_hora` — segunda llamada no actualiza `hora_salida`
- `test_mapa_excluye_pedidos_sin_coordenadas` — pedidos con `lat=None` no aparecen en puntos
- `test_mapa_solo_estados_operativos` — pedidos ENTREGADO o CANCELADO no aparecen
- `test_repartos_del_repartidor_incluye_solo_hoy_completados` — repartos entregados de ayer no aparecen

---

## 7. Veredicto final

**Estado general del archivo:** Contiene un bug real de producción (Hallazgo 7: firma de retorno inconsistente en `marcar_salida_reparto`). El resto de la lógica es sólida en su núcleo, pero tiene varias inconsistencias de estado y un riesgo de thread-safety latente.

**¿Bloquea crecimiento?** Sí parcialmente: la duplicación de la lógica de clasificación de pago (Hallazgo 6) hará que añadir nuevos métodos de pago sea propenso a errores de sincronización.

**¿Bloquea testeo?** No, pero el import lazy en `repartos_del_repartidor` (Hallazgo 5) y la captura de `self` en el thread (Hallazgo 1) complican los tests de integración.

**¿Tiene riesgo operativo real?** Sí. El Hallazgo 7 es un `ValueError` latente en producción. El Hallazgo 3 deja pedidos en estado fantasma sin observabilidad. El Hallazgo 4 puede bypasear la guarda financiera de cobro.
