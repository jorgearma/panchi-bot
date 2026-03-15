from decimal import Decimal
from models import Pedido , PedidoDetalle , Producto
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type
from sqlalchemy.exc import SQLAlchemyError , OperationalError
from states import EstadoPedido

class GestorPedidos:

    @property
    def session(self):
        from database import get_db
        return get_db()


    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1), retry=retry_if_exception_type((SQLAlchemyError, OperationalError)))
    def iniciar_pedido(self, id, direccion, telefono):
        try:
            nuevo_pedido = Pedido(ClienteID=id, DireccionEntrega=direccion, TelefonoEntrega=telefono)
            self.session.add(nuevo_pedido)
            self.session.commit()
            return nuevo_pedido.PedidoID
        except (SQLAlchemyError, OperationalError) as error:
            self.session.rollback()  # Revertir cambios en caso de error
            print(f"Error al iniciar el pedido: {error}")
            raise
    


    def guardar_enlace(self, pedido_id, enlace):
    # Busca el pedido por su ID
        pedido = self.session.query(Pedido).filter_by(PedidoID=pedido_id).first()
        if pedido:
            # Actualiza el campo Enlace del pedido
            pedido.enlace = enlace
            self.session.commit()
            print(f"El enlace ha sido guardado en el pedido {pedido_id}.")
            return True
        else:
            print("No se encontró un pedido con el ID proporcionado.")
            return False
            


    
    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1), retry=retry_if_exception_type(SQLAlchemyError))
    def hay_pedido_pendiente(self, cliente_id):
        """
        Verifica si existe un pedido pendiente para el cliente indicado.
        Se asume que el modelo Pedido tiene un atributo 'Estado' donde 'Pendiente' indica que aún no se ha procesado.
        """
        try:
            pedido = self.session.query(Pedido).filter_by(ClienteID=cliente_id, Estado=EstadoPedido.PENDIENTE).first()
            return pedido is not None
        except SQLAlchemyError as error:
            print(f"Error al verificar pedido pendiente para el cliente {cliente_id}: {error}")
            raise
    

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1), retry=retry_if_exception_type(SQLAlchemyError))
    def obtener_pedido_mas_reciente(self, id_usuario):
        """
        Devuelve el pedido más reciente (activo) del usuario.
        """
        try:
            pedido = (
                self.session.query(Pedido)
                .filter(Pedido.ClienteID == id_usuario)
                .filter(Pedido.Estado != EstadoPedido.PAGADO)
                .order_by(Pedido.FechaCreacion.desc())
                .first()
            )
            return pedido  # Devuelve None si no hay pedidos
        except SQLAlchemyError as error:
            print(f"Error al obtener el pedido activo del usuario {id_usuario}: {error}")
            raise  # O manejar el caso donde no se encuentra un pedido

    
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

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1), retry=retry_if_exception_type(SQLAlchemyError))
    def actualizar_estado(self, pedido_id, nuevo_estado):
        try:
            pedido = self.session.query(Pedido).filter_by(PedidoID=pedido_id).first()
            if pedido:
                pedido.Estado = nuevo_estado
                self.session.commit()
                return True
            else:
                print(f"Pedido con ID {pedido_id} no encontrado.")
                return False
        except SQLAlchemyError as error:
            self.session.rollback()
            print(f"Error al actualizar el estado del pedido {pedido_id}: {error}")
            raise 
    
    def introudcir_dato_redisID(self, pedido_id, id_redis):
        pedido = self.session.query(Pedido).filter_by(PedidoID=pedido_id).first()
        if pedido:
            pedido.redisID = id_redis
            self.session.commit()
            return True
        return False

    def obtener_pedido(self, pedido_id):
        try:
            pedido = self.session.query(Pedido).filter_by(PedidoID=pedido_id).first()
            if not pedido:
                print(f"No se encontró un pedido con el ID {pedido_id}.")
            return pedido
        except SQLAlchemyError as error:
            print(f"Error al recuperar el pedido con ID {pedido_id}: {error}")
            raise


    def agregar_producto(self, nombre, precio):
        nuevo_producto = Producto(Nombre=nombre, Precio=precio)
        self.session.add(nuevo_producto)
        self.session.commit()
        return nuevo_producto.ProductoID




    
