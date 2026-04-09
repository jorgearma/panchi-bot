# Auditoría de `managers/pedidos/lifecycle_mixin.py`

> Auditoría técnica estricta. Fecha: 2026-04-09.
> Archivos analizados: `managers/pedidos/lifecycle_mixin.py`, `managers/pedidos/base.py`, `managers/pedidos/workflow_mixin.py`, `states.py`, `models.py` (parcial: clases Pedido, PedidoDetalle, Producto).

---

## 1. Rol del archivo

**Responsabilidad principal:** Ciclo de vida temprano del pedido — creación, transición a ENLACE, adición de líneas de producto, confirmación de pago online y efectivo, y consulta de seguimiento.

**Qué debería hacer:** Operaciones atómicas de escritura en DB para los estados PENDIENTE → ENLACE → ENLACE2 → CONFIRMANDO_PAGO / CONTRA_REEMBOLSO. Consultas de lectura básicas (pedido por id, pedido activo del usuario).

**Qué no debería hacer:** Proyecciones de datos para vistas públicas (eso pertenece a una capa de lectura o mixin de consultas). Validación de inputs de usuario (eso es responsabilidad del schema o del controller).

**Dependencias clave:**
- `workflow_mixin.py` → `_set_estado`, `_asegurar_picking_si_procede` (acoplamiento implícito via MRO)
- `base.py` → `_to_decimal`, `self.session` (acoplamiento implícito via MRO)
- `states.py` → `ESTADOS_TERMINALES_PEDIDO`, `EstadoPedido`
- `models.py` → `Pedido`, `PedidoDetalle`, `Producto`

**Nivel de criticidad:** Crítico — toda transacción de dinero y toda creación de pedido pasan por este archivo.

---

## 2. Lo que hace bien

- **Atomicidad en operaciones compuestas:** `iniciar_enlace` (l.38-58), `confirmar_pago_online` (l.196-228) y `confirmar_pago_efectivo` (l.230-264) combinan múltiples cambios en un solo `commit`. Reemplaza el antipatrón de dos commits separados que dejaba estado inconsistente.
- **`_reemplazar_detalles` es idempotente** (l.114-161): borra las líneas existentes antes de insertar, por lo que reintentos del worker RQ no producen líneas duplicadas.
- **`tenacity` en rutas críticas:** `iniciar_pedido`, `iniciar_enlace`, `hay_pedido_pendiente`, `obtener_pedido_mas_reciente`, `confirmar_pago_online`, `confirmar_pago_efectivo` tienen `@retry` con 3 intentos y `wait_fixed(1)`.
- **Rollback explícito en todos los bloques `except`:** ningún error se descarta sin `session.rollback()`.
- **`obtener_pedido_mas_reciente` excluye estados terminales correctamente** (l.97-112): usa `ESTADOS_TERMINALES_PEDIDO` del módulo centralizado.

---

## 3. Hallazgos

### Hallazgo 1

**Tipo:** rendimiento  
**Severidad:** Alta

**Problema:** `_reemplazar_detalles` ejecuta un `SELECT Producto` individual por cada línea de producto dentro de un bucle.

**Evidencia:**
```python
# lifecycle_mixin.py líneas 134–154
for item in productos:
    producto_id = item["producto_id"]
    ...
    producto = self.session.query(Producto).filter_by(   # ← query dentro del loop
        ProductoID=producto_id,
    ).first()
```

**Impacto real:** Un pedido con 8 productos lanza 8 SELECTs seriales contra SQL Server. Bajo carga concurrente o ante pedidos grandes, esto multiplica la latencia de confirmación de pago. Este método es invocado desde `confirmar_pago_online` y `confirmar_pago_efectivo`, ambos en la ruta crítica de checkout.

**Recomendación mínima concreta:** Extraer todos los `producto_id` de la lista antes del bucle y hacer un único `WHERE ProductoID IN (...)`. Construir un dict `{id: producto}` para el lookup en O(1).

```python
ids = [item["producto_id"] for item in productos]
productos_db = {
    p.ProductoID: p
    for p in self.session.query(Producto).filter(Producto.ProductoID.in_(ids)).all()
}
```

---

### Hallazgo 2

**Tipo:** consistencia  
**Severidad:** Alta

**Problema:** `agregar_productos_a_pedido` (l.163-189) no tiene decorador `@retry`, a diferencia de todos los demás métodos de escritura del mixin.

**Evidencia:**
```python
# lifecycle_mixin.py línea 163 — sin @retry
def agregar_productos_a_pedido(self, pedido_id, productos):
    ...
    try:
        self.session.commit()
        return True
    except (SQLAlchemyError, OperationalError) as error:
        self.session.rollback()
        logger.error(...)
        raise   # ← re-lanza pero sin reintento automático
```

Comparar con `iniciar_pedido` (l.12-16) que sí tiene `@retry(stop=stop_after_attempt(3), wait=wait_fixed(1), ...)`.

**Impacto real:** Un fallo transitorio de SQL Server al reemplazar líneas de producto no se reintenta. El job RQ fallará y dependerá del mecanismo de retry de RQ (si está configurado), no del de tenacity. Puede dejar el pedido sin líneas de producto si `_reemplazar_detalles` borró las antiguas pero el commit falló.

**Recomendación mínima concreta:** Añadir el mismo decorador `@retry` que usan los métodos adyacentes.

---

### Hallazgo 3

**Tipo:** validación  
**Severidad:** Media

**Problema:** `_reemplazar_detalles` no valida que `cantidad > 0`. Una cantidad negativa o cero produce un subtotal negativo que reduce el `Total` del pedido.

**Evidencia:**
```python
# lifecycle_mixin.py línea 135–154
cantidad = item["cantidad"]   # ← sin validación
...
subtotal = precio_unitario * cantidad   # subtotal negativo si cantidad < 0
total += subtotal
```

**Impacto real:** Si un ítem llega con `cantidad: -1` (manipulación del carrito en JS o bug en el cliente), el total del pedido se reduce. El módulo de validación de precios en `/api/agregar_pedido` puede no cubrir este caso dependiendo de su implementación.

**Recomendación mínima concreta:** Añadir un guard antes de construir el detalle:
```python
if not isinstance(cantidad, int) or cantidad <= 0:
    logger.warning("_reemplazar_detalles: cantidad inválida %s para producto %s", cantidad, producto_id)
    continue
```

---

### Hallazgo 4

**Tipo:** consistencia  
**Severidad:** Media

**Problema:** `obtener_seguimiento` (l.266-293) accede a `pedido.reparto` y `pedido.reparto.repartidor` via lazy loading sin ningún try/except. Si la sesión está expirada o el objeto está detached, lanza `DetachedInstanceError` que no se captura aquí.

**Evidencia:**
```python
# lifecycle_mixin.py líneas 273–288
if pedido.reparto:                           # lazy load #1
    r = pedido.reparto
    if r.repartidor:                          # lazy load #2
        repartidor_nombre = f"{r.repartidor.Nombre} {r.repartidor.Apellido}"  # lazy load #3
```

**Impacto real:** La página de tracking del cliente falla con 500 si la sesión SQLAlchemy expira entre la query del pedido y el acceso al reparto. No se registra el error.

**Recomendación mínima concreta:** Envolver el método en try/except SQLAlchemyError con log de error. Considerar usar `joinedload` en la query de `obtener_seguimiento` para evitar lazy loading.

---

### Hallazgo 5

**Tipo:** observabilidad  
**Severidad:** Media

**Problema:** Los eventos de negocio más importantes del sistema no tienen `logger.info` en el path de éxito.

**Evidencia:**
- `iniciar_pedido` (l.17-31): sin log de éxito tras `commit()` — no hay traza de qué `PedidoID` se creó.
- `confirmar_pago_online` (l.196-228): sin log de éxito — una confirmación de pago online no deja traza en logs.
- `confirmar_pago_efectivo` (l.230-264): igual.
- `agregar_productos_a_pedido` (l.163-189): sin log de éxito.

Contraste: `iniciar_enlace` sí tiene `logger.info("ENLACE_INICIADO pedido_id=%s", pedido_id)` en l.54.

**Impacto real:** Al depurar un pedido fallido no se puede reconstruir la secuencia de eventos desde los logs de aplicación.

**Recomendación mínima concreta:** Añadir `logger.info` en el `return True` de `iniciar_pedido`, `confirmar_pago_online` y `confirmar_pago_efectivo` con el `pedido_id`.

---

### Hallazgo 6

**Tipo:** diseño  
**Severidad:** Baja

**Problema:** `obtener_seguimiento` (l.266-293) es una proyección de lectura para la vista pública de tracking. No forma parte del "ciclo de vida" del pedido — no escribe, no transiciona estado, no toca PedidoDetalle. Su presencia aquí mezcla responsabilidades de escritura y lectura en el mismo mixin.

**Evidencia:** El método devuelve un dict con `estado`, `forma_pago` y datos de reparto (l.289-293). No llama a ningún otro método del mixin ni modifica estado.

**Impacto real:** Bajo (semántico). No introduce bugs, pero hace el mixin más difícil de razonar.

**Recomendación mínima concreta:** Posible riesgo no confirmado si existe un mixin de consultas separado. Si el proyecto crece, moverlo a un `queries_mixin.py` o similar.

---

### Hallazgo 7

**Tipo:** testabilidad / acoplamiento  
**Severidad:** Baja

**Problema:** El mixin llama a `self._set_estado` (l.51, 217, 253) y `self._to_decimal` (l.129, 131, 143-144, 153) que están definidos en mixins hermanos (`workflow_mixin` y `base`), sin que ninguna interfaz ni docstring documente este contrato.

**Evidencia:**
```python
# lifecycle_mixin.py línea 51
if not self._set_estado(pedido, EstadoPedido.ENLACE):  # definido en workflow_mixin.py
```

**Impacto real:** Para testear `lifecycle_mixin` en aislamiento hay que componer manualmente una clase con todos los mixins o mockear `_set_estado` y `_to_decimal` explícitamente. Sin documentación del contrato, un desarrollador que refactorice `workflow_mixin` puede romper `lifecycle_mixin` sin que los tests de la clase aislada lo detecten.

**Recomendación mínima concreta:** Añadir un comentario de clase que documente las dependencias MRO. No es necesario cambiar la estructura.

---

## 4. Riesgos principales si no se toca

| Riesgo | Escenario concreto |
|---|---|
| N+1 en checkout | Un pedido de 10 productos bajo carga provoca 10 SELECTs seriales a SQL Server en la confirmación de pago |
| Subtotal negativo | Un carrito manipulado con `cantidad: -1` reduce el Total del pedido sin que el mixin lo detecte |
| Fallo silencioso en `agregar_productos_a_pedido` | Un corte transitorio de SQL Server deja el pedido sin líneas y el método no se reintenta automáticamente |
| 500 en tracking del cliente | Sesión SQLAlchemy expirada al acceder a `reparto.repartidor` lanza `DetachedInstanceError` no capturado |
| Imposible reconstruir audit trail | Sin `logger.info` en confirmaciones de pago, un pedido fantasma no tiene traza de cuándo se confirmó |

---

## 5. Refactor mínimo recomendado

### Qué tocar primero (en orden de impacto)

1. **Hallazgo 1 (N+1):** Reemplazar el `query(Producto)` en el loop por un `query(...).filter(Producto.ProductoID.in_(ids))` antes del loop. Es un cambio de 5 líneas con alto impacto en rendimiento.
2. **Hallazgo 2 (retry):** Añadir `@retry(stop=stop_after_attempt(3), wait=wait_fixed(1), retry=retry_if_exception_type((SQLAlchemyError, OperationalError)))` a `agregar_productos_a_pedido`. Una línea.
3. **Hallazgo 3 (cantidad):** Añadir el guard de `cantidad <= 0` en `_reemplazar_detalles`.

### Qué NO tocar todavía

- La estructura de mixins: funciona, no introduce bugs.
- `obtener_seguimiento`: moverlo es refactor semántico, no urgente.
- Los `@retry` existentes: no modificarlos.
- La lógica de atomicidad en `confirmar_pago_online` / `confirmar_pago_efectivo`: está bien diseñada.

---

## 6. Tests que deberían existir

- `test_reemplazar_detalles_cantidad_cero_se_ignora` — verifica que un item con `cantidad=0` no genera PedidoDetalle ni afecta Total.
- `test_reemplazar_detalles_cantidad_negativa_se_ignora` — mismo con `cantidad=-1`.
- `test_reemplazar_detalles_una_sola_query_productos` — verifica que se emiten exactamente 2 queries (DELETE + SELECT IN) para N productos, no N+2.
- `test_agregar_productos_reintenta_en_sqlerror` — mockea `session.commit` para lanzar `SQLAlchemyError` en el primer intento y verifica que se reintenta.
- `test_confirmar_pago_online_atomico` — verifica que si `_set_estado` falla, no se hace commit de los detalles.
- `test_obtener_seguimiento_sin_reparto` — pedido sin reparto asociado devuelve `reparto: None` sin excepción.
- `test_obtener_seguimiento_session_expirada` — verifica que un `DetachedInstanceError` en el acceso a `reparto` se captura y no propaga como 500.

---

## 7. Veredicto final

**Estado general del archivo:** Sólido en su diseño de atomicidad. Los métodos principales de escritura son seguros frente a interrupciones. Los problemas encontrados son puntuales, no estructurales.

**¿Bloquea crecimiento?** No. La separación en mixins es correcta y extensible.

**¿Bloquea testeo?** Parcialmente. El acoplamiento implícito con sibling mixins requiere composición manual en tests. Resoluble sin refactorizar la arquitectura.

**¿Tiene riesgo operativo real?** Sí, dos riesgos concretos: el N+1 bajo carga en checkout (rendimiento degradado en horas pico) y la ausencia de `@retry` en `agregar_productos_a_pedido` (posible estado inconsistente ante fallo transitorio de SQL Server).
