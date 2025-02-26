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