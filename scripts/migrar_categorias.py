"""
Migración Sprint 1: añade columnas nuevas a tablas existentes, pobla `categorias`
y enlaza categoria_id en productos.

Ejecutar una sola vez:
    source venv/bin/activate
    python scripts/migrar_categorias.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from database import SessionLocal, engine
from models import Producto, Categoria


# Columnas a añadir: (tabla, columna, definición SQL)
COLUMNAS_NUEVAS = [
    ("productos",       "categoria_id",     "INT NULL"),
    ("productos",       "created_at",       "DATETIME2 NULL DEFAULT SYSUTCDATETIME()"),
    ("productos",       "updated_at",       "DATETIME2 NULL"),
    ("pedidos",         "FechaActualizacion","DATETIME2 NULL"),
    ("pedido_detalles", "PrecioUnitario",   "DECIMAL(10,2) NULL"),
    ("pedido_detalles", "NombreProducto",   "NVARCHAR(255) NULL"),
    ("empleados",       "created_at",       "DATETIME2 NULL DEFAULT SYSUTCDATETIME()"),
    ("empleados",       "updated_at",       "DATETIME2 NULL"),
]


def columna_existe(conn, tabla, columna):
    resultado = conn.execute(text(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_NAME = :tabla AND COLUMN_NAME = :columna"
    ), {"tabla": tabla, "columna": columna})
    return resultado.scalar() > 0


def añadir_columnas():
    with engine.connect() as conn:
        for tabla, columna, definicion in COLUMNAS_NUEVAS:
            if columna_existe(conn, tabla, columna):
                print(f"  [=] {tabla}.{columna} ya existe, omitiendo")
            else:
                conn.execute(text(f"ALTER TABLE {tabla} ADD {columna} {definicion}"))
                conn.commit()
                print(f"  [+] {tabla}.{columna} añadida")


def migrar_categorias():
    session = SessionLocal()
    try:
        # Categorías únicas actuales en productos
        categorias_existentes = (
            session.query(Producto.Categoria)
            .distinct()
            .filter(Producto.Categoria.isnot(None))
            .all()
        )
        nombres = sorted({row.Categoria.strip() for row in categorias_existentes if row.Categoria})

        if not nombres:
            print("No se encontraron categorías en productos.")
            return

        print(f"\nCategorías encontradas: {nombres}")

        # Insertar en categorias
        for orden, nombre in enumerate(nombres):
            existente = session.query(Categoria).filter_by(nombre=nombre).first()
            if not existente:
                session.add(Categoria(nombre=nombre, orden_display=orden))
                print(f"  [+] Categoría creada: '{nombre}'")
            else:
                print(f"  [=] Ya existe: '{nombre}'")
        session.commit()

        # Enlazar categoria_id en cada producto
        categorias_map = {c.nombre: c.id for c in session.query(Categoria).all()}
        productos = session.query(Producto).all()
        actualizados = 0
        for producto in productos:
            cat_nombre = producto.Categoria.strip() if producto.Categoria else None
            cat_id = categorias_map.get(cat_nombre)
            if cat_id and producto.categoria_id != cat_id:
                producto.categoria_id = cat_id
                actualizados += 1

        session.commit()
        print(f"\n✅ {actualizados} productos enlazados a su categoria_id.")

    except Exception as e:
        session.rollback()
        print(f"❌ Error: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    print("=== Paso 1: Añadir columnas nuevas ===")
    añadir_columnas()

    print("\n=== Paso 2: Migrar categorías ===")
    migrar_categorias()

    print("\n✅ Migración Sprint 1 completada.")
