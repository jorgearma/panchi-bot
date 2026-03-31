import logging

from models import Pedido, PedidoDetalle, Producto
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from states import ESTADOS_TERMINALES_PEDIDO, EstadoPedido
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

logger = logging.getLogger(__name__)


class GestorPedidosLifecycleMixin:
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
        retry=retry_if_exception_type((SQLAlchemyError, OperationalError)),
    )
    def iniciar_pedido(self, id, direccion, telefono):
        """Crea un pedido base para iniciar el flujo."""
        try:
            nuevo_pedido = Pedido(
                ClienteID=id,
                DireccionEntrega=direccion,
                TelefonoEntrega=telefono,
            )
            self.session.add(nuevo_pedido)
            self.session.commit()
            return nuevo_pedido.PedidoID
        except (SQLAlchemyError, OperationalError) as error:
            self.session.rollback()
            logger.error("Error al iniciar el pedido: %s", error)
            raise

    def guardar_enlace(self, pedido_id, enlace):
        """Guarda el enlace asociado a un pedido."""
        pedido = self.session.query(Pedido).filter_by(PedidoID=pedido_id).first()
        if pedido:
            pedido.enlace = enlace
            self.session.commit()
            logger.info("Enlace guardado en pedido %s", pedido_id)
            return True
        logger.warning("No se encontró un pedido con el ID proporcionado.")
        return False

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
        retry=retry_if_exception_type(SQLAlchemyError),
    )
    def hay_pedido_pendiente(self, cliente_id):
        """
        Verifica si existe un pedido pendiente para el cliente indicado.
        Se asume que el modelo Pedido tiene un atributo 'Estado' donde 'Pendiente'
        indica que aún no se ha procesado.
        """
        try:
            pedido = self.session.query(Pedido).filter_by(
                ClienteID=cliente_id,
                Estado=EstadoPedido.PENDIENTE,
            ).first()
            return pedido is not None
        except SQLAlchemyError as error:
            logger.error(
                "Error al verificar pedido pendiente para el cliente %s: %s",
                cliente_id,
                error,
            )
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
        retry=retry_if_exception_type(SQLAlchemyError),
    )
    def obtener_pedido_mas_reciente(self, id_usuario):
        """
        Devuelve el pedido más reciente no terminal del usuario.
        Excluye estados terminales: entregado, cancelado, reembolsado.
        """
        try:
            estados_excluidos = [e.value for e in ESTADOS_TERMINALES_PEDIDO]
            pedido = (
                self.session.query(Pedido)
                .filter(Pedido.ClienteID == id_usuario)
                .filter(Pedido.Estado.notin_(estados_excluidos))
                .order_by(Pedido.FechaCreacion.desc())
                .first()
            )
            return pedido
        except SQLAlchemyError as error:
            logger.error(
                "Error al obtener el pedido activo del usuario %s: %s",
                id_usuario,
                error,
            )
            raise

    def _reemplazar_detalles(self, pedido, productos) -> bool:
        """
        Stages the replacement of order lines without committing.

        Deletes any existing PedidoDetalle for the order (idempotency) and
        inserts the new ones. The caller is responsible for committing.

        :param pedido: Pedido ORM instance.
        :param productos: List of (product_id, quantity) tuples.
        :return: True if lines were staged, False if no valid products were found.
        """
        self.session.query(PedidoDetalle).filter_by(PedidoID=pedido.PedidoID).delete()
        pedido.Total = self._to_decimal("0.0")

        total = self._to_decimal("0.0")
        detalles = []

        for producto_id, cantidad in productos:
            producto = self.session.query(Producto).filter_by(
                ProductoID=producto_id,
            ).first()
            if producto:
                precio_unitario = self._to_decimal(producto.Precio)
                subtotal = precio_unitario * cantidad
                detalles.append(PedidoDetalle(
                    PedidoID=pedido.PedidoID,
                    ProductoID=producto_id,
                    Cantidad=cantidad,
                    PrecioUnitario=precio_unitario,
                    NombreProducto=producto.Nombre,
                    Subtotal=subtotal,
                ))
                total += subtotal

        if not detalles:
            return False

        self.session.add_all(detalles)
        pedido.Total = total
        return True

    def agregar_productos_a_pedido(self, pedido_id, productos):
        """
        Idempotent: replaces order lines and commits. Existing lines are deleted
        first so retries never produce duplicates.

        :param pedido_id: ID del pedido al que se agregarán los productos.
        :param productos: Lista de tuplas con (producto_id, cantidad).
        :return: True si la operación fue exitosa, False en caso contrario.
        """
        pedido = self.session.query(Pedido).filter_by(PedidoID=pedido_id).first()
        if not pedido:
            return False

        if not self._reemplazar_detalles(pedido, productos):
            return False

        try:
            self.session.commit()
            return True
        except (SQLAlchemyError, OperationalError) as error:
            self.session.rollback()
            logger.error(
                "Error al agregar productos al pedido %s: %s",
                pedido_id,
                error,
            )
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
        retry=retry_if_exception_type((SQLAlchemyError, OperationalError)),
    )
    def confirmar_pago_online(
        self, pedido_id, productos, redirect_url, notas=None
    ) -> bool:
        """
        Atomic: replace order lines + transition to CONFIRMANDO_PAGO + save URL.

        Must be called AFTER the Monei payment has been created successfully so
        that a DB failure does not leave a committed payment without a matching
        order state.
        """
        try:
            pedido = self.session.query(Pedido).filter_by(PedidoID=pedido_id).first()
            if not pedido:
                logger.warning("confirmar_pago_online: pedido %s no encontrado", pedido_id)
                return False
            if not self._reemplazar_detalles(pedido, productos):
                logger.error("confirmar_pago_online: no se encontraron productos válidos")
                return False
            if notas:
                pedido.Notas = notas
            pedido.enlace = redirect_url
            if not self._set_estado(pedido, EstadoPedido.CONFIRMANDO_PAGO):
                return False
            self.session.commit()
            return True
        except (SQLAlchemyError, OperationalError) as error:
            self.session.rollback()
            logger.error(
                "Error al confirmar pago online del pedido %s: %s",
                pedido_id,
                error,
            )
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
        retry=retry_if_exception_type((SQLAlchemyError, OperationalError)),
    )
    def confirmar_pago_efectivo(
        self, pedido_id, productos, notas=None
    ) -> bool:
        """
        Atomic: replace order lines + set forma_pago + transition to
        CONTRA_REEMBOLSO in one commit.
        """
        try:
            pedido = self.session.query(Pedido).filter_by(PedidoID=pedido_id).first()
            if not pedido:
                logger.warning("confirmar_pago_efectivo: pedido %s no encontrado", pedido_id)
                return False
            if not self._reemplazar_detalles(pedido, productos):
                logger.error("confirmar_pago_efectivo: no se encontraron productos válidos")
                return False
            if notas:
                pedido.Notas = notas
            pedido.forma_pago = "efectivo"
            if not self._set_estado(pedido, EstadoPedido.CONTRA_REEMBOLSO):
                return False
            self.session.commit()
            return True
        except (SQLAlchemyError, OperationalError) as error:
            self.session.rollback()
            logger.error(
                "Error al confirmar pago efectivo del pedido %s: %s",
                pedido_id,
                error,
            )
            raise

    def obtener_pedido(self, pedido_id):
        """Recupera un pedido por id."""
        try:
            pedido = self.session.query(Pedido).filter_by(PedidoID=pedido_id).first()
            if not pedido:
                logger.warning("No se encontró un pedido con el ID %s.", pedido_id)
            return pedido
        except SQLAlchemyError as error:
            logger.error(
                "Error al recuperar el pedido con ID %s: %s",
                pedido_id,
                error,
            )
            raise
