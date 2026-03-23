# DB_MAP.md

> Mapa técnico completo de la base de datos de **panchi-bot** — 21 tablas, SQL Server, SQLAlchemy 2.0.

---

## Índice

1. [Visión General](#1-visión-general)
2. [Diagrama de Relaciones](#2-diagrama-de-relaciones)
3. [Tablas — Clientes y Catálogo](#3-tablas--clientes-y-catálogo)
4. [Tablas — Pedidos y Pagos](#4-tablas--pedidos-y-pagos)
5. [Tablas — Empleados y Roles](#5-tablas--empleados-y-roles)
6. [Tablas — Operaciones (Picking y Reparto)](#6-tablas--operaciones-picking-y-reparto)
7. [Tablas — Incidencias y Auditoría](#7-tablas--incidencias-y-auditoría)
8. [Tablas — Turnos y Fichaje](#8-tablas--turnos-y-fichaje)
9. [Estados y Transiciones](#9-estados-y-transiciones)
10. [Flujo de Datos del Negocio](#10-flujo-de-datos-del-negocio)
11. [Campos Críticos](#11-campos-críticos)
12. [Problemas e Inconsistencias](#12-problemas-e-inconsistencias)

---

## 1. Visión General

| Dominio            | Tablas                                                                                   |
|--------------------|------------------------------------------------------------------------------------------|
| Clientes           | `usuarios`                                                                               |
| Catálogo           | `categorias`, `productos`                                                                |
| Pedidos            | `pedidos`, `pedido_detalles`                                                             |
| Pagos y Auditoría  | `pagos`, `audit_log`, `historial_estados_pedido`                                         |
| Empleados          | `empleados`, `roles`, `empleado_capacidades`                                             |
| RRHH               | `turnos`, `check_ins`, `tramos_turno`, `ausencias`, `solicitudes_cambio_turno`           |
| Métricas           | `metricas_diarias_empleado`                                                              |
| Operaciones        | `picking_pedido`, `picking_items`, `repartos`                                            |
| Incidencias        | `incidencias`                                                                            |

---

## 2. Diagrama de Relaciones

```
usuarios ──────────────────────────────────────────────────┐
   │ 1:N                                                   │ 1:N
pedidos ──────── pedido_detalles ──── productos            incidencias
   │                   │                  │
   │ 1:N          1:1 picking_item    categorias
   │
   ├── pagos (1:N)
   ├── historial_estados_pedido (1:N)
   ├── audit_log (1:N)
   ├── incidencias (1:N)
   │
   ├── picking_pedido (1:1) ──── picking_items (1:N)
   │
   └── repartos (1:1)
            │
         empleados ──── roles (N:1)
            │      ──── empleado_capacidades (1:N)
            │      ──── turnos (1:N)
            │      ──── check_ins (1:N) ──── tramos_turno (1:N)
            │      ──── ausencias (1:N)
            │      ──── solicitudes_cambio_turno (1:N)
            └──────────  metricas_diarias_empleado (1:N)
```

---

## 3. Tablas — Clientes y Catálogo

### `usuarios`

Clientes registrados vía WhatsApp.

| Columna          | Tipo         | Restricciones         | Descripción                                    |
|------------------|--------------|-----------------------|------------------------------------------------|
| `id`             | Integer      | PK, autoincrement     |                                                |
| `nombre`         | String(255)  | NOT NULL              | Nombre validado con spaCy en el registro       |
| `numero_cliente` | String(50)   | NOT NULL, UNIQUE      | Número de teléfono WhatsApp (identificador real) |
| `direccion`      | String(255)  | nullable              | Dirección por defecto validada con Google Maps |

**Relaciones:**
- `pedidos` → `pedidos.ClienteID` (1:N, cascade delete)
- `incidencias` → `incidencias.cliente_id` (1:N)

---

### `categorias`

Categorías del menú.

| Columna         | Tipo         | Restricciones     | Descripción                          |
|-----------------|--------------|-------------------|--------------------------------------|
| `id`            | Integer      | PK                |                                      |
| `nombre`        | String(100)  | NOT NULL, UNIQUE  |                                      |
| `orden_display` | Integer      | NOT NULL, default 0 | Orden de aparición en el menú      |
| `activa`        | Boolean      | NOT NULL, default True | Ocultar categorías sin borrarlas |

---

### `productos`

Catálogo de productos del restaurante.

| Columna        | Tipo           | Restricciones          | Descripción                                          |
|----------------|----------------|------------------------|------------------------------------------------------|
| `ProductoID`   | Integer        | PK                     |                                                      |
| `categoria_id` | Integer        | FK → `categorias.id`, nullable | Referencia normalizada (usar en código nuevo)  |
| `Nombre`       | String(255)    | NOT NULL, UNIQUE       |                                                      |
| `Precio`       | DECIMAL(10,2)  | NOT NULL               | **Precio autoritativo** — validado en `/api/agregar_pedido` |
| `Categoria`    | String(50)     | NOT NULL               | **Legacy** — columna de texto, usar `categoria_id`  |
| `Ingredientes` | String(255)    | nullable               |                                                      |
| `Ubicacion`    | String(255)    | nullable               | Ubicación física en almacén para el picker           |
| `Stock`        | Integer        | NOT NULL, default 0    |                                                      |
| `ImagenURL`    | String(255)    | nullable               |                                                      |
| `Descripcion`  | String(500)    | nullable               |                                                      |
| `Descuento`    | DECIMAL(10,2)  | nullable, default 0.00 |                                                      |
| `Disponible`   | Boolean        | default True           | Control de visibilidad en el menú                    |
| `created_at`   | DateTime       | default utcnow         |                                                      |
| `updated_at`   | DateTime       | nullable, onupdate     |                                                      |

**Relaciones:**
- `categoria_rel` → `categorias` (N:1)
- `detalles` → `pedido_detalles.ProductoID` (1:N, cascade delete)

---

## 4. Tablas — Pedidos y Pagos

### `pedidos`

Tabla central del negocio. Cada pedido de un cliente.

| Columna             | Tipo           | Restricciones                      | Descripción                                              |
|---------------------|----------------|------------------------------------|----------------------------------------------------------|
| `PedidoID`          | Integer        | PK, autoincrement desde 2000       | IDs comienzan en 2000 (server_default IDENTITY)          |
| `ClienteID`         | Integer        | FK → `usuarios.id`, NOT NULL       |                                                          |
| `FechaCreacion`     | DateTime       | default utcnow                     |                                                          |
| `FechaActualizacion`| DateTime       | nullable, onupdate                 |                                                          |
| `Estado`            | String(20)     | default 'Pendiente'                | **Campo crítico** — ver estados en Sección 9             |
| `Total`             | DECIMAL(18,2)  | default 0.0                        | Suma de subtotales de `pedido_detalles`                  |
| `DireccionEntrega`  | String(255)    | NOT NULL                           | Dirección de entrega específica del pedido               |
| `TelefonoEntrega`   | String(50)     | NOT NULL                           | Teléfono del cliente en el momento del pedido            |
| `enlace`            | String(255)    | nullable                           | URL del menú generada (token incluido)                   |
| `redisID`           | String(255)    | nullable                           | UUID del carrito en Redis (TTL)                          |
| `estadopago`        | String(255)    | nullable                           | Estado devuelto por Monei en el webhook                  |
| `estadoauxiliar`    | String(255)    | nullable                           | Estado auxiliar para flujo interno                       |
| `forma_pago`        | String(20)     | nullable, default 'online'         | `online` \| `efectivo` \| `tarjeta`                      |
| `lat_entrega`       | Float          | nullable                           | Latitud de entrega (Google Maps geocoding)               |
| `lng_entrega`       | Float          | nullable                           | Longitud de entrega (Google Maps geocoding)              |
| `cancel_reason`     | String(50)     | nullable                           | Motivo de cancelación                                    |
| `cancelled_by`      | Integer        | FK → `empleados.EmpleadoID`, nullable | Empleado que canceló                                  |
| `cancelled_at`      | DateTime       | nullable                           |                                                          |
| `Notas`             | String(300)    | nullable                           | Notas libres del cliente o empleado                      |

**Relaciones:**
- `cliente` → `usuarios` (N:1)
- `detalles` → `pedido_detalles` (1:N, cascade delete)
- `pagos` → `pagos` (1:N)
- `historial_estados` → `historial_estados_pedido` (1:N)
- `picking` → `picking_pedido` (1:1)
- `reparto` → `repartos` (1:1)
- `incidencias` → `incidencias` (1:N)
- `audit_logs` → `audit_log` (1:N, backref)

---

### `pedido_detalles`

Líneas de un pedido (un registro por producto).

| Columna          | Tipo           | Restricciones                         | Descripción                                              |
|------------------|----------------|---------------------------------------|----------------------------------------------------------|
| `DetalleID`      | Integer        | PK                                    |                                                          |
| `PedidoID`       | Integer        | FK → `pedidos.PedidoID`, NOT NULL     |                                                          |
| `ProductoID`     | Integer        | FK → `productos.ProductoID`, NOT NULL |                                                          |
| `Cantidad`       | Integer        | NOT NULL                              |                                                          |
| `PrecioUnitario` | DECIMAL(10,2)  | nullable                              | Precio en el momento del pedido (snapshot)               |
| `NombreProducto` | String(255)    | nullable                              | Nombre en el momento del pedido (snapshot)               |
| `Subtotal`       | DECIMAL(18,2)  | NOT NULL                              | `Cantidad × PrecioUnitario`                              |

**Relaciones:**
- `pedido` → `pedidos` (N:1)
- `producto` → `productos` (N:1)
- `picking_item` → `picking_items` (1:1)

---

### `pagos`

Registro de cada intento de pago. Un pedido puede tener múltiples registros (reintentos).

| Columna               | Tipo           | Restricciones             | Descripción                                      |
|-----------------------|----------------|---------------------------|--------------------------------------------------|
| `id`                  | Integer        | PK                        |                                                  |
| `pedido_id`           | Integer        | FK → `pedidos.PedidoID`   |                                                  |
| `proveedor`           | String(50)     | NOT NULL, default 'monei' |                                                  |
| `referencia_externa`  | String(255)    | nullable, UNIQUE          | ID de pago en Monei                              |
| `estado`              | String(30)     | NOT NULL                  | Estado devuelto por Monei (SUCCEEDED, FAILED...) |
| `importe`             | DECIMAL(18,2)  | NOT NULL                  |                                                  |
| `importe_reembolsado` | DECIMAL(18,2)  | NOT NULL, default 0.00    |                                                  |
| `moneda`              | String(3)      | NOT NULL, default 'EUR'   |                                                  |
| `datos_raw`           | Text           | nullable                  | JSON completo del webhook de Monei               |
| `created_at`          | DateTime       | default utcnow             |                                                  |
| `updated_at`          | DateTime       | nullable, onupdate        |                                                  |

---

### `historial_estados_pedido`

Trazabilidad de cada cambio de estado de un pedido. Nunca se elimina.

| Columna          | Tipo        | Restricciones                          | Descripción                     |
|------------------|-------------|----------------------------------------|---------------------------------|
| `id`             | Integer     | PK                                     |                                 |
| `pedido_id`      | Integer     | FK → `pedidos.PedidoID`, NOT NULL      |                                 |
| `estado_anterior`| String(30)  | NOT NULL                               |                                 |
| `estado_nuevo`   | String(30)  | NOT NULL                               |                                 |
| `cambiado_en`    | DateTime    | NOT NULL, default utcnow               |                                 |
| `notas`          | String(500) | nullable                               |                                 |
| `empleado_id`    | Integer     | FK → `empleados.EmpleadoID`, nullable  | Quién hizo el cambio (si aplica)|

---

### `audit_log`

Log de acciones operativas sobre pedidos realizadas por empleados.

| Columna      | Tipo        | Restricciones                          | Descripción                                              |
|--------------|-------------|----------------------------------------|----------------------------------------------------------|
| `id`         | Integer     | PK                                     |                                                          |
| `pedido_id`  | Integer     | FK → `pedidos.PedidoID`, nullable      |                                                          |
| `empleado_id`| Integer     | FK → `empleados.EmpleadoID`, nullable  |                                                          |
| `accion`     | String(50)  | NOT NULL                               | `cancelar_pedido` \| `eliminar_item` \| `sustituir_item` |
| `detalles`   | Text        | nullable                               | JSON con valores anteriores/nuevos                       |
| `created_at` | DateTime    | NOT NULL, default utcnow               |                                                          |

---

## 5. Tablas — Empleados y Roles

### `roles`

Roles del sistema: `admin`, `picker`, `repartidor`, `supervisor`.

| Columna       | Tipo         | Restricciones    | Descripción |
|---------------|--------------|------------------|-------------|
| `id`          | Integer      | PK               |             |
| `nombre`      | String(100)  | NOT NULL, UNIQUE |             |
| `descripcion` | String(500)  | nullable         |             |

---

### `empleados`

Personal del restaurante. Se usan para login en el dashboard y para asignar pedidos.

| Columna            | Tipo           | Restricciones                         | Descripción                                          |
|--------------------|----------------|---------------------------------------|------------------------------------------------------|
| `EmpleadoID`       | Integer        | PK                                    |                                                      |
| `rol_id`           | Integer        | FK → `roles.id`, nullable             | Rol normalizado (usar en código nuevo)               |
| `Nombre`           | String(255)    | NOT NULL                              |                                                      |
| `Apellido`         | String(255)    | NOT NULL                              |                                                      |
| `Email`            | String(255)    | NOT NULL, UNIQUE                      | Credencial de login                                  |
| `Telefono`         | String(50)     | nullable                              |                                                      |
| `Direccion`        | String(255)    | nullable                              |                                                      |
| `Puesto`           | String(100)    | NOT NULL                              | **Legacy** — usar `rol_id` en código nuevo           |
| `Salario`          | DECIMAL(10,2)  | NOT NULL, default 0.00                |                                                      |
| `activo`           | Boolean        | NOT NULL, default True                | Desactivar sin borrar                                |
| `estado_operativo` | String(20)     | NOT NULL, default 'desconectado'      | `desconectado` \| `conectado` \| `ocupado`           |
| `password_hash`    | String(255)    | nullable                              | Hash de contraseña para el dashboard                 |
| `rol_activo`       | String(20)     | nullable                              | `picker` \| `repartidor` \| NULL (turno actual)      |
| `created_at`       | DateTime       | default utcnow                        |                                                      |
| `updated_at`       | DateTime       | nullable, onupdate                    |                                                      |

**Relaciones:**
- `rol` → `roles` (N:1)
- `capacidades` → `empleado_capacidades` (1:N, cascade delete)
- `pickings` → `picking_pedido` (1:N)
- `repartos` → `repartos` (1:N)
- `turnos` → `turnos` (1:N)
- `check_ins` → `check_ins` (1:N)
- `ausencias` → `ausencias` (1:N, backref)
- `metricas_diarias` → `metricas_diarias_empleado` (1:N, backref)

---

### `empleado_capacidades`

Roles operativos que puede desempeñar un empleado (picker, repartidor). Un empleado puede tener ambos.

| Columna       | Tipo        | Restricciones                          | Descripción                        |
|---------------|-------------|----------------------------------------|------------------------------------|
| `id`          | Integer     | PK                                     |                                    |
| `empleado_id` | Integer     | FK → `empleados.EmpleadoID`, NOT NULL  |                                    |
| `rol`         | String(20)  | NOT NULL                               | `picker` \| `repartidor`           |

**Constraint único:** `(empleado_id, rol)` — `uq_empleado_rol`

---

### `ausencias`

Registro de ausencias con flujo de aprobación.

| Columna       | Tipo        | Restricciones                               | Descripción                                          |
|---------------|-------------|---------------------------------------------|------------------------------------------------------|
| `id`          | Integer     | PK                                          |                                                      |
| `empleado_id` | Integer     | FK → `empleados.EmpleadoID`, NOT NULL       |                                                      |
| `fecha`       | Date        | NOT NULL                                    |                                                      |
| `tipo`        | String(30)  | NOT NULL                                    | `vacaciones` \| `baja_medica` \| `personal` \| `injustificada` |
| `estado`      | String(20)  | NOT NULL, default 'pendiente'               | `pendiente` \| `aprobada` \| `rechazada`             |
| `aprobado_por`| Integer     | FK → `empleados.EmpleadoID`, nullable       | Empleado supervisor que aprueba                      |
| `aprobado_en` | DateTime    | nullable                                    |                                                      |
| `notas`       | String(500) | nullable                                    |                                                      |
| `created_at`  | DateTime    | default utcnow                              |                                                      |

**Constraint único:** `(empleado_id, fecha)` — `uq_ausencia_empleado_fecha`

---

### `solicitudes_cambio_turno`

Solicitud de cesión o intercambio de turno entre empleados.

| Columna          | Tipo        | Restricciones                          | Descripción                  |
|------------------|-------------|----------------------------------------|------------------------------|
| `id`             | Integer     | PK                                     |                              |
| `turno_cedido_id`| Integer     | FK → `turnos.id`, NOT NULL             | Turno que se quiere ceder    |
| `solicitante_id` | Integer     | FK → `empleados.EmpleadoID`, NOT NULL  | Quien solicita el cambio     |
| `sustituto_id`   | Integer     | FK → `empleados.EmpleadoID`, nullable  | Quien cubre el turno         |
| `estado`         | String(20)  | NOT NULL, default 'pendiente'          | `pendiente` \| `aprobada` \| `rechazada` |
| `aprobado_por`   | Integer     | FK → `empleados.EmpleadoID`, nullable  |                              |
| `aprobado_en`    | DateTime    | nullable                               |                              |
| `motivo`         | String(500) | nullable                               |                              |
| `created_at`     | DateTime    | default utcnow                         |                              |

---

### `metricas_diarias_empleado`

Caché de métricas diarias por empleado y rol. Se recalcula periódicamente.

| Columna                      | Tipo        | Restricciones                         | Descripción                          |
|------------------------------|-------------|---------------------------------------|--------------------------------------|
| `id`                         | Integer     | PK                                    |                                      |
| `empleado_id`                | Integer     | FK → `empleados.EmpleadoID`, NOT NULL |                                      |
| `fecha`                      | Date        | NOT NULL                              |                                      |
| `rol`                        | String(20)  | NOT NULL                              | `picker` \| `repartidor`             |
| `horas_trabajadas_min`       | Integer     | nullable                              | Minutos trabajados                   |
| `pedidos_completados`        | Integer     | NOT NULL, default 0                   |                                      |
| `tiempo_medio_operacion_min` | Integer     | nullable                              | Minutos medios por pedido            |
| `incidencias`                | Integer     | NOT NULL, default 0                   |                                      |
| `minutos_tarde`              | Integer     | nullable                              |                                      |
| `calculado_en`               | DateTime    | default utcnow                        |                                      |

**Constraint único:** `(empleado_id, fecha, rol)` — `uq_metrica_empleado_fecha_rol`

---

## 6. Tablas — Operaciones (Picking y Reparto)

### `picking_pedido`

Estado de preparación de un pedido en almacén. **Uno por pedido** (unique en `pedido_id`).

| Columna        | Tipo        | Restricciones                          | Descripción                                      |
|----------------|-------------|----------------------------------------|--------------------------------------------------|
| `id`           | Integer     | PK                                     |                                                  |
| `pedido_id`    | Integer     | FK → `pedidos.PedidoID`, NOT NULL, UNIQUE |                                               |
| `empleado_id`  | Integer     | FK → `empleados.EmpleadoID`, nullable  | Picker asignado                                  |
| `estado`       | String(30)  | NOT NULL, default 'pendiente'          | Ver `EstadoPicking` en states.py                 |
| `iniciado_en`  | DateTime    | nullable                               |                                                  |
| `completado_en`| DateTime    | nullable                               |                                                  |
| `notas`        | String(500) | nullable                               |                                                  |
| `created_at`   | DateTime    | default utcnow                         |                                                  |

**Estados válidos (`EstadoPicking`):** `pendiente` → `en_proceso` → `completado` | `con_incidencias` | `cancelado`

---

### `picking_items`

Estado de cada línea de producto durante la preparación.

| Columna                | Tipo        | Restricciones                              | Descripción                              |
|------------------------|-------------|--------------------------------------------|------------------------------------------|
| `id`                   | Integer     | PK                                         |                                          |
| `picking_id`           | Integer     | FK → `picking_pedido.id`, NOT NULL         |                                          |
| `pedido_detalle_id`    | Integer     | FK → `pedido_detalles.DetalleID`, NOT NULL |                                          |
| `estado`               | String(30)  | NOT NULL, default 'pendiente'              | `pendiente` \| `encontrado` \| `sin_stock` \| `sustituido` |
| `cantidad_encontrada`  | Integer     | nullable                                   | Puede diferir de la cantidad pedida      |
| `producto_sustituto_id`| Integer     | FK → `productos.ProductoID`, nullable      | Producto sustituto si hay sin_stock      |
| `notas`                | String(500) | nullable                                   |                                          |

---

### `repartos`

Seguimiento de la entrega. **Uno por pedido** (unique en `pedido_id`).

| Columna                  | Tipo           | Restricciones                          | Descripción                                         |
|--------------------------|----------------|----------------------------------------|-----------------------------------------------------|
| `id`                     | Integer        | PK                                     |                                                     |
| `pedido_id`              | Integer        | FK → `pedidos.PedidoID`, UNIQUE        |                                                     |
| `repartidor_id`          | Integer        | FK → `empleados.EmpleadoID`, nullable  | Repartidor asignado                                 |
| `estado`                 | String(30)     | NOT NULL, default 'pendiente'          | Ver `EstadoReparto` en states.py                    |
| `hora_salida`            | DateTime       | nullable                               |                                                     |
| `hora_estimada_entrega`  | DateTime       | nullable                               |                                                     |
| `hora_entrega_real`      | DateTime       | nullable                               |                                                     |
| `motivo_no_entrega`      | String(500)    | nullable                               |                                                     |
| `prueba_entrega_url`     | String(500)    | nullable                               | URL de foto/evidencia de entrega                    |
| `notas`                  | String(500)    | nullable                               |                                                     |
| `metodo_cobro`           | String(20)     | nullable                               | `efectivo` \| `tarjeta` \| `mixto`                  |
| `importe_cobrado`        | DECIMAL(10,2)  | nullable                               | Total que cobró el repartidor en mano               |
| `cambio_devuelto`        | DECIMAL(10,2)  | nullable                               | Cambio devuelto (solo efectivo)                     |
| `importe_efectivo`       | DECIMAL(10,2)  | nullable                               | Parte en efectivo (solo mixto)                      |
| `importe_tarjeta`        | DECIMAL(10,2)  | nullable                               | Parte en tarjeta (solo mixto)                       |
| `created_at`             | DateTime       | default utcnow                         |                                                     |
| `updated_at`             | DateTime       | nullable, onupdate                     |                                                     |

**Estados válidos (`EstadoReparto`):** `pendiente` → `asignado` → `en_camino` → `entregado` | `no_entregado` | `cancelado`

---

## 7. Tablas — Incidencias y Auditoría

### `incidencias`

Incidencias operativas ligadas a un pedido y/o cliente.

| Columna       | Tipo        | Restricciones                          | Descripción                                                       |
|---------------|-------------|----------------------------------------|-------------------------------------------------------------------|
| `id`          | Integer     | PK                                     |                                                                   |
| `pedido_id`   | Integer     | FK → `pedidos.PedidoID`, nullable      | Puede no estar ligada a un pedido concreto                        |
| `cliente_id`  | Integer     | FK → `usuarios.id`, nullable           |                                                                   |
| `asignado_a`  | Integer     | FK → `empleados.EmpleadoID`, nullable  | Empleado responsable de resolverla                                |
| `tipo`        | String(50)  | NOT NULL                               | `entrega_fallida` \| `producto_faltante` \| `queja_cliente` \| … |
| `descripcion` | Text        | NOT NULL                               |                                                                   |
| `estado`      | String(30)  | NOT NULL, default 'abierta'            | `abierta` \| `en_proceso` \| `resuelta` \| `cerrada`             |
| `resolucion`  | Text        | nullable                               |                                                                   |
| `created_at`  | DateTime    | default utcnow                         |                                                                   |
| `resuelta_en` | DateTime    | nullable                               |                                                                   |

---

## 8. Tablas — Turnos y Fichaje

### `turnos`

Turno planificado de un empleado.

| Columna          | Tipo        | Restricciones                          | Descripción                                         |
|------------------|-------------|----------------------------------------|-----------------------------------------------------|
| `id`             | Integer     | PK                                     |                                                     |
| `empleado_id`    | Integer     | FK → `empleados.EmpleadoID`, NOT NULL  |                                                     |
| `fecha`          | Date        | NOT NULL                               |                                                     |
| `hora_inicio`    | Time        | NOT NULL                               |                                                     |
| `hora_fin`       | Time        | NOT NULL                               |                                                     |
| `notas`          | String(255) | nullable                               |                                                     |
| `estado`         | String(20)  | NOT NULL, default 'planificado'        | `planificado` \| `realizado` \| `ausente`           |
| `tipo`           | String(20)  | nullable                               | `mañana` \| `tarde` \| `noche` \| `partido`         |
| `creado_por`     | Integer     | FK → `empleados.EmpleadoID`, nullable  | Admin que creó el turno                             |
| `turno_origen_id`| Integer     | FK → `turnos.id`, nullable             | Auto-referencia: turno original si es una cesión    |
| `created_at`     | DateTime    | default utcnow                         |                                                     |

---

### `check_ins`

Fichaje real del empleado. Puede haber varios por día (entrada/salida/re-entrada).

| Columna              | Tipo        | Restricciones                         | Descripción                               |
|----------------------|-------------|---------------------------------------|-------------------------------------------|
| `id`                 | Integer     | PK                                    |                                           |
| `empleado_id`        | Integer     | FK → `empleados.EmpleadoID`, NOT NULL |                                           |
| `fecha`              | Date        | NOT NULL                              |                                           |
| `inicio`             | DateTime    | NOT NULL                              |                                           |
| `fin`                | DateTime    | nullable                              | NULL = turno en curso                     |
| `turno_id`           | Integer     | FK → `turnos.id`, nullable            | Turno planificado al que corresponde      |
| `estado_validacion`  | String(20)  | NOT NULL, default 'pendiente'         | `pendiente` \| `validado` \| `anomalia`   |
| `minutos_tarde`      | Integer     | nullable                              | Calculado al fichar entrada               |
| `created_at`         | DateTime    | default utcnow                        |                                           |

**Relaciones:**
- `tramos` → `tramos_turno` (1:N, cascade delete)

---

### `tramos_turno`

Segmento de tiempo trabajado en un rol concreto dentro de un check-in. Permite que un empleado sea picker en la mañana y repartidor por la tarde dentro del mismo fichaje.

| Columna      | Tipo        | Restricciones                      | Descripción              |
|--------------|-------------|------------------------------------|--------------------------|
| `id`         | Integer     | PK                                 |                          |
| `check_in_id`| Integer     | FK → `check_ins.id`, NOT NULL      |                          |
| `rol`        | String(20)  | NOT NULL                           | `picker` \| `repartidor` |
| `inicio`     | DateTime    | NOT NULL                           |                          |
| `fin`        | DateTime    | nullable                           | NULL = tramo en curso    |

---

## 9. Estados y Transiciones

### Pedido (`pedidos.Estado`)

```
PENDIENTE ──► ENLACE ──► ENLACE2 ──► CONFIRMANDO_PAGO ──► PAGADO ──► EN_PREPARACION ──► PREPARADO ──► EN_REPARTO ──► ENTREGADO ✓
                                  └──► CONTRA_REEMBOLSO ──────────────────────────────►
PENDIENTE, ENLACE, ENLACE2, CONFIRMANDO_PAGO, CONTRA_REEMBOLSO, EN_PREPARACION ──► CANCELADO ──► REEMBOLSADO ✓
PAGADO ──► REEMBOLSADO ✓
```

Estados terminales: `ENTREGADO`, `CANCELADO`, `REEMBOLSADO`

**Nota importante:** Los valores en DB tienen capitalización inconsistente:
- `"Pendiente"` (capital P)
- `"enlace"`, `"enlace2"`, `"confirmando-pago"`, `"pagado"`, etc. (minúsculas)

### Picking (`picking_pedido.estado`)

`pendiente` → `en_proceso` → `completado` | `con_incidencias` | `cancelado`

### Reparto (`repartos.estado`)

`pendiente` → `asignado` → `en_camino` → `entregado` | `no_entregado` | `cancelado`

### Registro de usuario (Redis — no en DB)

`saludo_inicial` → `esperando_confirmacion` → `esperando_nombre` → `esperando_direccion` → `confirmando_direccion` → **[guardar en DB]**

---

## 10. Flujo de Datos del Negocio

### 10.1 Registro de cliente (Redis → DB)

```
WhatsApp mensaje entrante
        │
        ▼
Redis: estado registration (clave = número de teléfono)
        │
        ▼ (tras confirmar dirección)
INSERT usuarios (nombre, numero_cliente, direccion)
DELETE clave Redis
```

**Datos que persisten:** nombre, teléfono (→ `numero_cliente`), dirección validada.

---

### 10.2 Creación de pedido

```
WhatsApp → POST /webhook
        │
        ▼
pedidos INSERT (Estado='Pendiente', ClienteID, DireccionEntrega, TelefonoEntrega)
Redis: token de menú (TTL ~10 min)
        │
        ▼ (cliente navega menú)
POST /api/confirmacion
Redis: carrito (clave = redisID)
pedidos UPDATE Estado='enlace2'
        │
        ▼
POST /api/agregar_pedido
pedido_detalles INSERT (×N productos)
pagos INSERT (estado='pendiente', referencia_externa=null)
pedidos UPDATE Total, Estado='confirmando-pago'
historial_estados_pedido INSERT
```

---

### 10.3 Confirmación de pago (Monei webhook)

```
POST /webhook/monei (HMAC verificado)
        │
        ▼
pagos UPDATE (estado='SUCCEEDED', referencia_externa, datos_raw)
pedidos UPDATE Estado='pagado', estadopago='SUCCEEDED'
historial_estados_pedido INSERT
picking_pedido INSERT (estado='pendiente')   ← se crea aquí
WhatsApp notificación al cliente
```

---

### 10.4 Pago en efectivo

```
POST /api/agregar_pedido_efectivo
pedido_detalles INSERT
pedidos UPDATE Estado='contra_reembolso', forma_pago='efectivo'
historial_estados_pedido INSERT
picking_pedido INSERT (estado='pendiente')
```

---

### 10.5 Picking (almacén)

```
Dashboard: asignar picker
picking_pedido UPDATE empleado_id, Estado='en_proceso', iniciado_en
        │
        ▼ (picker procesa cada item)
picking_items UPDATE estado (encontrado | sin_stock | sustituido)
        │
        ▼
picking_pedido UPDATE Estado='completado', completado_en
pedidos UPDATE Estado='preparado'
historial_estados_pedido INSERT
```

---

### 10.6 Reparto (entrega)

```
Dashboard: asignar repartidor
repartos INSERT (repartidor_id, estado='asignado')
pedidos UPDATE Estado='en_reparto'
historial_estados_pedido INSERT
        │
        ▼ (repartidor sale)
repartos UPDATE estado='en_camino', hora_salida
        │
        ▼ (repartidor entrega)
repartos UPDATE estado='entregado', hora_entrega_real, metodo_cobro, importe_cobrado...
pedidos UPDATE Estado='entregado'
historial_estados_pedido INSERT
```

---

### 10.7 Cancelación y reembolso

```
audit_log INSERT (accion='cancelar_pedido', detalles={JSON})
pedidos UPDATE Estado='cancelado', cancel_reason, cancelled_by, cancelled_at
historial_estados_pedido INSERT
        │
        ▼ (si pago online confirmado)
pagos UPDATE importe_reembolsado
pedidos UPDATE Estado='reembolsado'
historial_estados_pedido INSERT
```

---

## 11. Campos Críticos

### Control de estado del pedido

| Campo                    | Tabla     | Riesgo si se modifica directamente                      |
|--------------------------|-----------|---------------------------------------------------------|
| `pedidos.Estado`         | `pedidos` | Rompe el flujo si no pasa por `gestor_pedidos.py`       |
| `pedidos.estadopago`     | `pedidos` | Refleja el estado de Monei — no confundir con `Estado`  |
| `pedidos.forma_pago`     | `pedidos` | Determina si hay flujo Monei o flujo efectivo           |

### Validación de precios (anti-fraude)

| Campo                         | Tabla             | Propósito                                           |
|-------------------------------|-------------------|-----------------------------------------------------|
| `productos.Precio`            | `productos`       | Precio autoritativo validado en `/api/agregar_pedido` |
| `pedido_detalles.PrecioUnitario` | `pedido_detalles` | Snapshot del precio en el momento del pedido       |
| `pedido_detalles.Subtotal`    | `pedido_detalles` | `Cantidad × PrecioUnitario` (calculado al crear)   |
| `pedidos.Total`               | `pedidos`         | Suma de subtotales (no recalcular del carrito JS)  |

### Coordenadas de entrega

| Campo                | Tabla     | Uso                                              |
|----------------------|-----------|--------------------------------------------------|
| `pedidos.lat_entrega`| `pedidos` | Geocodificado por Google Maps al confirmar pedido|
| `pedidos.lng_entrega`| `pedidos` | Validado contra zona de reparto con Shapely       |

### Pagos presenciales (repartidor)

| Campo                     | Tabla      | Solo se rellena cuando…                         |
|---------------------------|------------|-------------------------------------------------|
| `repartos.metodo_cobro`   | `repartos` | El repartidor confirma la entrega con cobro     |
| `repartos.importe_cobrado`| `repartos` | Ídem                                            |
| `repartos.cambio_devuelto`| `repartos` | Solo si `metodo_cobro = 'efectivo'`             |
| `repartos.importe_efectivo`| `repartos`| Solo si `metodo_cobro = 'mixto'`               |
| `repartos.importe_tarjeta` | `repartos`| Solo si `metodo_cobro = 'mixto'`               |

---

## 12. Problemas e Inconsistencias

### 12.1 Columnas legacy con duplicado normalizado

Hay dos pares de columnas que coexisten: una legacy (texto plano) y una normalizada (FK). El código nuevo debe usar la FK.

| Columna legacy              | Tabla       | Columna normalizada     | Estado              |
|-----------------------------|-------------|-------------------------|---------------------|
| `productos.Categoria`       | `productos` | `productos.categoria_id`| FK nullable, coexisten |
| `empleados.Puesto`          | `empleados` | `empleados.rol_id`      | FK nullable, coexisten |

**Riesgo:** Si `categoria_id` y `Categoria` divergen, el menú puede mostrar categorías incorrectas. No hay constraint que los mantenga sincronizados.

---

### 12.2 `pedidos.Estado` tiene capitalización inconsistente

El valor `"Pendiente"` lleva capital P, mientras que el resto (`"enlace"`, `"pagado"`, `"en_preparacion"`, etc.) son minúsculas. Esto obliga a comparaciones case-sensitive en el código y es fuente de bugs silenciosos.

```python
# En states.py:
PENDIENTE = "Pendiente"   # ← capital P
ENLACE    = "enlace"      # ← minúsculas
```

---

### 12.3 `pedidos.redisID` puede quedar huérfano

`redisID` almacena el UUID del carrito en Redis. Si el proceso muere después de guardar en DB pero antes de limpiar Redis, la clave Redis queda viva hasta TTL. No hay limpieza activa de `redisID` obsoletos en DB.

---

### 12.4 `pagos` permite múltiples registros por pedido sin control de duplicados

Un pedido puede tener N filas en `pagos`. El único control de unicidad es `referencia_externa` (UNIQUE), que es `nullable`. Si hay un reintento donde `referencia_externa` es NULL en ambos, no hay nada que impida dos filas idénticas.

---

### 12.5 `pedidos.enlace` guarda la URL completa, no solo el token

`enlace` almacena la URL completa del menú (incluyendo el token). Si `PUBLIC_URL` cambia (por ejemplo en un cambio de dominio), los enlaces guardados en DB quedan obsoletos. Sería más robusto guardar solo el token y reconstruir la URL en runtime.

---

### 12.6 `check_ins.fin = NULL` indica turno en curso

No hay un mecanismo de cierre automático. Si el servidor cae mientras un empleado tiene un fichaje abierto (`fin = NULL`), el fichaje queda abierto indefinidamente. Tampoco hay un constraint que evite dos fichajes abiertos simultáneos para el mismo empleado.

---

### 12.7 `repartos` — campos de cobro presencial añadidos por ALTER TABLE

El comentario en el modelo indica que `metodo_cobro`, `importe_cobrado`, `cambio_devuelto`, `importe_efectivo` e `importe_tarjeta` fueron añadidos mediante `ALTER TABLE` manual, no a través de una migración rastreable. Esto significa que el archivo de migración correspondiente puede no existir y los entornos de desarrollo antiguos pueden carecer de estas columnas.

---

### 12.8 Sin índices explícitos en columnas de búsqueda frecuente

El ORM no define índices en:
- `pedidos.Estado` — consultado en cada carga del dashboard
- `pedidos.ClienteID` — JOIN frecuente
- `picking_pedido.estado` — cola del picker
- `repartos.estado` — cola del repartidor

SQL Server creará el PK como clustered index, pero las queries de filtro por estado no tienen índice y harán full scan en tablas grandes.

---

*Generado el 2026-03-23 a partir de `models.py` y `states.py`.*
