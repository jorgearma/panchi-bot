import pyodbc

def conectar_bd():
    try:
        connection = pyodbc.connect(
            "DRIVER={ODBC Driver 17 for SQL Server};"
            "SERVER=localhost,1433;"
            "DATABASE=pruebabot;"
            "UID=sa;"
            "PWD=Jorgejorge1"
        )
        print("Conexión exitosa a la base de datos SQL Server")
        return connection
    except Exception as e:
        print("Error al conectar con la base de datos:", e)
        return None