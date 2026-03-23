-- ============================================================
-- SEED TURNOS UI
-- Crea turnos de hoy para empleados 1, 2 y 4.
-- Idempotente: si ya existe el mismo turno, no lo duplica.
-- ============================================================

DECLARE @hoy DATE = CAST(GETDATE() AS DATE);

-- Empleado 1
IF EXISTS (
    SELECT 1
    FROM empleados
    WHERE EmpleadoID = 1
)
AND NOT EXISTS (
    SELECT 1
    FROM turnos
    WHERE empleado_id = 1
      AND fecha = @hoy
      AND hora_inicio = '09:00:00'
      AND hora_fin = '13:00:00'
)
BEGIN
    INSERT INTO turnos (
        empleado_id,
        fecha,
        hora_inicio,
        hora_fin,
        notas,
        estado,
        tipo,
        creado_por
    )
    VALUES (
        1,
        @hoy,
        '09:00:00',
        '13:00:00',
        N'Turno de prueba para UI',
        'planificado',
        'manana',
        NULL
    );
END;

-- Empleado 2
IF EXISTS (
    SELECT 1
    FROM empleados
    WHERE EmpleadoID = 2
)
AND NOT EXISTS (
    SELECT 1
    FROM turnos
    WHERE empleado_id = 2
      AND fecha = @hoy
      AND hora_inicio = '13:00:00'
      AND hora_fin = '17:00:00'
)
BEGIN
    INSERT INTO turnos (
        empleado_id,
        fecha,
        hora_inicio,
        hora_fin,
        notas,
        estado,
        tipo,
        creado_por
    )
    VALUES (
        2,
        @hoy,
        '13:00:00',
        '17:00:00',
        N'Turno de prueba para UI',
        'planificado',
        'tarde',
        NULL
    );
END;

-- Empleado 4
IF EXISTS (
    SELECT 1
    FROM empleados
    WHERE EmpleadoID = 4
)
AND NOT EXISTS (
    SELECT 1
    FROM turnos
    WHERE empleado_id = 4
      AND fecha = @hoy
      AND hora_inicio = '20:00:00'
      AND hora_fin = '23:30:00'
)
BEGIN
    INSERT INTO turnos (
        empleado_id,
        fecha,
        hora_inicio,
        hora_fin,
        notas,
        estado,
        tipo,
        creado_por
    )
    VALUES (
        4,
        @hoy,
        '20:00:00',
        '23:30:00',
        N'Turno de prueba para UI',
        'planificado',
        'noche',
        NULL
    );
END;

SELECT
    id,
    empleado_id,
    fecha,
    hora_inicio,
    hora_fin,
    estado,
    tipo,
    notas
FROM turnos
WHERE fecha = @hoy
  AND empleado_id IN (1, 2, 4)
ORDER BY empleado_id, hora_inicio;
