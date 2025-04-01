import pyodbc
from database import   db_session
from menu import mostrar_menu
from utils.mensajes import enviar_mensaje_whatsapp
from data.estado_usuarios import estado_usuarios
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError
from models import Usuario 

from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type
from sqlalchemy.exc import SQLAlchemyError , OperationalError
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

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1), retry=retry_if_exception_type(SQLAlchemyError))
    def obtener_usuario_completo(self, numero_cliente):
        """Recupera un usuario completo, incluyendo su id, dado su número de cliente."""
        usuario = self.session.query(Usuario).filter_by(numero_cliente=numero_cliente).first()
        if usuario:
            return {
                "id": usuario.id,
                "nombre": usuario.nombre,
                "numero": usuario.numero_cliente,
                "direccion": usuario.direccion
            }
        return None
    
    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1), retry=retry_if_exception_type(SQLAlchemyError))
    def verificar_usuario(self, numero_cliente):

        try:
            usuario = self.session.query(Usuario).filter_by(numero_cliente=numero_cliente).scalar()
            # Si no se encontró usuario, se retorna None
            return usuario  
        except OperationalError as op_err:
            # Error de conexión (o similar)
            print("Error de conexión al verificar el usuario:", op_err)
            # Se relanza la excepción para que el decorador realice los reintentos
            raise
        except SQLAlchemyError as e:
            print("Error al verificar el usuario:", e)
            raise
        


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
        

        # 2. Verificamos si es un usuario recién registrado
        if estado_usuarios.get(numero_cliente, {}).get("recien_registrado"):
            del estado_usuarios[numero_cliente]["recien_registrado"]
            return "Usuario registrado, esperando siguiente mensaje.", 200

        # 3. Si no tiene un pedido pendiente, lo iniciamos y enviamos el menú
        
        try:
            gestor_pedidos.iniciar_pedido(id_usuario, direccion_usuario, nombre_usuario)
            
        except (SQLAlchemyError, OperationalError) as error:
            # Captura los errores después de que el decorador haya agotado los intentos
            print(f"Error al iniciar el pedido para el usuario {id_usuario}: {error}")
            return "Error al procesar el pedido. Inténtalo más tarde.", 500
        
        menu_texto = mostrar_menu()

        enviar_mensaje_whatsapp(
                f"¡Hola *{nombre_usuario}*! 🙂 {menu_texto} \nescribe el *numero* para elegir ",
                numero_cliente
            )

        return "Mensaje enviado", 200
