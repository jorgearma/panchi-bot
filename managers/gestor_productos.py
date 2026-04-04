import logging
from decimal import Decimal
from sqlalchemy.exc import SQLAlchemyError
from models import Producto, Categoria

logger = logging.getLogger(__name__)


class ProductoManager:

    @property
    def session(self):
        """Devuelve la sesión activa de base de datos."""
        from database import get_db
        return get_db()
    
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
                    "IngredientesRemovibles": producto.IngredientesRemovibles,
                    "Imagen": producto.ImagenURL,
                    "Codigo": producto.ProductoID
                })
            
            return lista_productos
        except SQLAlchemyError as e:
            logger.error("Error al obtener los productos: %s", e)
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
                    "Imagen": producto.ImagenURL,
                    "Codigo": producto.ProductoID
                }
            else:
                return None
        except SQLAlchemyError as e:
            logger.error("Error al obtener el producto por código: %s", e)
            return None

    def productos_admin(self) -> list:
        """Full product list for the admin panel, including stock and availability."""
        try:
            productos = (
                self.session.query(Producto)
                .order_by(Producto.Categoria, Producto.Nombre)
                .all()
            )
            return [
                {
                    "id": p.ProductoID,
                    "nombre": p.Nombre,
                    "categoria": p.Categoria,
                    "precio": float(p.Precio),
                    "stock": p.Stock,
                    "disponible": p.Disponible,
                    "ubicacion": p.Ubicacion,
                    "descripcion": p.Descripcion,
                    "imagen": p.ImagenURL,
                    "descuento": float(p.Descuento) if p.Descuento else 0.0,
                }
                for p in productos
            ]
        except SQLAlchemyError as e:
            logger.error("Error en productos_admin: %s", e)
            return []

    def actualizar_stock(self, producto_id: int, nuevo_stock: int) -> tuple:
        """Sets stock to an absolute value. Marks unavailable if stock reaches 0."""
        if nuevo_stock < 0:
            return False, "El stock no puede ser negativo"
        s = self.session
        try:
            p = s.query(Producto).filter_by(ProductoID=producto_id).first()
            if not p:
                return False, "Producto no encontrado"
            p.Stock = nuevo_stock
            if nuevo_stock == 0:
                p.Disponible = False
            elif not p.Disponible:
                p.Disponible = True
            s.commit()
            return True, nuevo_stock
        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error actualizando stock producto %s: %s", producto_id, e)
            return False, "Error de base de datos"

    def ajustar_stock(self, producto_id: int, delta: int) -> tuple:
        """Increments or decrements stock by delta. Returns (ok, nuevo_stock)."""
        s = self.session
        try:
            p = s.query(Producto).filter_by(ProductoID=producto_id).first()
            if not p:
                return False, "Producto no encontrado"
            nuevo = max(0, p.Stock + delta)
            p.Stock = nuevo
            if nuevo == 0:
                p.Disponible = False
            elif delta > 0 and not p.Disponible:
                p.Disponible = True
            s.commit()
            return True, nuevo
        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error ajustando stock producto %s: %s", producto_id, e)
            return False, "Error de base de datos"

    def toggle_disponible(self, producto_id: int, disponible: bool) -> tuple:
        """Activa o desactiva un producto en catalogo."""
        s = self.session
        try:
            p = s.query(Producto).filter_by(ProductoID=producto_id).first()
            if not p:
                return False, "Producto no encontrado"
            p.Disponible = disponible
            s.commit()
            return True, disponible
        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error toggling disponible producto %s: %s", producto_id, e)
            return False, "Error de base de datos"

    def actualizar_precio(self, producto_id: int, nuevo_precio: float) -> tuple:
        """Actualiza el precio de venta del producto."""
        if nuevo_precio <= 0:
            return False, "El precio debe ser mayor que 0"
        s = self.session
        try:
            p = s.query(Producto).filter_by(ProductoID=producto_id).first()
            if not p:
                return False, "Producto no encontrado"
            p.Precio = Decimal(str(nuevo_precio))
            s.commit()
            return True, float(p.Precio)
        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error actualizando precio producto %s: %s", producto_id, e)
            return False, "Error de base de datos"

    def descontar_stock_picking(self, items_picking: list) -> None:
        """Called after picking is completed. Decrements stock for each picked item.
        items_picking: list of dicts {producto_id, cantidad_encontrada, estado}
        """
        s = self.session
        try:
            for item in items_picking:
                p = s.query(Producto).filter_by(ProductoID=item["producto_id"]).first()
                if not p:
                    continue
                if item["estado"] == "encontrado":
                    cantidad = item["cantidad_encontrada"] or item["cantidad_pedida"]
                    p.Stock = max(0, p.Stock - cantidad)
                    if p.Stock == 0:
                        p.Disponible = False
                elif item["estado"] == "sin_stock":
                    p.Stock = 0
                    p.Disponible = False
            s.commit()
        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error descontando stock en picking: %s", e)
