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

def obtener_usuario_bd(numero_cliente):
    try:
        connection = conectar_bd()
        cursor = connection.cursor()
        cursor.execute("SELECT nombre, numero_cliente, direccion FROM usuarios WHERE numero_cliente = ?", numero_cliente)
        result = cursor.fetchone()
        return {
            "nombre": result[0],
            "numero": result[1],
            "direccion": result[2]
        } if result else None
    except Exception as e:
        print("Error al obtener el usuario de la base de datos:", e)
        return None
    finally:
        if connection:
            connection.close()

def guardar_usuario_bd(numero, nombre, direccion):
    connection = conectar_bd()
    if connection:
        try:
            cursor = connection.cursor()
            cursor.execute("""
                INSERT INTO usuarios (nombre, numero_cliente, direccion)
                VALUES (?, ?, ?)
            """, (nombre, numero, direccion))
            connection.commit()
            print(f"Usuario {nombre} guardado en la base de datos.")
        except Exception as e:
            print("Error al guardar el usuario en la base de datos:", e)
        finally:
            connection.close()

def registrar_usuario(numero, nombre, direccion):
    # Registrar el usuario directamente en la base de datos
    guardar_usuario_bd(numero, nombre, direccion)
    
    # Devolver el usuario registrado
    return obtener_usuario_bd(numero)
