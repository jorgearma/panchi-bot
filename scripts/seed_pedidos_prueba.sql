-- ============================================================
-- DATOS DE PRUEBA: 3 clientes + 3 pedidos operativos
-- SQL Server
--
-- Estados creados:
--   Pedido A → pagado          (listo para asignar picker)
--   Pedido B → en_preparacion  (picker trabajando)
--   Pedido C → preparado       (listo para repartir)
--
-- Ejecutar en SSMS o sqlcmd contra la BD de panchi-bot
-- ============================================================

BEGIN TRANSACTION;

-- ============================================================
-- 1. CLIENTES
-- ============================================================

INSERT INTO usuarios (nombre, numero_cliente, direccion) VALUES
    (N'Ana García López',     N'whatsapp:+34611222333', N'Avenida Miguel de Cervantes 79 1B'),
    (N'Carlos Martínez Ruiz', N'whatsapp:+34622333444', N'Paseo de la Estación 5'),
    (N'Laura Sánchez Mora',   N'whatsapp:+34633444555', N'Calle Los Labradores 5');

-- Capturar IDs de clientes recién creados
DECLARE @c1 INT = (SELECT id FROM usuarios WHERE numero_cliente = N'whatsapp:+34611222333');
DECLARE @c2 INT = (SELECT id FROM usuarios WHERE numero_cliente = N'whatsapp:+34622333444');
DECLARE @c3 INT = (SELECT id FROM usuarios WHERE numero_cliente = N'whatsapp:+34633444555');

-- ============================================================
-- 2. PRODUCTOS: coger los 4 primeros disponibles del catálogo
-- ============================================================

DECLARE @p1id   INT,           @p1nom NVARCHAR(255), @p1pre DECIMAL(10,2);
DECLARE @p2id   INT,           @p2nom NVARCHAR(255), @p2pre DECIMAL(10,2);
DECLARE @p3id   INT,           @p3nom NVARCHAR(255), @p3pre DECIMAL(10,2);
DECLARE @p4id   INT,           @p4nom NVARCHAR(255), @p4pre DECIMAL(10,2);

SELECT @p1id = ProductoID, @p1nom = Nombre, @p1pre = Precio
FROM   productos WHERE Disponible = 1
ORDER BY ProductoID ASC OFFSET 0 ROWS FETCH NEXT 1 ROWS ONLY;

SELECT @p2id = ProductoID, @p2nom = Nombre, @p2pre = Precio
FROM   productos WHERE Disponible = 1
ORDER BY ProductoID ASC OFFSET 1 ROWS FETCH NEXT 1 ROWS ONLY;

SELECT @p3id = ProductoID, @p3nom = Nombre, @p3pre = Precio
FROM   productos WHERE Disponible = 1
ORDER BY ProductoID ASC OFFSET 2 ROWS FETCH NEXT 1 ROWS ONLY;

SELECT @p4id = ProductoID, @p4nom = Nombre, @p4pre = Precio
FROM   productos WHERE Disponible = 1
ORDER BY ProductoID ASC OFFSET 3 ROWS FETCH NEXT 1 ROWS ONLY;

-- Si hay menos de 4 productos, reutilizar el primero para no romper la inserción
IF @p2id IS NULL SET @p2id = @p1id; IF @p2nom IS NULL SET @p2nom = @p1nom; IF @p2pre IS NULL SET @p2pre = @p1pre;
IF @p3id IS NULL SET @p3id = @p1id; IF @p3nom IS NULL SET @p3nom = @p1nom; IF @p3pre IS NULL SET @p3pre = @p1pre;
IF @p4id IS NULL SET @p4id = @p1id; IF @p4nom IS NULL SET @p4nom = @p1nom; IF @p4pre IS NULL SET @p4pre = @p1pre;

-- ============================================================
-- 3. PEDIDOS
-- ============================================================

-- ── Pedido A: PAGADO — hace 22 min, pago online ─────────────
INSERT INTO pedidos
    (ClienteID, FechaCreacion, Estado, Total, DireccionEntrega, TelefonoEntrega,
     forma_pago, lat_entrega, lng_entrega)
VALUES
    (@c1, DATEADD(MINUTE, -22, GETUTCDATE()), N'pagado', @p1pre * 1 + @p2pre * 2,
     N'Avenida Miguel de Cervantes 79 1B', N'+34611222333',
     N'online', 40.00618, -3.00103);

DECLARE @pedA INT = SCOPE_IDENTITY();

-- ── Pedido B: EN_PREPARACION — hace 35 min, contra reembolso ─
INSERT INTO pedidos
    (ClienteID, FechaCreacion, Estado, Total, DireccionEntrega, TelefonoEntrega,
     forma_pago, lat_entrega, lng_entrega)
VALUES
    (@c2, DATEADD(MINUTE, -35, GETUTCDATE()), N'en_preparacion', @p3pre * 3,
     N'Paseo de la Estación 5', N'+34622333444',
     N'contra_reembolso', 40.00287, -3.00521);

DECLARE @pedB INT = SCOPE_IDENTITY();

-- ── Pedido C: PREPARADO — hace 50 min, pago online ───────────
INSERT INTO pedidos
    (ClienteID, FechaCreacion, Estado, Total, DireccionEntrega, TelefonoEntrega,
     forma_pago, lat_entrega, lng_entrega)
VALUES
    (@c3, DATEADD(MINUTE, -50, GETUTCDATE()), N'preparado', @p4pre * 2 + @p1pre * 1,
     N'Calle Los Labradores 5', N'+34633444555',
     N'online', 40.00752, -3.00248);

DECLARE @pedC INT = SCOPE_IDENTITY();

-- ============================================================
-- 4. LÍNEAS DE DETALLE
-- ============================================================

-- Pedido A: 1× prod1, 2× prod2
INSERT INTO pedido_detalles (PedidoID, ProductoID, Cantidad, PrecioUnitario, NombreProducto, Subtotal) VALUES
    (@pedA, @p1id, 1, @p1pre, @p1nom, @p1pre * 1),
    (@pedA, @p2id, 2, @p2pre, @p2nom, @p2pre * 2);

-- Pedido B: 3× prod3
INSERT INTO pedido_detalles (PedidoID, ProductoID, Cantidad, PrecioUnitario, NombreProducto, Subtotal) VALUES
    (@pedB, @p3id, 3, @p3pre, @p3nom, @p3pre * 3);

-- Pedido C: 2× prod4, 1× prod1
INSERT INTO pedido_detalles (PedidoID, ProductoID, Cantidad, PrecioUnitario, NombreProducto, Subtotal) VALUES
    (@pedC, @p4id, 2, @p4pre, @p4nom, @p4pre * 2),
    (@pedC, @p1id, 1, @p1pre, @p1nom, @p1pre * 1);

-- ============================================================
-- 5. HISTORIAL DE ESTADOS
-- ============================================================

-- Pedido A: llegó a pagado
INSERT INTO historial_estados_pedido (pedido_id, estado_anterior, estado_nuevo, cambiado_en, notas) VALUES
    (@pedA, N'Pendiente',        N'enlace',            DATEADD(MINUTE, -22, GETUTCDATE()), N'Seed prueba'),
    (@pedA, N'enlace',           N'enlace2',            DATEADD(MINUTE, -21, GETUTCDATE()), NULL),
    (@pedA, N'enlace2',          N'confirmando-pago',   DATEADD(MINUTE, -20, GETUTCDATE()), NULL),
    (@pedA, N'confirmando-pago', N'pagado',             DATEADD(MINUTE, -19, GETUTCDATE()), N'Webhook Monei OK');

-- Pedido B: llegó a en_preparacion
INSERT INTO historial_estados_pedido (pedido_id, estado_anterior, estado_nuevo, cambiado_en, notas) VALUES
    (@pedB, N'Pendiente',        N'enlace',             DATEADD(MINUTE, -35, GETUTCDATE()), N'Seed prueba'),
    (@pedB, N'enlace',           N'enlace2',            DATEADD(MINUTE, -34, GETUTCDATE()), NULL),
    (@pedB, N'enlace2',          N'contra_reembolso',   DATEADD(MINUTE, -33, GETUTCDATE()), NULL),
    (@pedB, N'contra_reembolso', N'en_preparacion',     DATEADD(MINUTE, -28, GETUTCDATE()), N'Picker asignado');

-- Pedido C: llegó a preparado
INSERT INTO historial_estados_pedido (pedido_id, estado_anterior, estado_nuevo, cambiado_en, notas) VALUES
    (@pedC, N'Pendiente',        N'enlace',             DATEADD(MINUTE, -50, GETUTCDATE()), N'Seed prueba'),
    (@pedC, N'enlace',           N'enlace2',            DATEADD(MINUTE, -49, GETUTCDATE()), NULL),
    (@pedC, N'enlace2',          N'confirmando-pago',   DATEADD(MINUTE, -48, GETUTCDATE()), NULL),
    (@pedC, N'confirmando-pago', N'pagado',             DATEADD(MINUTE, -47, GETUTCDATE()), N'Webhook Monei OK'),
    (@pedC, N'pagado',           N'en_preparacion',     DATEADD(MINUTE, -40, GETUTCDATE()), N'Picking iniciado'),
    (@pedC, N'en_preparacion',   N'preparado',          DATEADD(MINUTE, -15, GETUTCDATE()), N'Picking completado');

-- ============================================================
-- 6. PAGO (online) para pedidos A y C
-- ============================================================

INSERT INTO pagos (pedido_id, proveedor, referencia_externa, estado, importe, moneda, created_at) VALUES
    (@pedA, N'monei', N'TEST-MONEI-A-001', N'completado', @p1pre * 1 + @p2pre * 2, N'EUR', DATEADD(MINUTE, -19, GETUTCDATE())),
    (@pedC, N'monei', N'TEST-MONEI-C-001', N'completado', @p4pre * 2 + @p1pre * 1, N'EUR', DATEADD(MINUTE, -47, GETUTCDATE()));

-- ============================================================
-- 7. PICKING para pedidos B (en curso) y C (completado)
-- ============================================================

-- Buscar un picker disponible (cualquier empleado activo)
DECLARE @picker INT = (SELECT TOP 1 EmpleadoID FROM empleados WHERE activo = 1 ORDER BY EmpleadoID);

-- Pedido B: picking en proceso
INSERT INTO picking_pedido (pedido_id, empleado_id, estado, iniciado_en, created_at) VALUES
    (@pedB, @picker, N'en_proceso', DATEADD(MINUTE, -28, GETUTCDATE()), DATEADD(MINUTE, -28, GETUTCDATE()));

DECLARE @pkB INT = SCOPE_IDENTITY();

-- Items del picking B: el único detalle como "pendiente"
INSERT INTO picking_items (picking_id, pedido_detalle_id, estado)
SELECT @pkB, DetalleID, N'pendiente'
FROM   pedido_detalles
WHERE  PedidoID = @pedB;

-- Pedido C: picking completado
INSERT INTO picking_pedido (pedido_id, empleado_id, estado, iniciado_en, completado_en, created_at) VALUES
    (@pedC, @picker, N'completado',
     DATEADD(MINUTE, -40, GETUTCDATE()),
     DATEADD(MINUTE, -15, GETUTCDATE()),
     DATEADD(MINUTE, -40, GETUTCDATE()));

DECLARE @pkC INT = SCOPE_IDENTITY();

INSERT INTO picking_items (picking_id, pedido_detalle_id, estado, cantidad_encontrada)
SELECT @pkC, DetalleID, N'encontrado', Cantidad
FROM   pedido_detalles
WHERE  PedidoID = @pedC;

-- ============================================================
-- 8. RESUMEN
-- ============================================================

SELECT
    N'Pedido A (pagado)'       AS Descripcion, @pedA AS PedidoID, N'Ana García López'    AS Cliente UNION ALL
SELECT
    N'Pedido B (en_preparacion)', @pedB,        N'Carlos Martínez Ruiz' UNION ALL
SELECT
    N'Pedido C (preparado)',    @pedC,           N'Laura Sánchez Mora';

COMMIT TRANSACTION;
