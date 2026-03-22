-- Migración 004: Tabla de ausencias de empleados
-- Ejecutar en producción ANTES de desplegar el código

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'ausencias')
BEGIN
    CREATE TABLE ausencias (
        id           INT IDENTITY(1,1) PRIMARY KEY,
        empleado_id  INT NOT NULL REFERENCES empleados(EmpleadoID),
        fecha        DATE NOT NULL,
        tipo         VARCHAR(30) NOT NULL,  -- vacaciones | baja_medica | personal | injustificada
        estado       VARCHAR(20) NOT NULL DEFAULT 'pendiente',  -- pendiente | aprobada | rechazada
        aprobado_por INT NULL REFERENCES empleados(EmpleadoID),
        aprobado_en  DATETIME NULL,
        notas        VARCHAR(500) NULL,
        created_at   DATETIME NOT NULL DEFAULT GETUTCDATE(),

        CONSTRAINT uq_ausencia_empleado_fecha UNIQUE (empleado_id, fecha)
    );
END
GO
