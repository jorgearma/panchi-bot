# data/usuarios.py

import pyodbc
usuarios_registrados = {
    "whatsapp:+453182209": {"nombre": "pendejo", "numero": "whatsapp:+4531822092", "direccion": "Calle Falsa 123"},
}

def obtener_usuario_bd(numero_cliente):
    try:
        connection = conectar_bd()
        cursor = connection.cursor()
        cursor.execute("SELECT nombre FROM usuarios WHERE numero_cliente = ?", numero_cliente)
        result = cursor.fetchone()
        return result[0] if result else None
    except Exception as e:
        print("Error al obtener el usuario de la base de datos:", e)
        return None
    finally:
        if connection:
            connection.close()

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

def registrar_usuario(numero, nombre, direccion, guardar_usuario_bd=None):
    # Registrar el usuario en el diccionario
    usuarios_registrados[numero] = {
        "nombre": nombre,
        "numero": numero,
        "direccion": direccion
    }
    
    # Llamar a la función de guardado en la base de datos si se proporciona
    if guardar_usuario_bd:
        guardar_usuario_bd(numero, nombre, direccion)
    
    return usuarios_registrados[numero]
