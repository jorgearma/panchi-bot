-- ============================================================
-- SEED SIMPLE
-- ============================================================

-- 1 CLIENTES
INSERT INTO usuarios (nombre, numero_cliente, direccion)
VALUES
(N'Ana García', N'whatsapp:+34611222333', N'Avenida Miguel de Cervantes 79 1B'),
(N'Carlos Martínez', N'whatsapp:+34622333444', N'Paseo de la Estación 5'),
(N'Laura Sánchez', N'whatsapp:+34633444555', N'Calle Los Labradores 5');


-- 2 PEDIDOS
INSERT INTO pedidos (
ClienteID,
Estado,
Total,
DireccionEntrega,
TelefonoEntrega,
forma_pago,
lat_entrega,
lng_entrega
)
SELECT id, N'pagado',12.50,
N'Avenida Miguel de Cervantes 79 1B',
N'+34611222333',
N'online',
40.00618,
-3.00103
FROM usuarios
WHERE numero_cliente=N'whatsapp:+34611222333'

UNION ALL

SELECT id, N'contra_reembolso',8.90,
N'Paseo de la Estación 5',
N'+34622333444',
N'contra_reembolso',
40.00287,
-3.00521
FROM usuarios
WHERE numero_cliente=N'whatsapp:+34622333444'

UNION ALL

SELECT id, N'pagado',19.75,
N'Calle Los Labradores 5',
N'+34633444555',
N'online',
40.00752,
-3.00248
FROM usuarios
WHERE numero_cliente=N'whatsapp:+34633444555';


-- 3 DETALLES
INSERT INTO pedido_detalles (
PedidoID,
ProductoID,
Cantidad,
PrecioUnitario,
NombreProducto,
Subtotal
)
SELECT
p.PedidoID,
pr.ProductoID,
2,
pr.Precio,
pr.Nombre,
pr.Precio*2
FROM pedidos p
JOIN usuarios u ON u.id=p.ClienteID
CROSS JOIN (
SELECT TOP 1 ProductoID,Nombre,Precio
FROM productos
WHERE Disponible=1
ORDER BY ProductoID
) pr
WHERE u.numero_cliente IN (
N'whatsapp:+34611222333',
N'whatsapp:+34622333444',
N'whatsapp:+34633444555'
);


-- 4 HISTORIAL
INSERT INTO historial_estados_pedido (
    pedido_id,
    estado_anterior,
    estado_nuevo,
    notas,
    cambiado_en
)
SELECT
    p.PedidoID,
    N'confirmando-pago',
    p.Estado,
    N'seed prueba',
    GETDATE()
FROM pedidos p
JOIN usuarios u ON u.id = p.ClienteID
WHERE u.numero_cliente IN (
    N'whatsapp:+34611222333',
    N'whatsapp:+34622333444',
    N'whatsapp:+34633444555'
);