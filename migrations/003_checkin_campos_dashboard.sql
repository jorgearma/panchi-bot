-- Migración 003: Campos de dashboard en check_ins + eliminar unique constraint por fecha
-- Ejecutar en producción ANTES de desplegar el código

-- 1. Eliminar unique constraint que impide turnos AM+PM el mismo día
IF EXISTS (
    SELECT 1 FROM sys.key_constraints
    WHERE name = 'uq_checkin_empleado_fecha' AND type = 'UQ'
)
    ALTER TABLE check_ins DROP CONSTRAINT uq_checkin_empleado_fecha;
GO

-- 2. Añadir FK al turno planificado (nullable: fichajes espontáneos no tienen turno)
IF COL_LENGTH('check_ins', 'turno_id') IS NULL
    ALTER TABLE check_ins ADD turno_id INT NULL REFERENCES turnos(id);
GO

-- 3. Estado de validación para flujo de revisión del supervisor
IF COL_LENGTH('check_ins', 'estado_validacion') IS NULL
    ALTER TABLE check_ins ADD estado_validacion VARCHAR(20) NOT NULL DEFAULT 'pendiente';
GO

-- 4. Minutos de desfase respecto al turno (positivo = tarde, negativo = adelantado)
IF COL_LENGTH('check_ins', 'minutos_tarde') IS NULL
    ALTER TABLE check_ins ADD minutos_tarde INT NULL;
GO
