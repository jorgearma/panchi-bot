-- Ejecutar en producción ANTES de desplegar el código
CREATE TABLE check_ins (
    id          INT IDENTITY(1,1) PRIMARY KEY,
    empleado_id INT NOT NULL REFERENCES empleados(EmpleadoID),
    fecha       DATE NOT NULL,
    inicio      DATETIME NOT NULL,
    fin         DATETIME NULL,
    created_at  DATETIME NOT NULL DEFAULT GETUTCDATE(),
    CONSTRAINT uq_checkin_empleado_fecha UNIQUE (empleado_id, fecha)
);

GO

CREATE TABLE tramos_turno (
    id           INT IDENTITY(1,1) PRIMARY KEY,
    check_in_id  INT NOT NULL REFERENCES check_ins(id),
    rol          VARCHAR(20) NOT NULL,
    inicio       DATETIME NOT NULL,
    fin          DATETIME NULL
);
