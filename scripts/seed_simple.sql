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