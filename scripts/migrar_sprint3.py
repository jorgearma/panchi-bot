"""
Migración Sprint 3: columnas de cancelación en pedidos + tabla audit_log.

Ejecutar una sola vez:
    source venv/bin/activate
    python scripts/migrar_sprint3.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from database import engine, Base
from models import AuditLog


COLUMNAS_NUEVAS = [
    ("pedidos", "cancel_reason",  "NVARCHAR(50) NULL"),
    ("pedidos", "cancelled_by",   "INT NULL"),
    ("pedidos", "cancelled_at",   "DATETIME NULL"),
]


def columna_existe(conn, tabla, columna):
    r = conn.execute(text(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_NAME = :t AND COLUMN_NAME = :c"
    ), {"t": tabla, "c": columna})
    return r.scalar() > 0


def tabla_existe(conn, tabla):
    r = conn.execute(text(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES "
        "WHERE TABLE_NAME = :t"
    ), {"t": tabla})
    return r.scalar() > 0


def paso1_columnas_pedidos():
    print("=== Paso 1: Columnas de cancelación en pedidos ===")
    with engine.connect() as conn:
        for tabla, columna, definicion in COLUMNAS_NUEVAS:
            if columna_existe(conn, tabla, columna):
                print(f"  [=] {tabla}.{columna} ya existe")
            else:
                conn.execute(text(f"ALTER TABLE {tabla} ADD {columna} {definicion}"))
                conn.commit()
                print(f"  [+] {tabla}.{columna} añadida")


def paso2_tabla_audit_log():
    print("\n=== Paso 2: Crear tabla audit_log ===")
    with engine.connect() as conn:
        if tabla_existe(conn, "audit_log"):
            print("  [=] audit_log ya existe")
        else:
            Base.metadata.create_all(engine, tables=[AuditLog.__table__])
            print("  [+] audit_log creada")


if __name__ == "__main__":
    paso1_columnas_pedidos()
    paso2_tabla_audit_log()
    print("\n✅ Migración Sprint 3 completada.")
