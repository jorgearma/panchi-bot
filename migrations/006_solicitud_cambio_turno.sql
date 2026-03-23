-- Migración 006: Tabla de solicitudes de cambio de turno
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'solicitudes_cambio_turno')
BEGIN
    CREATE TABLE solicitudes_cambio_turno (
        id               INT IDENTITY(1,1) PRIMARY KEY,
        turno_cedido_id  INT NOT NULL REFERENCES turnos(id),
        solicitante_id   INT NOT NULL REFERENCES empleados(EmpleadoID),
        sustituto_id     INT NULL REFERENCES empleados(EmpleadoID),
        estado           VARCHAR(20) NOT NULL DEFAULT 'pendiente',  -- pendiente | aprobada | rechazada | cancelada
        aprobado_por     INT NULL REFERENCES empleados(EmpleadoID),
        aprobado_en      DATETIME NULL,
        motivo           VARCHAR(500) NULL,
        created_at       DATETIME NOT NULL DEFAULT GETUTCDATE()
    );
END
GO
