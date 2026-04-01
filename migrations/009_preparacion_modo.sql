-- Migration 009: añade columna modo a picking_pedido
-- warehouse (defecto): flujo con items y validación de stock
-- restaurant: preparación sin items, marcar listo directamente

ALTER TABLE picking_pedido
  ADD modo VARCHAR(20) NOT NULL DEFAULT 'warehouse';
