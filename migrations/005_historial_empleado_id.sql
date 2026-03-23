-- Migración 005: Añadir empleado_id al historial de estados de pedido
IF COL_LENGTH('historial_estados_pedido', 'empleado_id') IS NULL
    ALTER TABLE historial_estados_pedido
    ADD empleado_id INT NULL REFERENCES empleados(EmpleadoID);
GO
