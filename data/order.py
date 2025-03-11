from sqlalchemy import create_engine, Column, Integer, String, DateTime, DECIMAL, ForeignKey 
from sqlalchemy.orm import sessionmaker, declarative_base , relationship 
from datetime import datetime
from decimal import Decimal


from models import Pedido , PedidoDetalle , Producto








class GestorPedidos:
    
    def __init__(self,session):
        self.session = session


    def iniciar_pedido(self, id, direccion, telefono):
        nuevo_pedido = Pedido(ClienteID=id, DireccionEntrega=direccion, TelefonoEntrega=telefono)
        self.session.add(nuevo_pedido)
        self.session.commit()
        return nuevo_pedido.PedidoID
    
    def actualizar_pedido(self, cliente_id):
        # Busca el pedido pendiente más reciente para el cliente
        pedido1 = self.session.query(Pedido).filter_by(ClienteID=cliente_id, Estado='pendiente').first()
        print(pedido1)
        
        if pedido1:
            pedido1.Estado = 'Abandonado'
            self.session.commit()
            print(f"El pedido {pedido1.PedidoID} se actualizó a 'Abandonado'.")
        else:
            print("No se encontró un pedido pendiente para actualizar.")


    
    def hay_pedido_pendiente(self, cliente_id):
        """
        Verifica si existe un pedido pendiente para el cliente indicado.
        Se asume que el modelo Pedido tiene un atributo 'Estado' donde 'pendiente' indica que aún no se ha procesado.
        """
        pedido = self.session.query(Pedido).filter_by(ClienteID=cliente_id, Estado='Pendiente').first()
        return pedido is not None
    
    def hay_pedido_enlace(self, cliente_id):
        """
        Verifica si existe un pedido pendiente para el cliente indicado.
        Se asume que el modelo Pedido tiene un atributo 'Estado' donde 'pendiente' indica que aún no se ha procesado.
        """
        pedido = self.session.query(Pedido).filter_by(ClienteID=cliente_id, Estado='enlace').first()
        return pedido is not None
    
    def hay_pedido_confirmando_pago(self, cliente_id):
        """
        Verifica si existe un pedido pendiente para el cliente indicado.
        Se asume que el modelo Pedido tiene un atributo 'Estado' donde 'pendiente' indica que aún no se ha procesado.
        """
        pedido = self.session.query(Pedido).filter_by(ClienteID=cliente_id, Estado='confirmando-pago').first()
        return pedido is not None
    
    def obtener_pedido_mas_reciente(self, id_usuario):
        pedido = (
            self.session.query(Pedido)
            .filter(Pedido.ClienteID == id_usuario)
            .order_by(Pedido.FechaCreacion.desc())
            .first()
        )
        return pedido


    
    def agregar_productos_a_pedido(self, pedido_id, productos):
        """
        Agrega múltiples productos a un pedido en una sola transacción.
        
        :param pedido_id: ID del pedido al que se agregarán los productos.
        :param productos: Lista de tuplas con (producto_id, cantidad).
        :return: True si la operación fue exitosa, False en caso contrario.
        """
        pedido = self.session.query(Pedido).filter_by(PedidoID=pedido_id).first()
        if not pedido:
            return False  # El pedido no existe

        total_agregado = Decimal("0.0")
        detalles = []

        for producto_id, cantidad in productos:
            producto = self.session.query(Producto).filter_by(ProductoID=producto_id).first()
            if producto:
                subtotal = Decimal(str(producto.Precio)) * cantidad
                detalle = PedidoDetalle(PedidoID=pedido_id, ProductoID=producto_id, Cantidad=cantidad, Subtotal=subtotal)
                detalles.append(detalle)
                total_agregado += subtotal

        if detalles:
            self.session.add_all(detalles)  # Agregar todos los productos a la base de datos
            pedido.Total += total_agregado  # Actualizar el total del pedido
            self.session.commit()  # Guardar todos los cambios en la base de datos
            return True

        return False  # No se agregaron productos válidos

    
    def actualizar_estado(self, pedido_id, nuevo_estado):
        pedido = self.session.query(Pedido).filter_by(PedidoID=pedido_id).first()
        if pedido:
            pedido.Estado = nuevo_estado
            self.session.commit()
            return True
        return False

    def obtener_pedido(self, pedido_id):
        return self.session.query(Pedido).filter_by(PedidoID=pedido_id).first()

    def listar_pedidos(self):
        return self.session.query(Pedido).all()

    def agregar_producto(self, nombre, precio):
        nuevo_producto = Producto(Nombre=nombre, Precio=precio)
        self.session.add(nuevo_producto)
        self.session.commit()
        return nuevo_producto.ProductoID


    def cargar_productos(self):
        menu = {
            "🍔 HAMBURGUESAS": {
                "clasica": {"precio": 5.00},
                "ranchera": {"precio": 5.50},
                "crispy": {"precio": 6.00}
            },
            "🌭 PERRITOS": {
                "clasico": {"precio": 4.00},
                "picanton": {"precio": 4.00},
                "texano": {"precio": 4.00},
                "bbq": {"precio": 4.00}
            },
            "🍨 POSTRES": {
                "flan": {"precio": 4.00},
                "tarta": {"precio": 5.00},
                "helado": {"precio": 3.50}
            },
            "🥤 BEBIDAS": {
                "agua": {"precio": 1.50},
                "vino": {"precio": 4.00},
                "cerveza": {"precio": 3.00},
                "refresco": {"precio": 2.50},
                "café": {"precio": 2.00}
            }
        }
        for categoria, productos in menu.items():
            for nombre, datos in productos.items():
                self.agregar_producto(nombre.capitalize(), datos["precio"])



    
