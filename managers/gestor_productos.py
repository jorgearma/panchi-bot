import pyodbc
from database import   db_session
from sqlalchemy.orm import  declarative_base
from sqlalchemy.exc import SQLAlchemyError
from models import Producto


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
        
