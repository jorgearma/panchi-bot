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

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
        retry=retry_if_exception_type((SQLAlchemyError, OperationalError)),
    )
    def iniciar_enlace(self, pedido_id: int, enlace: str) -> bool:
        """Atomic: transition to ENLACE + save link in one commit.

        Reemplaza la secuencia actualizar_estado(ENLACE) + guardar_enlace que
        era vulnerable a dejar el pedido en ENLACE sin enlace si el segundo
        commit fallaba.
        """
        try:
            pedido = self.session.query(Pedido).filter_by(PedidoID=pedido_id).first()
            if not pedido:
                logger.warning("iniciar_enlace: pedido %s no encontrado", pedido_id)
                return False
            pedido.enlace = enlace
            if not self._set_estado(pedido, EstadoPedido.ENLACE):
                return False
            self.session.commit()
            logger.info("ENLACE_INICIADO pedido_id=%s", pedido_id)
            return True
        except (SQLAlchemyError, OperationalError) as error:
            self.session.rollback()
            logger.error("Error al iniciar enlace pedido %s: %s", pedido_id, error)
            raise

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
        :param productos: List of dicts {producto_id, cantidad, notas} — each dict
                          is a separate line item. The same producto_id may appear
                          multiple times with different notas (e.g. pizza sin cebolla
                          and pizza con todo).
        :return: True if lines were staged, False if no valid products were found.
        """
        self.session.query(PedidoDetalle).filter_by(PedidoID=pedido.PedidoID).delete()
        pedido.Total = self._to_decimal("0.0")

        total = self._to_decimal("0.0")
        detalles = []

        for item in productos:
            producto_id = item["producto_id"]
            cantidad    = item["cantidad"]
            notas       = item.get("notas") or None

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
                    Notas=notas,
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

    def obtener_seguimiento(self, redis_id: str) -> dict | None:
        """Proyección pública del estado del pedido para la página de tracking."""
        pedido = self.session.query(Pedido).filter_by(redisID=redis_id).first()
        if not pedido:
            return None

        reparto_data = None
        if pedido.reparto:
            r = pedido.reparto
            repartidor_nombre = None
            repartidor_telefono = None
            if r.repartidor:
                repartidor_nombre = f"{r.repartidor.Nombre} {r.repartidor.Apellido}"
                repartidor_telefono = r.repartidor.Telefono
            reparto_data = {
                "estado": r.estado,
                "hora_salida": r.hora_salida.strftime("%H:%M") if r.hora_salida else None,
                "hora_estimada_entrega": r.hora_estimada_entrega.strftime("%H:%M") if r.hora_estimada_entrega else None,
                "repartidor_nombre": repartidor_nombre,
                "repartidor_telefono": repartidor_telefono,
                "calle_destino": pedido.DireccionEntrega,
            }

        return {
            "estado": pedido.Estado,
            "forma_pago": pedido.forma_pago,
            "reparto": reparto_data,
        }

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
