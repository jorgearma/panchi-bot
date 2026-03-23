-- Migración 008: Tabla de métricas diarias por empleado (caché para dashboard)
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'metricas_diarias_empleado')
BEGIN
    CREATE TABLE metricas_diarias_empleado (
        id                        INT IDENTITY(1,1) PRIMARY KEY,
        empleado_id               INT NOT NULL REFERENCES empleados(EmpleadoID),
        fecha                     DATE NOT NULL,
        rol                       VARCHAR(20) NOT NULL,          -- picker | repartidor
        horas_trabajadas_min      INT NULL,                      -- minutos totales trabajados
        pedidos_completados       INT NOT NULL DEFAULT 0,
        tiempo_medio_operacion_min INT NULL,                     -- media picking o reparto en min
        incidencias               INT NOT NULL DEFAULT 0,
        minutos_tarde             INT NULL,                      -- del check-in del día
        calculado_en              DATETIME NOT NULL DEFAULT GETUTCDATE(),

        CONSTRAINT uq_metrica_empleado_fecha_rol UNIQUE (empleado_id, fecha, rol)
    );
END
GO
