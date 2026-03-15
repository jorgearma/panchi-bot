import os
import urllib.parse
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

params = urllib.parse.quote_plus(
    f"DRIVER=ODBC Driver 18 for SQL Server;"
    f"SERVER={os.environ.get('SQL_SERVER', 'localhost,1433')};"
    f"DATABASE={os.environ.get('SQL_DATABASE', 'pruebabot')};"
    f"UID={os.environ.get('SQL_UID', 'sa')};"
    f"PWD={os.environ.get('SQL_PWD', '')};"
    "TrustServerCertificate=yes;"
)


# Crear el motor con timeouts y pooling
engine = create_engine(
    f"mssql+pyodbc:///?odbc_connect={params}",
    echo=False,
    pool_pre_ping=True,       # Verifica que la conexión esté viva
    pool_timeout=5,           # ⏱ Tiempo máximo para obtener una conexión del pool
    connect_args={"timeout": 5}  # ⏱ Tiempo máximo al conectar con la DB
)

# Base y sesión
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    """Devuelve la sesión asociada al request actual (via Flask g)."""
    from flask import g
    if 'db' not in g:
        g.db = SessionLocal()
    return g.db


def close_db(e=None):
    """Cierra la sesión al final del request. Registrar con app.teardown_appcontext."""
    from flask import g
    db = g.pop('db', None)
    if db is not None:
        db.close()

# 📌 Función para inicializar la base de datos (crear tablas)
def conectar_bd1():
    """Crea todas las tablas en la base de datos si no existen."""
    try:

        from models import Usuario , Pedido , PedidoDetalle , Producto , Empleado
        
        Base.metadata.create_all(engine, tables=[Usuario.__table__])  # Crea `usuarios` primero
        Base.metadata.create_all(engine, tables=[Producto.__table__])
        Base.metadata.create_all(engine, tables=[Pedido.__table__]) 
        Base.metadata.create_all(engine, tables=[PedidoDetalle.__table__])
        Base.metadata.create_all(engine, tables=[Empleado.__table__])
        
        print("✅ Base de datos inicializada correctamente.")
    except Exception as e:
        print(f"❌ Error al inicializar la base de datos: {e}")

