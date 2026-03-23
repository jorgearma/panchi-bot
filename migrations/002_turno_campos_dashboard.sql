-- Migración 002: Campos de dashboard en tabla turnos
-- Ejecutar en producción ANTES de desplegar el código

IF COL_LENGTH('turnos', 'estado') IS NULL
    ALTER TABLE turnos ADD estado VARCHAR(20) NOT NULL DEFAULT 'planificado';
GO

IF COL_LENGTH('turnos', 'tipo') IS NULL
    ALTER TABLE turnos ADD tipo VARCHAR(20) NULL;
GO

IF COL_LENGTH('turnos', 'creado_por') IS NULL
    ALTER TABLE turnos ADD creado_por INT NULL REFERENCES empleados(EmpleadoID);
GO
