import os
import pyodbc
import urllib.parse
from dotenv import load_dotenv

load_dotenv()

class DatabaseConnection:
    def __init__(self, driver, server, database, uid, pwd):
        self.driver = driver
        self.server = server
        self.database = database
        self.uid = uid
        self.pwd = pwd
        self.connection = None

    def connect(self):
        try:
            self.connection = pyodbc.connect(
                f"DRIVER={{{self.driver}}};"
                f"SERVER={self.server};"
                f"DATABASE={self.database};"
                f"UID={self.uid};"
                f"PWD={self.pwd}"
            )
            print("Conexión exitosa a la base de datos SQL Server")
            return self.connection
        except Exception as e:
            print("Error al conectar con la base de datos:", e)
            return None

    def close(self):
        if self.connection:
            self.connection.close()
            print("Conexión cerrada")

# Función global para mantener compatibilidad
def conectar_bd():
    db = DatabaseConnection(
        driver="ODBC Driver 18 for SQL Server",
        server=os.environ.get('SQL_SERVER', 'localhost,1433'),
        database=os.environ.get('SQL_DATABASE', 'pruebabot'),
        uid=os.environ.get('SQL_UID', 'sa'),
        pwd=os.environ.get('SQL_PWD', '')
    )
    return db.connect()



from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Definir la base para los modelos
Base = declarative_base()

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
db_session = SessionLocal()

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

# Ejecutar la inicialización al importar el módulo
conectar_bd1()