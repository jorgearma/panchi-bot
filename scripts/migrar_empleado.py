"""
Migración: Zona de empleados — estado_operativo + tabla turnos

Ejecutar una sola vez:
    python scripts/migrar_empleado.py

Es idempotente: comprueba si la columna/tabla ya existen antes de crearlas.
"""
import os
import sys

import pyodbc

SQL_SERVER   = os.environ.get('SQL_SERVER',   'localhost,1433')
SQL_DATABASE = os.environ.get('SQL_DATABASE', 'pruebabot')
SQL_UID      = os.environ.get('SQL_UID',      '')
SQL_PWD      = os.environ.get('SQL_PWD',      '')

CONN_STR = (
    f"DRIVER={{ODBC Driver 18 for SQL Server}};"
    f"SERVER={SQL_SERVER};DATABASE={SQL_DATABASE};"
    f"UID={SQL_UID};PWD={SQL_PWD};"
    f"TrustServerCertificate=yes"
)

ADD_COLUMN = """
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'empleados' AND COLUMN_NAME = 'estado_operativo'
)
BEGIN
    ALTER TABLE empleados
    ADD estado_operativo VARCHAR(20) NOT NULL DEFAULT 'desconectado';
    PRINT 'Columna estado_operativo añadida.';
END
ELSE
    PRINT 'Columna estado_operativo ya existe — omitida.';
"""

CREATE_TURNOS = """
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME = 'turnos'
)
BEGIN
    CREATE TABLE turnos (
        id          INT PRIMARY KEY IDENTITY,
        empleado_id INT NOT NULL REFERENCES empleados(EmpleadoID),
        fecha       DATE NOT NULL,
        hora_inicio TIME NOT NULL,
        hora_fin    TIME NOT NULL,
        notas       VARCHAR(255) NULL,
        created_at  DATETIME NOT NULL DEFAULT GETUTCDATE()
    );
    PRINT 'Tabla turnos creada.';
END
ELSE
    PRINT 'Tabla turnos ya existe — omitida.';
"""


def run():
    print(f"Conectando a {SQL_SERVER}/{SQL_DATABASE}…")
    conn = pyodbc.connect(CONN_STR, autocommit=True)
    cursor = conn.cursor()

    print("Aplicando ADD COLUMN estado_operativo…")
    cursor.execute(ADD_COLUMN)

    print("Aplicando CREATE TABLE turnos…")
    cursor.execute(CREATE_TURNOS)

    cursor.close()
    conn.close()
    print("Migración completada.")


if __name__ == '__main__':
    try:
        run()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
