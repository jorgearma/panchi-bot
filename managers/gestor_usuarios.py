import pyodbc
from database import   db_session
from menu import mostrar_menu
from utils.mensajes import enviar_mensaje_whatsapp
from data.estado_usuarios import estado_usuarios
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError
from models import Usuario 

Base = declarative_base()

class GestorUsuariosBD:
    def __init__(self):
        self.session = db_session
       

    def obtener_usuario(self, numero_cliente):
        """Recupera un usuario dando su número de cliente."""
        try:
            usuario = self.session.query(Usuario).filter_by(numero_cliente=numero_cliente).first()
            if usuario:
                return {
                    "nombre": usuario.nombre,
                    "numero": usuario.numero_cliente,
                    "direccion": usuario.direccion
                }
            return None
        except SQLAlchemyError as e:
            print("Error al obtener el usuario:", e)
            return None

    def guardar_usuario(self, numero_cliente, nombre, direccion):
        """Guarda un nuevo usuario en la base de datos."""
        try:
            nuevo_usuario = Usuario(numero_cliente=numero_cliente, nombre=nombre, direccion=direccion)  # Crear una instancia del modelo
            self.session.add(nuevo_usuario)
            self.session.commit()
            print(f"Usuario {nombre} guardado en la base de datos.")
        except SQLAlchemyError as e:
            self.session.rollback()
            print("Error al guardar el usuario en la base de datos:", e)

    def obtener_usuario_completo(self, numero_cliente):
        """Recupera un usuario completo, incluyendo su id, dado su número de cliente."""
        try:
            usuario = self.session.query(Usuario).filter_by(numero_cliente=numero_cliente).first()
            if usuario:
                return {
                    "id": usuario.id,
                    "nombre": usuario.nombre,
                    "numero": usuario.numero_cliente,
                    "direccion": usuario.direccion
                }
            return None
        except SQLAlchemyError as e:
            print("Error al obtener el usuario:", e)
            return None
    
    def verificar_usuario(self, numero_cliente):
        """Verifica si existe un usuario con el número de cliente dado."""
        try:
            count = self.session.query(Usuario).filter_by(numero_cliente=numero_cliente).count()
            return count > 0
        except SQLAlchemyError as e:
            print("Error al verificar el usuario:", e)
            return False
        
def ejecutar_con_reintentos(funcion, max_reintentos, *args, **kwargs):
    """
    Ejecuta una función con lógica de reintentos en caso de que ocurra un SQLAlchemyError.

    Args:
        funcion (callable): La función a ejecutar.
        max_reintentos (int): Número máximo de reintentos permitidos.
        *args: Argumentos posicionales para la función.
        **kwargs: Argumentos nombrados para la función.

    Returns:
        cualquier: El resultado de la función si tiene éxito.

    Raises:
        SQLAlchemyError: Si se alcanzan los reintentos máximos y persiste el error.
    """
    intentos = 0
    while intentos < max_reintentos:
        try:
            return funcion(*args, **kwargs)
        except SQLAlchemyError as e:
            intentos += 1
            print(f"Error en la base de datos: {e}")
            if intentos < max_reintentos:
                print(f"Reintentando... ({intentos}/{max_reintentos})")
            else:
                print("Se alcanzó el número máximo de reintentos. Abortando flujo.")
                raise e

class GestorUsuarios:

    @staticmethod
    def manejar_usuario(numero_cliente , usuario_datos):
        """
        Maneja la interacción con un usuario basado en su número de cliente.
        si no hay un pedido iniciado, se le envía el menú y se inicia un nuevo pedido.

        Este método realiza las siguientes acciones:
        1. Intenta obtener los datos del usuario desde la base de datos, con un máximo de reintentos.
        2. Verifica si el usuario está recién registrado y maneja ese caso.
        3. Si el usuario no tiene un pedido pendiente, inicia un nuevo pedido y envía el menú.

        Args:
            numero_cliente (str): El número de cliente del usuario.

        Returns:
            tuple: Una tupla que contiene un mensaje de estado (str) y un código HTTP (int).
                   - En caso de error en la base de datos, devuelve un mensaje de error y el código 500.
                   - Si el usuario está recién registrado, devuelve un mensaje de confirmación y el código 200.
                   - Si se envía el menú correctamente, devuelve un mensaje de éxito y el código 200.

        Raises:
            SQLAlchemyError: Si ocurre un error al interactuar con la base de datos.
        """
        from main import gestor_pedidos


        id_usuario = usuario_datos["id"]
        direccion_usuario = usuario_datos["direccion"]
        nombre_usuario = usuario_datos["nombre"]

        # 1. Intentar obtener los datos críticos desde la base de datos
        hay_pedido = False
        try:
            if gestor_pedidos.hay_pedido_pendiente(id_usuario):
                hay_pedido = True
        except SQLAlchemyError as e:
            print(f"Error al verificar el pedido pendiente: {e}")
            return "Error en la base de datos. Intente más tarde.", 500
        except Exception as e:
            print(f"Error inesperado: {e}")
            return "Error inesperado. Intente más tarde.", 500

        # 2. Verificamos si es un usuario recién registrado
        if estado_usuarios.get(numero_cliente, {}).get("recien_registrado"):
            del estado_usuarios[numero_cliente]["recien_registrado"]
            return "Usuario registrado, esperando siguiente mensaje.", 200

        # 3. Si no tiene un pedido pendiente, lo iniciamos y enviamos el menú
        if not hay_pedido:
            gestor_pedidos.iniciar_pedido(id_usuario, direccion_usuario, nombre_usuario)
            menu_texto = mostrar_menu()

            enviar_mensaje_whatsapp(
                f"¡Hola *{nombre_usuario}*! 🙂 {menu_texto} \nescribe el *numero* para elegir ",
                numero_cliente
            )

        return "Mensaje enviado", 200
