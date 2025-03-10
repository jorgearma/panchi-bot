import pyodbc

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
        driver="ODBC Driver 17 for SQL Server",
        server="localhost,1433",
        database="pruebabot;",
        uid="sa",
        pwd="Jorgejorge1"
    )
    return db.connect()



from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Definir la base para los modelos
Base = declarative_base()

# URL de conexión a SQL Server (asegúrate de que sea correcta)
DATABASE_URL = "mssql+pyodbc://sa:Jorgejorge1@localhost:1433/pruebabot?driver=ODBC+Driver+17+for+SQL+Server"

# Crear el motor de la base de datos
engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)

# 📌 Crear un `SessionLocal` reutilizable en toda la aplicación
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# 📌 Crear una única sesión que se usará en toda la aplicación
db_session = SessionLocal()

# 📌 Función para inicializar la base de datos (crear tablas)
def conectar_bd1():
    """Crea todas las tablas en la base de datos si no existen."""
    try:

        from models import Usuario , Pedido , PedidoDetalle , Producto 
        
        Base.metadata.create_all(engine, tables=[Usuario.__table__])  # Crea `usuarios` primero
        Base.metadata.create_all(engine, tables=[Producto.__table__])
        Base.metadata.create_all(engine, tables=[Pedido.__table__]) 
        Base.metadata.create_all(engine, tables=[PedidoDetalle.__table__])
        
        print("✅ Base de datos inicializada correctamente.")
    except Exception as e:
        print(f"❌ Error al inicializar la base de datos: {e}")

# Ejecutar la inicialización al importar el módulo
conectar_bd1()