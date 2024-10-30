from flask import Flask, request
from controllers.registro import manejar_registro
from controllers.mensajes_registrados import manejar_mensajes_registrados
from data.usuarios import usuarios_registrados , guardar_usuario_bd
from data.carrito import carrito
from data.estado_usuarios import estado_usuarios
import pyodbc

app = Flask(__name__)

def conectar_bd():
    try:
        connection = pyodbc.connect(
            "DRIVER={ODBC Driver 17 for SQL Server};"
            "SERVER=localhost,1433;"
            "DATABASE=master;"
            "UID=sa;"
            "PWD=Jorgejorge1"
        )
        print("Conexión exitosa a la base de datos SQL Server")
        return connection
    except Exception as e:
        print("Error al conectar con la base de datos:", e)
        return None


def verificar_usuario_bd(numero_cliente):
    try:
        connection = pyodbc.connect(
            "DRIVER={ODBC Driver 17 for SQL Server};"
            "SERVER=localhost,1433;"
            "DATABASE=pruebabot;"
            "UID=sa;"
            "PWD=Jorgejorge1"
        )
        cursor = connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM usuarios WHERE numero_cliente = ?", numero_cliente)
        result = cursor.fetchone()
        return result[0] > 0
    except Exception as e:
        print("Error al verificar el usuario en la base de datos:", e)
        return False
    finally:
        if connection:
            connection.close()

@app.route('/webhook', methods=['POST'])
def webhook():
    numero_cliente = request.form['From']
    mensaje_cliente = request.form['Body'].strip().lower()

    # Verificar si el usuario está registrado en la base de datos
    if not verificar_usuario_bd(numero_cliente):
        return manejar_registro(numero_cliente, mensaje_cliente)
    else:
        return manejar_mensajes_registrados(numero_cliente, mensaje_cliente)

if __name__ == "__main__":
    db_conn = conectar_bd()
    if db_conn:
        db_conn.close()
    app.run(debug=True, port=5000)

