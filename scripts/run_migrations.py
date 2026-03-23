"""Ejecuta todas las migraciones SQL en orden desde el directorio migrations/."""
import os
import sys
import glob
from pathlib import Path

import pyodbc
from dotenv import load_dotenv

load_dotenv()

SERVER   = os.getenv('SQL_SERVER')
DATABASE = os.getenv('SQL_DATABASE')
UID      = os.getenv('SQL_UID')
PWD      = os.getenv('SQL_PWD')

conn_str = (
    f"DRIVER={{ODBC Driver 18 for SQL Server}};"
    f"SERVER={SERVER};DATABASE={DATABASE};UID={UID};PWD={PWD};"
    "TrustServerCertificate=yes;"
)

migrations_dir = Path(__file__).parent.parent / 'migrations'
sql_files = sorted(migrations_dir.glob('*.sql'))

if not sql_files:
    print("No se encontraron archivos .sql en migrations/")
    sys.exit(0)

print(f"Conectando a {SERVER}/{DATABASE}...")
try:
    conn = pyodbc.connect(conn_str, autocommit=True)
    cursor = conn.cursor()
    print("Conexión OK\n")
except Exception as e:
    print(f"Error de conexión: {e}")
    sys.exit(1)

for sql_file in sql_files:
    print(f"  Ejecutando {sql_file.name}...", end=' ')
    sql = sql_file.read_text(encoding='utf-8')
    # Dividir por GO (separador de batches de SQL Server)
    batches = [b.strip() for b in sql.split('\nGO') if b.strip()]
    try:
        for batch in batches:
            # Eliminar líneas que son solo comentarios y ver si queda SQL real
            lines = [l for l in batch.splitlines() if not l.strip().startswith('--')]
            sql_real = '\n'.join(lines).strip()
            if sql_real:
                cursor.execute(batch)
        print("OK")
    except Exception as e:
        print(f"ERROR\n    {e}")

cursor.close()
conn.close()
print("\nMigraciones completadas.")
