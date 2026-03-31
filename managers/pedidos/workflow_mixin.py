import logging
from datetime import datetime

from models import HistorialEstadoPedido, Pago, Pedido, PickingItem, PickingPedido
from sqlalchemy.exc import SQLAlchemyError
from states import EstadoPedido, EstadoPicking, transicion_valida_pedido
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

logger = logging.getLogger(__name__)


class GestorPedidosWorkflowMixin:
    def _set_estado(self, pedido, nuevo_estado, notas=None, empleado_id=None) -> bool:
        """Stages a state transition without committing. Returns False if invalid."""
        if not transicion_valida_pedido(pedido.Estado, nuevo_estado):
            logger.error(
                "Transición de pedido inválida: %s → %s (pedido %s)",
                pedido.Estado,
                nuevo_estado,
                pedido.PedidoID,
            )
            return False
        estado_anterior = pedido.Estado
        pedido.Estado = nuevo_estado
        self.session.add(
            HistorialEstadoPedido(
                pedido_id=pedido.PedidoID,
                estado_anterior=estado_anterior,
                estado_nuevo=nuevo_estado,
                notas=notas,
                empleado_id=empleado_id,
            )
        )
        self._asegurar_picking_si_procede(pedido, nuevo_estado)
        return True

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
        retry=retry_if_exception_type(SQLAlchemyError),
    )
    def actualizar_estado(self, pedido_id, nuevo_estado, notas=None, empleado_id=None):
        """Valida y registra un cambio de estado del pedido."""
        try:
            pedido = self.session.query(Pedido).filter_by(PedidoID=pedido_id).first()
            if not pedido:
                logger.warning("Pedido con ID %s no encontrado.", pedido_id)
                return False
            if not self._set_estado(pedido, nuevo_estado, notas, empleado_id):
                return False
            self.session.commit()
            return True
        except SQLAlchemyError as error:
            self.session.rollback()
            logger.error(
                "Error al actualizar el estado del pedido %s: %s",
                pedido_id,
                error,
            )
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
        retry=retry_if_exception_type(SQLAlchemyError),
    )
    def fijar_carrito_confirmado(
        self, pedido_id, redis_id, lat=None, lng=None
    ) -> bool:
        """Atomic: set redisID + coordinates + transition to ENLACE2 in one commit."""
        try:
            pedido = self.session.query(Pedido).filter_by(PedidoID=pedido_id).first()
            if not pedido:
                logger.warning("Pedido con ID %s no encontrado.", pedido_id)
                return False
            pedido.redisID = redis_id
            if lat is not None and lng is not None:
                pedido.lat_entrega = lat
                pedido.lng_entrega = lng
            if not self._set_estado(pedido, EstadoPedido.ENLACE2):
                return False
            self.session.commit()
            return True
        except SQLAlchemyError as error:
            self.session.rollback()
            logger.error(
                "Error al fijar carrito confirmado para pedido %s: %s",
                pedido_id,
                error,
            )
            raise

    def _asegurar_picking_si_procede(self, pedido, nuevo_estado) -> None:
        """Crea un PickingPedido pendiente al entrar en la cola operativa inicial."""
        if nuevo_estado not in {
            EstadoPedido.PAGADO,
            EstadoPedido.CONTRA_REEMBOLSO,
        }:
            return

        picking_existente = (
            self.session.query(PickingPedido)
            .filter_by(pedido_id=pedido.PedidoID)
            .first()
        )
        if picking_existente:
            return

        picking = PickingPedido(
            pedido_id=pedido.PedidoID,
            estado=EstadoPicking.PENDIENTE.value,
        )
        self.session.add(picking)
        self.session.flush()

        for detalle in pedido.detalles:
            self.session.add(
                PickingItem(
                    picking_id=picking.id,
                    pedido_detalle_id=detalle.DetalleID,
                    estado=EstadoPicking.PENDIENTE.value,
                )
            )

    def guardar_forma_pago(self, pedido_id, forma_pago: str):
        """Guarda la forma de pago elegida en el pedido."""
        pedido = self.session.query(Pedido).filter_by(PedidoID=pedido_id).first()
        if pedido:
            pedido.forma_pago = forma_pago
            self.session.commit()
            return True
        return False

    def guardar_coordenadas(self, pedido_id, lat: float, lng: float) -> bool:
        """Guarda las coordenadas de entrega del pedido."""
        pedido = self.session.query(Pedido).filter_by(PedidoID=pedido_id).first()
        if pedido:
            pedido.lat_entrega = lat
            pedido.lng_entrega = lng
            self.session.commit()
            return True
        return False

    def guardar_redis_id(self, pedido_id, id_redis):
        """Asocia el identificador de Redis al pedido."""
        pedido = self.session.query(Pedido).filter_by(PedidoID=pedido_id).first()
        if pedido:
            pedido.redisID = id_redis
            self.session.commit()
            return True
        return False

    def registrar_pago(
        self,
        pedido_id,
        importe_euros,
        referencia_externa=None,
        datos_raw=None,
    ):
        """Inserta un registro de pago completado. Llamar tras confirmar el webhook de Monei."""
        try:
            pago = Pago(
                pedido_id=pedido_id,
                proveedor='monei',
                referencia_externa=referencia_externa,
                estado='completado',
                importe=importe_euros,
                moneda='EUR',
                datos_raw=datos_raw,
            )
            self.session.add(pago)
            self.session.commit()
            logger.info(
                "Pago registrado para pedido %s (ref: %s)",
                pedido_id,
                referencia_externa,
            )
            return True
        except SQLAlchemyError as error:
            self.session.rollback()
            logger.error(
                "Error al registrar pago del pedido %s: %s",
                pedido_id,
                error,
            )
            return False
