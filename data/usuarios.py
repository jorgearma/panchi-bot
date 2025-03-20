import pyodbc
from database import   db_session
from menu import mostrar_menu
from utils.mensajes import enviar_mensaje_whatsapp
from data.estado_usuarios import estado_usuarios

from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError

from models import Usuario , Producto


Base = declarative_base()


class ProductoManager:
    def __init__(self):
        self.session = db_session
    
    def obtener_productos(self):
        """Recupera todos los productos de la base de datos."""
        try:
            productos = self.session.query(Producto).all()
            
            lista_productos = []
            for producto in productos:
                lista_productos.append({
                    "Nombre": producto.Nombre,
                    "Precio": producto.Precio,
                    "Categoria": producto.Categoria,
                    "Ingredientes": producto.Ingredientes,
                    "Imagen": producto.ImagenURL,
                    "Codigo": producto.ProductoID  # Ruta de la imagen en el servidor
                })
            
            return lista_productos
        except SQLAlchemyError as e:
            print("Error al obtener los productos:", e)
            return None
        
        
    def obtener_producto_por_codigo(self, codigo):
        """Recupera un producto de la base de datos según su código."""
        try:
            producto = self.session.query(Producto).filter(Producto.ProductoID == codigo).first()
            if producto:
                return {
                    "Nombre": producto.Nombre,
                    "Precio": producto.Precio,
                    "Categoria": producto.Categoria,
                    "Ingredientes": producto.Ingredientes,
                    "Imagen": producto.ImagenURL,  # Ruta de la imagen en el servidor
                    "Codigo": producto.ProductoID
                }
            else:
                return None
        except SQLAlchemyError as e:
            print("Error al obtener el producto por código:", e)
            return None    
        
class GestorUsuariosBD:
    def __init__(self):
        self.session = db_session
       

    def obtener_usuario(self, numero_cliente):
        """Recupera un usuario dado su número de cliente."""
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
        
        from main import gestor_usuarios
        from main import gestor_pedidos
        
        # Verifica si el usuario está recién registrado
        if estado_usuarios.get(numero_cliente, {}).get("recien_registrado"):
            del estado_usuarios[numero_cliente]["recien_registrado"]
        else:
            # Inicializa el carrito si el cliente no lo tiene
            datos_usuario = gestor_usuarios.obtener_usuario_completo(numero_cliente)
            id_usuario = datos_usuario["id"]
            direccion_usuario = datos_usuario["direccion"]
            numero_usuario = datos_usuario["nombre"]

            
            
            if not gestor_pedidos.hay_pedido_pendiente(id_usuario):
                gestor_pedidos.iniciar_pedido(id_usuario,direccion_usuario, numero_usuario)
                menu_texto = mostrar_menu()
                nombre_usuario = datos_usuario["nombre"]
                
                enviar_mensaje_whatsapp(
                    f"¡Hola *{nombre_usuario}*! 🙂 {menu_texto} \nescribe el *numero* para elegir ", 
                    numero_cliente
                )
   
                return "Mensaje enviado", 200


class Usuario_web:
    def __init__(self, datos):
        """
        Inicializa una instancia de Usuario usando un diccionario con los datos.
        Se esperan las claves 'nombre', 'numero' y 'direccion'.
        """
        self.id = datos.get("id", "")
        self.nombre = datos.get("nombre", "")
        self.numero = datos.get("numero", "")
        self.direccion = datos.get("direccion", "")
        self.token = datos.get("token", "")

    def __repr__(self):
        return f"<Usuario: {self.nombre}>"

    def to_dict(self):
        """Devuelve un diccionario con los datos del usuario."""
        return {
            "nombre": self.nombre,
            "numero": self.numero,
            "direccion": self.direccion
        }


# Alias de funciones globales para evitar que el código actual se rompa
obtener_usuario_bd = GestorUsuariosBD.obtener_usuario
guardar_usuario_bd = GestorUsuariosBD.guardar_usuario
verificar_usuario_bd = GestorUsuariosBD.verificar_usuario
registrar_usuario = GestorUsuarios.registrar_usuario
manejar_usuario = GestorUsuarios.manejar_usuario
obtener_nombre_usuario = GestorUsuarios.obtener_nombre_usuario



