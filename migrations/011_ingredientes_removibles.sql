-- Migración 011: añade columna IngredientesRemovibles a productos
-- Permite distinguir entre ingredientes de descripción (Ingredientes)
-- e ingredientes que el cliente puede pedir que quiten (IngredientesRemovibles).
-- NULL o cadena vacía = ningún ingrediente es removible (ej. bebidas).
--
-- Ejecutar: una sola vez en producción y en desarrollo.

ALTER TABLE productos
  ADD IngredientesRemovibles NVARCHAR(255) NULL;
