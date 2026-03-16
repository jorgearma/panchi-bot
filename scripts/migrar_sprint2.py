"""
Migración Sprint 2: crea tablas nuevas y añade columnas a empleados.

Ejecutar una sola vez:
    source venv/bin/activate
    python scripts/migrar_sprint2.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from database import SessionLocal, engine, Base
from models import Rol, Empleado, PickingPedido, PickingItem, Reparto, Incidencia


COLUMNAS_NUEVAS = [
    ("empleados", "rol_id",        "INT NULL"),
    ("empleados", "activo",        "BIT NOT NULL DEFAULT 1"),
    ("empleados", "password_hash", "NVARCHAR(255) NULL"),
]

ROLES_INICIALES = [
    ("admin",       "Acceso total al sistema"),
    ("picker",      "Preparación de pedidos en almacén"),
    ("repartidor",  "Entrega de pedidos a domicilio"),
    ("supervisor",  "Supervisión de operaciones"),
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


def paso1_columnas_empleados():
    print("=== Paso 1: Columnas nuevas en empleados ===")
    with engine.connect() as conn:
        for tabla, columna, definicion in COLUMNAS_NUEVAS:
            if columna_existe(conn, tabla, columna):
                print(f"  [=] {tabla}.{columna} ya existe")
            else:
                conn.execute(text(f"ALTER TABLE {tabla} ADD {columna} {definicion}"))
                conn.commit()
                print(f"  [+] {tabla}.{columna} añadida")


def paso2_tablas_nuevas():
    print("\n=== Paso 2: Crear tablas nuevas ===")
    tablas = [
        (Rol,         "roles"),
        (PickingPedido, "picking_pedido"),
        (PickingItem,   "picking_items"),
        (Reparto,       "repartos"),
        (Incidencia,    "incidencias"),
    ]
    with engine.connect() as conn:
        for modelo, nombre_tabla in tablas:
            if tabla_existe(conn, nombre_tabla):
                print(f"  [=] {nombre_tabla} ya existe")
            else:
                Base.metadata.create_all(engine, tables=[modelo.__table__])
                print(f"  [+] {nombre_tabla} creada")


def paso3_roles_iniciales():
    print("\n=== Paso 3: Insertar roles iniciales ===")
    session = SessionLocal()
    try:
        for nombre, descripcion in ROLES_INICIALES:
            existente = session.query(Rol).filter_by(nombre=nombre).first()
            if not existente:
                session.add(Rol(nombre=nombre, descripcion=descripcion))
                print(f"  [+] Rol creado: '{nombre}'")
            else:
                print(f"  [=] Ya existe: '{nombre}'")
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"  ❌ Error: {e}")
        raise
    finally:
        session.close()


def paso4_fk_empleados_roles():
    """Añade la FK de empleados.rol_id → roles.id si no existe."""
    print("\n=== Paso 4: FK empleados → roles ===")
    with engine.connect() as conn:
        r = conn.execute(text(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS "
            "WHERE CONSTRAINT_NAME = 'fk_empleados_rol'"
        ))
        if r.scalar() > 0:
            print("  [=] FK ya existe")
            return
        try:
            conn.execute(text(
                "ALTER TABLE empleados ADD CONSTRAINT fk_empleados_rol "
                "FOREIGN KEY (rol_id) REFERENCES roles(id)"
            ))
            conn.commit()
            print("  [+] FK añadida")
        except Exception as e:
            print(f"  ⚠️  No se pudo añadir FK (puede que ya exista): {e}")


if __name__ == "__main__":
    paso1_columnas_empleados()
    paso2_tablas_nuevas()
    paso3_roles_iniciales()
    paso4_fk_empleados_roles()
    print("\n✅ Migración Sprint 2 completada.")
