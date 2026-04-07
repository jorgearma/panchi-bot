# Auditoría de `managers/dashboard/reparto_cobro.py`

> Auditoría técnica estricta. Fecha: 2026-04-08.
> Archivos analizados: `managers/dashboard/reparto_cobro.py`, `managers/dashboard/_helpers.py`, `states.py`, `models.py` (referenciado vía imports).

---

## 1. Rol del archivo

**Responsabilidad principal:** Persistir el cobro realizado por el repartidor en un reparto ya entregado, y calcular el resumen de cierre de caja diario de un repartidor.

**Qué debería hacer:** Escritura de datos de cobro en `Reparto`, lectura y agregación de repartos entregados en un día para generar el resumen de caja.

**Qué no debería hacer:** Validar si un pedido puede ser cobrado (eso es del controller), enviar notificaciones, calcular métricas históricas de rendimiento.

**Dependencias clave:** `models.Reparto`, `models.Pedido`, `states.EstadoReparto`, `managers/dashboard/_helpers._iso`. No depende de Redis.

**Nivel de criticidad:** Alto — los datos de cobro alimentan la liquidación financiera del repartidor. Un error aquí tiene impacto económico directo.

---

## 2. Lo que hace bien

- **Validación de `metodo_cobro` (línea 27–29):** Whitelist explícita `{'efectivo', 'tarjeta', 'mixto'}` antes de tocar la DB. Correcto.
- **Eager loading en `cierre_caja_repartidor` (líneas 61–64):** `joinedload(Reparto.pedido)` con `joinedload(Pedido.cliente)` y `selectinload(Pedido.pagos)` evita N+1 queries.
- **Separación contable limpia (líneas 96–106):** El cálculo distingue correctamente efectivo puro, tarjeta pura y parte efectivo/tarjeta de mixto.
- **Manejo de errores en escritura (líneas 44–47):** `SQLAlchemyError` capturado con rollback y log estructurado.
- **Función `_detalle` local (líneas 108–122):** Encapsulada correctamente dentro del método, no contamina el namespace del mixin.

---

## 3. Hallazgos

### Hallazgo 1

**Tipo:** consistencia de estado  
**Severidad:** Alta

**Problema:** `registrar_cobro` no verifica que el `Reparto` esté en estado `ENTREGADO` antes de registrar el cobro. Se puede registrar un cobro en un reparto en estado `ASIGNADO` o `EN_CAMINO`, lo que genera datos financieros incoherentes con el estado operativo.

**Evidencia:**
```python
# líneas 33-43
reparto = s.query(Reparto).filter_by(id=reparto_id).first()
if not reparto:
    return False, "Reparto no encontrado"

reparto.metodo_cobro     = metodo_cobro
reparto.importe_cobrado  = importe_cobrado
# ... no hay verificación de reparto.estado
s.commit()
```

**Impacto real:** Un repartidor (o llamada errónea de blueprint) puede registrar el cobro antes de marcar la entrega. El cierre de caja entonces agregaría un reparto filtrado por `estado == ENTREGADO` (línea 69) que aún no lo está — pero los campos de cobro ya estarán escritos para cuando se marque como entregado. El riesgo principal es que permite una escritura en cualquier estado, violando el contrato del modelo.

**Recomendación mínima concreta:** Añadir guarda tras obtener `reparto`:
```python
if reparto.estado != EstadoReparto.ENTREGADO.value:
    return False, f"Solo se puede registrar cobro en repartos entregados (estado actual: {reparto.estado})"
```

---

### Hallazgo 2

**Tipo:** consistencia / errores  
**Severidad:** Alta

**Problema:** `registrar_cobro` no valida la coherencia de los importes para el método `mixto`. Se puede registrar `metodo_cobro='mixto'` con `importe_efectivo=None` e `importe_tarjeta=None`, lo que haría que el cierre de caja compute ceros para ese reparto sin ningún aviso.

**Evidencia:**
```python
# líneas 17-47
def registrar_cobro(
    self,
    reparto_id: int,
    metodo_cobro: str,
    importe_cobrado: float,
    cambio_devuelto: float | None = None,
    importe_efectivo: float | None = None,
    importe_tarjeta: float | None = None,
) -> tuple:
    METODOS_VALIDOS = {'efectivo', 'tarjeta', 'mixto'}
    if metodo_cobro not in METODOS_VALIDOS:
        return False, ...
    # No hay validación adicional por método
```

**Impacto real:** Un cobro `mixto` con ambos importes parciales a `None` pasa la validación y se persiste. El cierre de caja (líneas 99–100) hace `float(r.importe_efectivo or 0)`, silenciando el error. El repartidor aparece con cobro registrado pero con importe real 0.

**Recomendación mínima concreta:** Añadir validación condicional:
```python
if metodo_cobro == 'mixto' and (importe_efectivo is None or importe_tarjeta is None):
    return False, "Para método mixto debes indicar importe_efectivo e importe_tarjeta"
```

---

### Hallazgo 3

**Tipo:** consistencia / idempotencia  
**Severidad:** Media

**Problema:** `registrar_cobro` no es idempotente: si se llama dos veces (reintento del cliente web, doble click, o reintento del webhook de Meta), sobreescribe silenciosamente el cobro anterior sin avisar. No hay ningún flag ni timestamp de "cobro ya registrado".

**Evidencia:**
```python
# líneas 37-42
reparto.metodo_cobro     = metodo_cobro
reparto.importe_cobrado  = importe_cobrado
reparto.cambio_devuelto  = cambio_devuelto
reparto.importe_efectivo = importe_efectivo
reparto.importe_tarjeta  = importe_tarjeta
s.commit()
return True, "Cobro registrado"
```

**Impacto real:** Si el repartidor registra un cobro en efectivo y por error pulsa dos veces (segunda llamada con datos diferentes), el segundo cobro sobreescribe el primero sin rastro. En liquidación, la discrepancia no es detectable.

**Recomendación mínima concreta:** Verificar si `reparto.metodo_cobro is not None` antes de sobreescribir y devolver advertencia. O añadir un `updated_at` a la tabla `Reparto` para tener trazabilidad.

---

### Hallazgo 4

**Tipo:** diseño / lógica de negocio  
**Severidad:** Media

**Problema:** `cierre_caja_repartidor` contiene lógica de inferencia de método de pago (líneas 89–94) que es lógica de negocio, no acceso a datos. Infiere si un pedido es "online" basándose en la existencia de un pago completado o el campo `forma_pago`. Esta lógica debería estar en un controller o helper, no en un mixin de manager.

**Evidencia:**
```python
# líneas 89-94
pago_ok = next((p for p in pedido.pagos if p.estado == 'completado'), None)
if pago_ok or getattr(pedido, 'forma_pago', 'online') == 'online':
    online_list.append(r)
else:
    sin_registro.append(r)
```
El `getattr(pedido, 'forma_pago', 'online')` usa `'online'` como default, lo que significa que cualquier pedido sin `forma_pago` y sin pago completado se clasifica como online. Esta es una decisión de negocio no documentada.

**Impacto real:** Si un pedido contra reembolso no tiene `forma_pago` seteado correctamente (bug de datos), se clasifica como online y el repartidor parece no tener efectivo que entregar. En la liquidación, el local perdería ese cobro.

**Recomendación mínima concreta:** Extraer la función de clasificación de pago a un helper con nombre explícito y documentar el default. Al menos cambiar el default de `getattr` a `None` y tratar ese caso explícitamente en `sin_registro`.

---

### Hallazgo 5

**Tipo:** observabilidad  
**Severidad:** Media

**Problema:** `cierre_caja_repartidor` no tiene ningún logging. Si el resumen devuelve totales incorrectos (por ejemplo, `sin_registro` > 0), no hay registro que ayude a diagnosticar qué repartos fallaron la clasificación.

**Evidencia:** Líneas 49–140 — ningún `logger.info` ni `logger.warning` en la función entera.

**Impacto real:** En producción, si el cierre de caja muestra discrepancias, no hay forma de determinar la causa sin ejecutar la query manualmente.

**Recomendación mínima concreta:** Añadir al menos:
```python
if sin_registro:
    logger.warning("cierre_caja repartidor %s: %d repartos sin cobro registrado", repartidor_id, len(sin_registro))
```

---

### Hallazgo 6

**Tipo:** seguridad  
**Severidad:** Baja

**Problema:** `registrar_cobro` acepta `importe_cobrado: float` sin validar que sea positivo. Un importe negativo o cero pasaría la validación de método y se persistiría, generando un cierre de caja con totales incorrectos.

**Evidencia:**
```python
# línea 22
importe_cobrado: float,
# No hay: if importe_cobrado <= 0: return False, "Importe inválido"
```

**Impacto real:** En un escenario de error de UI o llamada malformada, un cobro de -50€ reduciría el total de efectivo del cierre. Impacto financiero directo.

**Recomendación mínima concreta:**
```python
if importe_cobrado <= 0:
    return False, "El importe cobrado debe ser positivo"
```

---

### Hallazgo 7

**Tipo:** rendimiento  
**Severidad:** Baja

**Problema:** `cierre_caja_repartidor` carga todos los `Reparto` con sus `pedido`, `cliente` y `pagos` en Python y hace la clasificación y agregación en memoria (líneas 78–106). Para un repartidor con muchos pedidos históricos en un día, todo el cómputo es en Python.

**Evidencia:** Líneas 57–73 cargan todos los repartos del día. Las sumas (líneas 97–106) son `sum(...)` en Python sobre listas cargadas en memoria.

**Impacto real:** Con volúmenes normales de un restaurante (10–50 pedidos/día por repartidor), es completamente aceptable. No es urgente.

**Recomendación mínima concreta:** No tocar hasta que los volúmenes crezcan. Si se necesita optimizar, las sumas se pueden delegar a `func.sum()` en SQL con `GROUP BY`.

---

## 4. Riesgos principales si no se toca

| Riesgo | Escenario concreto |
|--------|-------------------|
| Cobro registrado en estado incorrecto | El blueprint llama `registrar_cobro` antes de `marcar_entregado`; el cierre de caja no lo incluye pero los datos quedan escritos; en un reintento el cobro se sobreescribe con valores distintos |
| Cobro mixto con importes nulos | Repartidor registra cobro mixto desde UI con un campo vacío; los 0€ se persisten y el cierre de caja reporta menos efectivo del real |
| Pedido contra reembolso sin `forma_pago` | Bug de datos upstream; el repartidor tiene efectivo que no aparece en el cierre; el local pierde dinero sin saberlo |
| Doble registro de cobro | Reintento de frontend sobreescribe el primer cobro sin traza; discrepancia en liquidación no detectable |

---

## 5. Refactor mínimo recomendado

### Qué tocar primero (en orden de impacto)
1. **Hallazgo 1:** Añadir guarda de `reparto.estado == ENTREGADO` en `registrar_cobro`. Una línea, impacto de integridad máximo.
2. **Hallazgo 2:** Validar que en método `mixto` ambos importes parciales estén presentes.
3. **Hallazgo 6:** Validar que `importe_cobrado > 0`.
4. **Hallazgo 5:** Añadir logging de `sin_registro` en `cierre_caja_repartidor`.

### Qué NO tocar todavía
- La lógica de agregación en Python (Hallazgo 7) — funciona correctamente a estos volúmenes.
- El eager loading — está bien configurado y evita N+1.
- La estructura de retorno de `cierre_caja_repartidor` — el blueprint y el frontend ya consumen este contrato.

---

## 6. Tests que deberían existir

- `test_registrar_cobro_estado_invalido` — reparto en `ASIGNADO` devuelve error
- `test_registrar_cobro_metodo_invalido` — método desconocido devuelve error sin tocar DB
- `test_registrar_cobro_importe_negativo` — importe <= 0 devuelve error
- `test_registrar_cobro_mixto_sin_importes_parciales` — mixto con importe_efectivo=None devuelve error
- `test_registrar_cobro_idempotente` — segunda llamada con datos diferentes devuelve advertencia
- `test_cierre_caja_clasifica_efectivo_correctamente` — reparto efectivo aparece en total_efectivo
- `test_cierre_caja_clasifica_mixto_correctamente` — reparto mixto suma correctamente a efectivo y tarjeta
- `test_cierre_caja_sin_registro_cuando_forma_pago_none` — pedido sin forma_pago y sin pago completado va a sin_registro, no a online
- `test_cierre_caja_rango_fecha` — solo repartos dentro del día solicitado se incluyen

---

## 7. Veredicto final

**Estado general del archivo:** Funcional pero con huecos de validación que tienen impacto financiero directo. El código es limpio y legible, pero asume que el caller ya valida el estado y los importes, lo que es una suposición peligrosa en un contexto de cobros.

**¿Bloquea crecimiento?** No, pero añadir nuevos métodos de cobro (p.ej. Bizum) requeriría refactorizar la whitelist y la lógica de clasificación en varios puntos.

**¿Bloquea testeo?** No. El mixin es testeable con una sesión mockeada.

**¿Tiene riesgo operativo real?** Sí. Un cobro registrado con importe nulo o en estado incorrecto puede producir un cierre de caja con discrepancias financieras que no son detectables sin consulta manual a la DB.
