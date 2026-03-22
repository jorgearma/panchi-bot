-- Migración 007: Self-referencia en turnos para trazabilidad de cambios
IF COL_LENGTH('turnos', 'turno_origen_id') IS NULL
    ALTER TABLE turnos ADD turno_origen_id INT NULL REFERENCES turnos(id);
GO
