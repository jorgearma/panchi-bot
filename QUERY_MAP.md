# QUERY_MAP.md

> Catálogo técnico de todas las queries SQLAlchemy relevantes de **panchi-bot** — rendimiento, N+1, índices y mejoras.

---

## Índice

1. [Resumen Ejecutivo](#1-resumen-ejecutivo)
2. [managers/gestor_pedidos.py](#2-managersggestor_pedidospy)
3. [managers/gestor_usuarios.py](#3-managersgestor_usuariospy)
4. [managers/gestor_productos.py](#4-managersgestor_productospy)
5. [managers/gestor_empleado.py](#5-managersgestor_empleadopy)
6. [managers/gestor_dashboard.py](#6-managersgestor_dashboardpy)
7. [managers/gestor_metricas.py](#7-managersgestor_metricaspy)
8. [blueprints/api.py](#8-blueprintsapipy)
9. [Problemas Globales](#9-problemas-globales)
10. [Índices Recomendados](#10-índices-recomendados)

---

## 1. Resumen Ejecutivo

| Categoría                     | Count |
|-------------------------------|-------|
| Total queries identificadas   | ~150+ |
| N+1 confirmados               | 5     |
| SELECT sin límite en tablas grandes | 8 |
| Lazy loads en cadena          | 3     |
| Queries en hot path (cada mensaje WhatsApp) | 4 |
| Queries en polling (dashboard cada N seg)   | 12+ |
| Columnas sin índice filtradas frecuentemente | 6 |

**Archivos más críticos:** `gestor_dashboard.py` (121 KB, god object), `gestor_metricas.py` (1209 líneas).

---

## 2. managers/gestor_pedidos.py

### Q-001 — `iniciar_pedido()`
**Trigger:** `POST /webhook` (primer mensaje de pedido)
**Frecuencia:** Media | **Coste:** Bajo

```python
session.add(nuevo_pedido)
session.commit()
```

| Operación | Tablas    | Filtros | Índices |
|-----------|-----------|---------|---------|
| INSERT    | `pedidos` | —       | PK auto |

Decorador `@retry` (3 intentos). Sin problemas.

---

### Q-002 — `hay_pedido_pendiente()`
**Trigger:** `POST /webhook` — cada mensaje de usuario registrado
**Frecuencia:** Alta | **Coste:** Medio ⚠️

```python
session.query(Pedido)
    .filter_by(ClienteID=cliente_id, Estado=EstadoPedido.PENDIENTE)
    .first()
```

| Operación | Tablas    | Filtros                    | Índices disponibles |
|-----------|-----------|----------------------------|---------------------|
| SELECT    | `pedidos` | `ClienteID`, `Estado`      | Solo PK             |

**Problemas:**
- Sin índice en `ClienteID` → full scan en tabla `pedidos`
- Sin índice en `Estado` → compuesto con ClienteID sería ideal
- Se ejecuta en cada mensaje WhatsApp (hot path)

**Mejora:** `CREATE INDEX ix_pedidos_cliente_estado ON pedidos (ClienteID, Estado)`

---

### Q-003 — `obtener_pedido_mas_reciente()`
**Trigger:** `POST /webhook`, `GET /menu/<token>`, `GET /api/seguimiento`
**Frecuencia:** Alta | **Coste:** Medio ⚠️

```python
session.query(Pedido)
    .filter(Pedido.ClienteID == id_usuario)
    .filter(Pedido.Estado.notin_(estados_excluidos))  # lista de 3 estados terminales
    .order_by(Pedido.FechaCreacion.desc())
    .first()
```

| Operación | Tablas    | Filtros                       | Order By         | Índices disponibles |
|-----------|-----------|-------------------------------|------------------|---------------------|
| SELECT    | `pedidos` | `ClienteID`, `Estado NOT IN`  | `FechaCreacion DESC` | Solo PK         |

**Problemas:**
- `NOT IN` sobre lista de estados no puede usar índice de igualdad eficientemente
- `ORDER BY FechaCreacion DESC` sin índice → sort en memoria
- Hot path (cada webhook)

**Mejora:** Índice compuesto `(ClienteID, FechaCreacion DESC)` + filtrar solo estados activos conocidos en vez de `NOT IN` terminales.

---

### Q-004 — `agregar_productos_a_pedido()` ⛔ N+1
**Trigger:** `POST /api/agregar_pedido`
**Frecuencia:** Media | **Coste:** Alto ⚠️⚠️

```python
# Loop por cada producto del carrito:
for item in carrito:
    producto = session.query(Producto)
        .filter_by(ProductoID=item['id'])
        .first()   # ← query dentro del loop
    # ... validar precio y crear PedidoDetalle

session.add_all(detalles)
session.commit()
```

| Operación | Tablas                         | N+1 |
|-----------|--------------------------------|-----|
| SELECT x N | `productos` (uno por item)   | ✅ SÍ |
| INSERT batch | `pedido_detalles`           | No  |

**Problemas:**
- N queries a `productos` donde N = cantidad de ítems en el carrito
- Típico carrito: 3-8 ítems → 3-8 queries en serie

**Mejora:**
```python
ids = [item['id'] for item in carrito]
productos = session.query(Producto).filter(Producto.ProductoID.in_(ids)).all()
productos_map = {p.ProductoID: p for p in productos}
```

---

### Q-005 — `actualizar_estado()` (cadena de queries)
**Trigger:** Cada cambio de estado (webhook Monei, picker, repartidor, dashboard)
**Frecuencia:** Media | **Coste:** Medio

```python
# 1. Cargar pedido
pedido = session.query(Pedido).filter_by(PedidoID=pedido_id).first()
# 2. Insertar historial
session.add(HistorialEstadoPedido(...))
# 3. (Condicional) _asegurar_picking_si_procede()
picking = session.query(PickingPedido).filter_by(pedido_id=pedido_id).first()
# 4. (Si no existe picking) INSERT picking + loop de PickingItems
session.add(picking)
session.flush()
for detalle in pedido.detalles:  # ← lazy load de detalles
    session.add(PickingItem(...))
```

| Operación | Tablas                                                | Notas                         |
|-----------|-------------------------------------------------------|-------------------------------|
| SELECT    | `pedidos`                                             |                               |
| INSERT    | `historial_estados_pedido`                            |                               |
| SELECT    | `picking_pedido`                                      |                               |
| SELECT    | `pedido_detalles` (lazy load via `pedido.detalles`)   | Lazy load implícito           |
| INSERT x N| `picking_items`                                       | Un INSERT por detalle del pedido |

**Problemas:**
- Lazy load de `pedido.detalles` dispara query adicional no explícita
- El loop de INSERT de `picking_items` hace N adds individuales (aunque van en un commit)

**Mejora:** Hacer eager load de detalles en el SELECT inicial: `.options(joinedload(Pedido.detalles))`

---

### Q-006 — `_recalcular_total()`
**Trigger:** `eliminar_item()`, `sustituir_item()`
**Frecuencia:** Baja | **Coste:** Bajo

```python
session.query(PedidoDetalle)
    .filter_by(PedidoID=pedido.PedidoID)
    .all()
```

Carga todos los detalles para sumar en Python. Sin problemas dado el volumen esperado (< 20 ítems por pedido). Sin índice en `PedidoID` de `pedido_detalles` pero frecuencia baja.

---

### Q-007 — `guardar_enlace()`, `guardar_forma_pago()`, `guardar_coordenadas()`, `guardar_redis_id()`
**Trigger:** Flujo de creación de pedido
**Frecuencia:** Media | **Coste:** Bajo

```python
# Patrón repetido 4 veces:
session.query(Pedido).filter_by(PedidoID=pedido_id).first()
# ... update campo específico
session.commit()
```

**Problema:** Cuatro funciones separadas que hacen SELECT + UPDATE sobre el mismo registro, generando 4 round trips a la BD en el flujo de creación de un pedido. Podrían consolidarse en una sola función `actualizar_campos_pedido(**kwargs)`.

---

### Q-008 — `cancelar_pedido()`
**Trigger:** Dashboard (admin cancela)
**Frecuencia:** Baja | **Coste:** Bajo

```python
pedido = s.query(Pedido).filter_by(PedidoID=pedido_id).first()
s.add(HistorialEstadoPedido(...))
s.add(AuditLog(...))
s.commit()
```

Sin problemas. Frecuencia baja, todas las operaciones sobre PK.

---

## 3. managers/gestor_usuarios.py

### Q-009 — `verificar_usuario()`
**Trigger:** `POST /webhook` — cada mensaje entrante de WhatsApp
**Frecuencia:** Alta | **Coste:** Bajo–Medio ⚠️

```python
session.query(Usuario)
    .filter_by(numero_cliente=numero_cliente)
    .scalar()
```

| Operación | Tablas     | Filtros          | Índices disponibles   |
|-----------|------------|------------------|-----------------------|
| SELECT    | `usuarios` | `numero_cliente` | UNIQUE constraint ✅  |

`numero_cliente` tiene `unique=True` en el modelo → SQL Server crea índice único automáticamente. Sin problemas de rendimiento.

---

### Q-010 — `obtener_usuario()` / `obtener_usuario_completo()`
**Trigger:** Flujo de registro y mensajes registrados
**Frecuencia:** Alta | **Coste:** Bajo

```python
session.query(Usuario)
    .filter_by(numero_cliente=numero_cliente)
    .first()
```

Mismo patrón que Q-009, mismo índice. Sin problemas.

---

## 4. managers/gestor_productos.py

### Q-011 — `obtener_productos()`
**Trigger:** `GET /api/productos` (carga del menú)
**Frecuencia:** Alta | **Coste:** Medio ⚠️

```python
session.query(Producto).all()
```

| Operación | Tablas      | Filtros                | Resultado |
|-----------|-------------|------------------------|-----------|
| SELECT *  | `productos` | Ninguno                | `.all()`  |

**Problemas:**
- Carga **todos** los productos incluyendo los `Disponible=False`
- No hay caché — cada carga del menú por cualquier cliente genera esta query
- `SELECT *` carga `ImagenURL`, `Descripcion`, `Ingredientes`, `Ubicacion` aunque el menú no los use todos
- Si hay 200 productos, carga 200 filas completas por cada `/api/productos`

**Mejora:**
1. Filtrar `Disponible=True` y `Stock > 0` en la query
2. Añadir caché Redis con TTL de 60s para el catálogo
3. Seleccionar solo columnas necesarias para el menú: `ProductoID`, `Nombre`, `Precio`, `Categoria`, `ImagenURL`, `Descuento`, `Disponible`

---

### Q-012 — `productos_admin()`
**Trigger:** `GET /productos-admin`
**Frecuencia:** Baja | **Coste:** Bajo

```python
session.query(Producto)
    .order_by(Producto.Categoria, Producto.Nombre)
    .all()
```

`ORDER BY Categoria` usa la columna legacy (`Categoria` texto), no `categoria_id`. Sin índice en esa columna → sort en memoria. Frecuencia baja, aceptable.

---

### Q-013 — `descontar_stock_picking()` ⛔ N+1
**Trigger:** `POST /picker/picking/<id>/finalizar`
**Frecuencia:** Media | **Coste:** Alto ⚠️⚠️

```python
for item in items_picking:
    producto = s.query(Producto)
        .filter_by(ProductoID=item["producto_id"])
        .first()  # ← query dentro del loop
    producto.Stock -= item["cantidad_encontrada"]
s.commit()
```

| Operación  | Tablas      | N+1 |
|------------|-------------|-----|
| SELECT x N | `productos` | ✅ SÍ |
| UPDATE x N | `productos` | (en memoria, un commit) |

**Mejora:** Cargar todos los productos en una query + bulk update, o usar `UPDATE productos SET Stock = Stock - X WHERE ProductoID = Y` via `session.execute()`.

---

## 5. managers/gestor_empleado.py

### Q-014 — `carga_operativa()`
**Trigger:** `GET /empleado/carga-operativa` (al cargar el hub del empleado)
**Frecuencia:** Alta | **Coste:** Bajo–Medio

```python
# 4 queries COUNT independientes:
s.query(func.count(PickingPedido.id)).filter(estado == PENDIENTE).scalar()
s.query(func.count(PickingPedido.id)).filter(estado == EN_PROCESO).scalar()
s.query(func.count(Reparto.id)).filter(estado == PENDIENTE).scalar()
s.query(func.count(Reparto.id)).filter(estado == EN_CAMINO).scalar()
```

**Problema:** 4 queries separadas donde podría hacerse con 2 usando `GROUP BY estado`:

```python
# Alternativa eficiente:
s.query(PickingPedido.estado, func.count(PickingPedido.id))
    .filter(PickingPedido.estado.in_([PENDIENTE, EN_PROCESO]))
    .group_by(PickingPedido.estado)
    .all()
```

Sin índice en `picking_pedido.estado` ni `repartos.estado`.

---

### Q-015 — `metricas_hoy()`
**Trigger:** `GET /empleado/metricas` (al cargar hub)
**Frecuencia:** Alta | **Coste:** Medio ⚠️

```python
# Para picker:
pickings = s.query(PickingPedido).filter(
    empleado_id == id,
    estado == COMPLETADO,
    completado_en >= hoy
).all()

ids = [p.id for p in pickings]
incidencias = s.query(func.count(PickingItem.id)).filter(
    PickingItem.picking_id.in_(ids),  # ← IN sobre lista variable
    estado.in_(['sin_stock', 'sustituido'])
).scalar()
```

**Problemas:**
- `IN` sobre lista de IDs dinámica — si hay muchos pickings del día puede ser lento
- Podría resolverse con un JOIN directo en vez de dos queries

**Mejora:**
```python
s.query(func.count(PickingItem.id)).join(PickingPedido).filter(
    PickingPedido.empleado_id == id,
    PickingPedido.estado == COMPLETADO,
    PickingPedido.completado_en >= hoy,
    PickingItem.estado.in_(['sin_stock', 'sustituido'])
).scalar()
```

---

### Q-016 — `_checkin_abierto_hoy()` (helper llamado múltiples veces)
**Trigger:** `cambiar_estado()`, `cambiar_rol()`, `iniciar_turno()`, `cerrar_turno()`, `checkin_hoy()`
**Frecuencia:** Alta | **Coste:** Bajo

```python
session.query(CheckIn).filter(
    CheckIn.empleado_id == empleado_id,
    CheckIn.fecha == hoy,
    CheckIn.fin == None
).first()
```

Se invoca repetidamente dentro de la misma request en algunos flujos (por ejemplo `cambiar_rol()` llama `cambiar_estado()` que llama `_checkin_abierto_hoy()`, y luego `cambiar_rol()` también la llama directamente). Sin caché de resultado en la misma sesión.

---

### Q-017 — `calcular_y_guardar_metrica_diaria()`
**Trigger:** Cálculo programado de métricas
**Frecuencia:** Baja | **Coste:** Medio

```python
# DELETE + INSERT (upsert manual)
s.query(MetricaDiariaEmpleado).filter(...).delete()
s.add(metrica)
s.commit()
```

Patrón correcto para un upsert manual. Sin problemas graves. SQL Server soporta `MERGE` para atomicidad real, pero el patrón actual es funcional.

---

## 6. managers/gestor_dashboard.py

> Este archivo es un god object de 121 KB. Las queries están distribuidas en decenas de funciones. Se documentan los patrones y grupos más relevantes.

### Q-018 — `metricas()` — múltiples COUNTs separados
**Trigger:** `GET /dashboard/metricas` (polling del dashboard)
**Frecuencia:** Muy alta (polling cada ~5s) | **Coste:** Alto ⚠️⚠️⚠️

```python
# 8+ queries COUNT/SUM independientes:
s.query(func.count(Pedido.PedidoID)).filter(FechaCreacion >= hoy).scalar()
s.query(func.count(Pedido.PedidoID)).filter(Estado.in_(ESTADOS_OPERATIVOS)).scalar()
s.query(func.count(Pedido.PedidoID)).filter(Estado == EN_PREPARACION).scalar()
s.query(func.count(Pedido.PedidoID)).filter(Estado == EN_REPARTO).scalar()
s.query(func.count(Pedido.PedidoID)).filter(Estado == ENTREGADO, FechaActualizacion >= hoy).scalar()
s.query(func.count(PickingPedido.id)).filter(estado == EN_PROCESO).scalar()
s.query(func.count(Reparto.id)).filter(estado == EN_CAMINO).scalar()
s.query(func.sum(Pedido.Total)).filter(FechaCreacion >= hoy, Estado.in_(...)).scalar()
```

**Problemas:**
- 8 round trips por cada ciclo de polling del dashboard
- Sin índice en `pedidos.Estado`, `pedidos.FechaCreacion`, `pedidos.FechaActualizacion`
- Sin índice en `picking_pedido.estado`, `repartos.estado`
- Si el dashboard está abierto en 3 pantallas simultáneas → 24 queries/ciclo

**Mejora:**
1. Consolidar en un solo query con `CASE WHEN` + `GROUP BY`
2. Añadir caché Redis con TTL de 10s para estos contadores
3. Crear índice en `(FechaCreacion, Estado)` para los filtros más frecuentes

---

### Q-019 — `picking_activo()` ⛔ N+1
**Trigger:** `GET /dashboard` (carga principal del dashboard)
**Frecuencia:** Alta | **Coste:** Alto ⚠️⚠️

```python
pickings = s.query(PickingPedido).filter(
    estado.in_([PENDIENTE, EN_PROCESO])
).all()

for picking in pickings:
    # Query por cada picking:
    ultimo_estado = s.query(HistorialEstadoPedido).filter(
        pedido_id == picking.pedido_id
    ).order_by(cambiado_en.desc()).first()

    # Acceso lazy a picking.pedido → query implícita
    # Acceso lazy a picking.items → query implícita
```

**Problemas:**
- N queries a `historial_estados_pedido` donde N = pedidos activos
- Lazy loads de `picking.pedido` y `picking.items` → potencialmente 3N queries

**Mejora:**
```python
s.query(PickingPedido)
    .options(
        joinedload(PickingPedido.pedido),
        joinedload(PickingPedido.items),
    )
    .filter(estado.in_([PENDIENTE, EN_PROCESO]))
    .all()
# + subquery para último estado en vez de loop
```

---

### Q-020 — `rendimiento_empleados()` ⛔ N+1
**Trigger:** `GET /dashboard/rendimiento`
**Frecuencia:** Media | **Coste:** Muy alto ⚠️⚠️⚠️

```python
empleados = s.query(Empleado).all()  # ← todos los empleados

for empleado in empleados:
    # Query por empleado:
    pickings = s.query(PickingPedido).join(PickingItem).filter(
        empleado_id == empleado.EmpleadoID,
        fecha_range
    ).all()

    repartos = s.query(Reparto).filter(
        repartidor_id == empleado.EmpleadoID,
        fecha_range
    ).all()
```

**Problemas:**
- 2 queries por empleado → si hay 20 empleados: 40+ queries por request
- Sin paginación en la lista de empleados
- Sin índice en `picking_pedido.empleado_id`, `repartos.repartidor_id`

**Mejora:** Hacer JOIN directo en vez de loop, o al menos añadir filtro para empleados activos con actividad en el periodo.

---

### Q-021 — `estadisticas()` — queries de analítica sin límite
**Trigger:** `GET /dashboard/estadisticas`
**Frecuencia:** Baja–Media | **Coste:** Alto

```python
# Query 1: todos los pedidos del periodo
s.query(Pedido.Estado, func.count(Pedido.PedidoID))
    .filter(FechaCreacion.between(inicio, fin))
    .group_by(Pedido.Estado)
    .all()

# Query 2: tiempos de estados (join con historial)
s.query(Pedido, HistorialEstadoPedido)
    .join(...)
    .filter(fecha_range)
    .all()  # ← sin LIMIT

# Query 3: agrupación por fecha (cast de DateTime a Date)
s.query(func.cast(Pedido.FechaCreacion, Date), func.count(...))
    .filter(fecha_range)
    .group_by(func.cast(...))
    .all()
```

**Problemas:**
- `func.cast(Pedido.FechaCreacion, Date)` en `GROUP BY` impide uso de índice en `FechaCreacion`
- Join con `historial_estados_pedido` sin límite — puede ser muy costoso en periodos largos
- Sin paginación

---

### Q-022 — `turnos_hoy()` — join 3 tablas
**Trigger:** `GET /dashboard` (sección turnos)
**Frecuencia:** Alta | **Coste:** Medio

```python
s.query(Turno, Empleado, CheckIn)
    .join(Empleado, Turno.empleado_id == Empleado.EmpleadoID)
    .outerjoin(CheckIn, and_(
        CheckIn.empleado_id == Turno.empleado_id,
        CheckIn.fecha == hoy
    ))
    .filter(Turno.fecha == hoy)
    .all()
```

Join bien estructurado. Sin problemas graves. Índice en `turnos.fecha` sería útil.

---

### Q-023 — `buscar_pedidos_historial()` — sin paginación
**Trigger:** `GET /dashboard/historial`
**Frecuencia:** Media | **Coste:** Alto ⚠️

```python
query = s.query(Pedido)
if filtro_cliente:
    query = query.filter(Pedido.TelefonoEntrega.like(f'%{filtro}%'))
if filtro_estado:
    query = query.filter(Pedido.Estado == filtro_estado)
if filtro_fecha:
    query = query.filter(FechaCreacion.between(...))

return query.order_by(FechaCreacion.desc()).all()  # ← sin LIMIT
```

**Problemas:**
- `LIKE '%texto%'` no puede usar índice (wildcard al inicio)
- Sin `.limit()` — puede cargar miles de pedidos
- `ORDER BY FechaCreacion DESC` sin índice → sort en memoria

**Mejora:** Añadir `.limit(100).offset(page * 100)` + índice en `FechaCreacion`.

---

## 7. managers/gestor_metricas.py

### Q-024 — `dashboard_operacional()` — múltiples COUNTs
**Trigger:** `GET /metricas/operacion/*` (polling de métricas en tiempo real)
**Frecuencia:** Muy alta | **Coste:** Alto ⚠️⚠️

Similar a Q-018 pero para el blueprint de métricas operacionales. Múltiples queries COUNT separadas ejecutadas en cada ciclo de polling.

```python
# Pattern: 5-10 .scalar() calls per invocation
s.query(func.count(...)).filter(...).scalar()  # × 10
```

**Problemas idénticos a Q-018.** El hecho de tener dos blueprints (`metricas_operacion` y `metricas_analitica`) con sus propios gestores implica duplicación de lógica de conteo sobre las mismas tablas.

---

### Q-025 — `monitoreo_pickers()` ⛔ N+1
**Trigger:** `GET /metricas/operacion/pickers`
**Frecuencia:** Alta (polling) | **Coste:** Alto ⚠️⚠️

```python
pickings_activos = s.query(PickingPedido).filter(
    estado.in_([EN_PROCESO, PENDIENTE])
).all()

for picking in pickings_activos:
    # Query por cada picking activo:
    historial = s.query(HistorialEstadoPedido).filter(
        pedido_id == picking.pedido_id
    ).order_by(cambiado_en.desc()).first()
```

**N+1 confirmado.** Mismo patrón que Q-019 pero en el blueprint de métricas. Duplicación del problema.

---

### Q-026 — `analisis_periodo()` — queries analíticas pesadas
**Trigger:** `GET /metricas/analitica/*`
**Frecuencia:** Baja | **Coste:** Muy alto

```python
# Query 1: todos los pedidos del periodo (sin límite)
pedidos = s.query(Pedido).filter(FechaCreacion.between(inicio, fin)).all()

# Query 2: repartos del periodo
repartos = s.query(Reparto).filter(updated_at.between(inicio, fin)).all()

# Query 3: forma de pago (GROUP BY)
s.query(Pedido.forma_pago, func.count(...))
    .filter(fecha_range)
    .group_by(Pedido.forma_pago)
    .all()

# Query 4: picking + items (join)
s.query(PickingPedido).join(PickingItem).filter(fecha_range).all()
```

**Problemas:**
- `pedidos.all()` sin límite — periodo largo = miles de filas en memoria
- No hay paginación ni streaming
- `repartos.updated_at` sin índice

---

## 8. blueprints/api.py

### Q-027 — `GET /api/seguimiento/<redis_id>` — lazy loads en cadena
**Trigger:** Polling del cliente desde `ver_comandas.html`
**Frecuencia:** Muy alta (cada 5-10s por cliente esperando) | **Coste:** Medio ⚠️

```python
pedido = get_db().query(Pedido)
    .filter_by(redisID=redis_id)
    .first()

# Accesos lazy posteriores:
pedido.reparto           # → SELECT repartos WHERE pedido_id = ?
pedido.reparto.repartidor  # → SELECT empleados WHERE EmpleadoID = ?
```

| Operación | Tablas                          | Tipo        |
|-----------|---------------------------------|-------------|
| SELECT    | `pedidos` (filtro `redisID`)    | Explícita   |
| SELECT    | `repartos`                      | Lazy load   |
| SELECT    | `empleados`                     | Lazy load   |

**Problemas:**
- 3 queries en vez de 1 (lazy loading en cadena)
- Sin índice en `pedidos.redisID` — full scan en pedidos
- Se ejecuta cada 5-10 segundos por cada cliente en espera

**Mejora:**
```python
pedido = get_db().query(Pedido)
    .options(
        joinedload(Pedido.reparto).joinedload(Reparto.repartidor)
    )
    .filter_by(redisID=redis_id)
    .first()
```
Y añadir índice: `CREATE INDEX ix_pedidos_redis_id ON pedidos (redisID)`

---

### Q-028 — `POST /api/agregar_pedido` — validación de precios
**Trigger:** Confirmación del pedido online
**Frecuencia:** Media | **Coste:** Medio

Ver Q-004 (`agregar_productos_a_pedido`). La validación de precios es el motivo del N+1 — se carga cada `Producto` para comparar el precio del carrito JS contra la BD. Lógica correcta y necesaria; el problema es la implementación con loop.

---

## 9. Problemas Globales

### 9.1 N+1 confirmados

| ID | Función | Loop sobre | Query dentro del loop | Mejora |
|----|---------|------------|----------------------|--------|
| Q-004 | `agregar_productos_a_pedido()` | Items del carrito | `SELECT productos WHERE ProductoID=?` | `IN` + dict |
| Q-013 | `descontar_stock_picking()` | Items del picking | `SELECT productos WHERE ProductoID=?` | `IN` + bulk update |
| Q-019 | `picking_activo()` | Pickings activos | `SELECT historial_estados WHERE pedido_id=?` | joinedload |
| Q-020 | `rendimiento_empleados()` | Todos los empleados | `SELECT picking_pedido WHERE empleado_id=?` + reparto | JOIN directo |
| Q-025 | `monitoreo_pickers()` | Pickings activos | `SELECT historial_estados WHERE pedido_id=?` | joinedload |

---

### 9.2 Queries sin índice en hot path

| Columna filtrada              | Tabla              | Frecuencia de filtro | Impacto |
|-------------------------------|--------------------|-----------------------|---------|
| `pedidos.ClienteID`           | `pedidos`          | Cada webhook          | Alto    |
| `pedidos.Estado`              | `pedidos`          | Cada webhook + polling| Alto    |
| `pedidos.FechaCreacion`       | `pedidos`          | Dashboard polling     | Alto    |
| `pedidos.redisID`             | `pedidos`          | Cada polling cliente  | Alto    |
| `picking_pedido.estado`       | `picking_pedido`   | Dashboard polling     | Medio   |
| `repartos.estado`             | `repartos`         | Dashboard polling     | Medio   |
| `picking_pedido.empleado_id`  | `picking_pedido`   | Hub empleado          | Medio   |
| `repartos.repartidor_id`      | `repartos`         | Hub empleado          | Medio   |

---

### 9.3 SELECT sin filtro sobre tabla completa

| ID | Función | Query | Problema |
|----|---------|-------|----------|
| Q-011 | `obtener_productos()` | `SELECT * FROM productos` | Carga todos incluso inactivos, sin caché |
| Q-020 | `rendimiento_empleados()` | `SELECT * FROM empleados` | Todos los empleados sin filtro de activos |

---

### 9.4 Columnas de texto largo cargadas innecesariamente

`productos.Ingredientes`, `productos.Descripcion`, `productos.Ubicacion` se cargan en cada `obtener_productos()` aunque el menú del cliente no los usa todos. En tablas con muchas filas esto infla el payload innecesariamente.

---

### 9.5 Queries duplicadas entre `gestor_dashboard.py` y `gestor_metricas.py`

Los contadores de pedidos activos, pickings y repartos se implementan de forma independiente en ambos archivos. Cualquier cambio de lógica (nuevo estado, nueva condición) debe aplicarse en dos sitios.

---

### 9.6 Polling sin caché

Los endpoints consultados por polling (`/dashboard/metricas`, `/empleado/carga-operativa`, `/api/seguimiento/<id>`) ejecutan queries a SQL Server en cada ciclo sin ninguna capa de caché. Redis ya está disponible en el proyecto — usarlo para cachear estos resultados con TTL de 10-30s reduciría la carga en al menos un 90%.

---

### 9.7 Lazy loading como norma implícita

SQLAlchemy usa lazy loading por defecto. En este proyecto las relaciones se acceden frecuentemente después del SELECT inicial (picking.pedido, pedido.reparto, reparto.repartidor, etc.) sin `joinedload` explícito. El resultado es queries adicionales silenciosas e impredecibles que no aparecen en los logs si no se activa el echo de SQLAlchemy.

---

### 9.8 Patrón SELECT-then-UPDATE redundante

Las funciones `guardar_enlace()`, `guardar_forma_pago()`, `guardar_coordenadas()`, `guardar_redis_id()` hacen cada una un SELECT + UPDATE sobre el mismo `PedidoID`. En el flujo de creación de pedido se encadenan 4 veces seguidas sobre el mismo registro. Una sola función de actualización batch reduciría a 1 SELECT + 1 UPDATE.

---

## 10. Índices Recomendados

```sql
-- Hot path: búsqueda por cliente y estado en cada webhook
CREATE INDEX ix_pedidos_cliente_estado
    ON pedidos (ClienteID, Estado);

-- Hot path: seguimiento de pedido por cliente desde ver_comandas.html
CREATE INDEX ix_pedidos_redis_id
    ON pedidos (redisID)
    WHERE redisID IS NOT NULL;

-- Dashboard polling: filtros por fecha y estado
CREATE INDEX ix_pedidos_fecha_creacion
    ON pedidos (FechaCreacion DESC);

CREATE INDEX ix_pedidos_fecha_estado
    ON pedidos (FechaCreacion, Estado);

-- Dashboard polling: colas de picking y reparto
CREATE INDEX ix_picking_pedido_estado
    ON picking_pedido (estado);

CREATE INDEX ix_picking_pedido_empleado
    ON picking_pedido (empleado_id, estado);

CREATE INDEX ix_repartos_estado
    ON repartos (estado);

CREATE INDEX ix_repartos_repartidor
    ON repartos (repartidor_id, estado);

-- Hub empleado: métricas del día
CREATE INDEX ix_picking_pedido_empleado_fecha
    ON picking_pedido (empleado_id, completado_en)
    WHERE estado = 'completado';

CREATE INDEX ix_repartos_repartidor_fecha
    ON repartos (repartidor_id, hora_entrega_real)
    WHERE estado = 'entregado';

-- Historial de estados: búsqueda por pedido (trazabilidad)
CREATE INDEX ix_historial_pedido_id
    ON historial_estados_pedido (pedido_id, cambiado_en DESC);

-- Turnos y fichaje: búsqueda por fecha
CREATE INDEX ix_turnos_empleado_fecha
    ON turnos (empleado_id, fecha);

CREATE INDEX ix_check_ins_empleado_fecha
    ON check_ins (empleado_id, fecha);
```

---

*Generado el 2026-03-23 a partir de `managers/`, `controllers/` y `blueprints/`.*
