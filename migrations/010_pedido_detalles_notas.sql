-- Migración 010: añade columna Notas a pedido_detalles
-- Permite registrar instrucciones especiales por línea de pedido
-- (ej. "Sin: cebolla, ajo") que llegan desde el menú web del cliente.
--
-- Ejecutar: una sola vez en producción y en desarrollo.

ALTER TABLE pedido_detalles
  ADD Notas NVARCHAR(300) NULL;
