import pyodbc
from database import conectar_bd
from menu import mostrar_menu
from utils.mensajes import enviar_mensaje_whatsapp
from data.estado_usuarios import estado_usuarios


# Clases definidas anteriormente

class GestorUsuariosBD:
    @staticmethod
    def obtener_usuario(numero_cliente):
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

    @staticmethod
    def guardar_usuario(numero, nombre, direccion):
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

    @staticmethod
    def verificar_usuario(numero_cliente):
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


class GestorUsuarios:
    @staticmethod
    def registrar_usuario(numero, nombre, direccion):
        # Registrar el usuario directamente en la base de datos
        GestorUsuariosBD.guardar_usuario(numero, nombre, direccion)
        
        # Devolver el usuario registrado
        return GestorUsuariosBD.obtener_usuario(numero)

    @staticmethod
    def obtener_nombre_usuario(numero_cliente):
        nombre = obtener_usuario_bd(numero_cliente)
        return nombre["nombre"] 

    @staticmethod
    def manejar_usuario(numero_cliente):
        from data.carrito import carrito_instancia
        # Verifica si el usuario está recién registrado
        if estado_usuarios.get(numero_cliente, {}).get("recien_registrado"):
            del estado_usuarios[numero_cliente]["recien_registrado"]
        else:
            # Inicializa el carrito si el cliente no lo tiene
            if not carrito_instancia.verificar_carrito(numero_cliente):
                carrito_instancia.inicializar_carrito(numero_cliente)
                menu_texto = mostrar_menu()
                nombre_usuario = GestorUsuarios.obtener_nombre_usuario(numero_cliente)
                enviar_mensaje_whatsapp(
                    f"¡Hola {nombre_usuario}! 👋 Bienvenido de nuevo. {menu_texto}                ⬆️ *MENU* ⬆️ \n❗*Para agregar un producto*❗\n\nescribe el *numero* o su *nombre* \n\n      👇 *Ejemplos* 👇 \n\n ▪️ *clasica*    o    *301* \n ▪️ *helado*    o    *503* ", 
                    numero_cliente
                )
                return "Mensaje enviado", 200

class Usuario:
    def __init__(self, nombre, numero_cliente, direccion):
        self.nombre = nombre
        self.numero_cliente = numero_cliente
        self.direccion = direccion

    @classmethod
    def desde_diccionario(cls, datos):
        """
        Crea una instancia de Usuario a partir de un diccionario.
        """
        return cls(
            nombre=datos["nombre"],
            numero_cliente=datos["numero"],
            direccion=datos["direccion"]
        )

    def to_dict(self):
        """
        Convierte la instancia de Usuario a un diccionario.
        """
        return {
            "nombre": self.nombre,
            "numero_cliente": self.numero_cliente,
            "direccion": self.direccion
        }


# Alias de funciones globales para evitar que el código actual se rompa
obtener_usuario_bd = GestorUsuariosBD.obtener_usuario
guardar_usuario_bd = GestorUsuariosBD.guardar_usuario
verificar_usuario_bd = GestorUsuariosBD.verificar_usuario
registrar_usuario = GestorUsuarios.registrar_usuario
manejar_usuario = GestorUsuarios.manejar_usuario
obtener_nombre_usuario = GestorUsuarios.obtener_nombre_usuario
