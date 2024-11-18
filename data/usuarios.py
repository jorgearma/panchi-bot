import pyodbc
from database import conectar_bd
from menu import mostrar_menu
from utils.mensajes import enviar_mensaje_whatsapp
from data.estado_usuarios import estado_usuarios


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


def verificar_usuario_bd(numero_cliente):
    try:
        connection = conectar_bd()
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


def manejar_usuario(numero_cliente ):
    from data.carrito import carrito
    if estado_usuarios.get(numero_cliente, {}).get("recien_registrado"):
        del estado_usuarios[numero_cliente]["recien_registrado"]
    else:
        if numero_cliente not in carrito:
            carrito[numero_cliente] = []
            menu_texto = mostrar_menu()
            nombre_usuario = obtener_usuario_bd(numero_cliente)["nombre"]
            enviar_mensaje_whatsapp(
                f"¡Hola {nombre_usuario}! 👋 Bienvenido de nuevo. {menu_texto}                ⬆️ *MENU* ⬆️ \n❗*Para agregar un producto*❗\n\nescribe el *numero* o su *nombre* \n\n      👇 *Ejemplos* 👇 \n\n ▪️ *clasica*    o    *301* \n ▪️ *helado*    o    *503* ", 
                numero_cliente
            )
            return "Mensaje enviado", 200
