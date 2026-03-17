import json
import logging
from datetime import datetime
from decimal import Decimal
from models import AuditLog, Pedido, PedidoDetalle, PickingItem, Producto, HistorialEstadoPedido, Pago
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from states import EstadoPedido, ESTADOS_TERMINALES_PEDIDO, transicion_valida_pedido

logger = logging.getLogger(__name__)

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
            logger.error("Error al iniciar el pedido: %s", error)
            raise
    


    def guardar_enlace(self, pedido_id, enlace):
    # Busca el pedido por su ID
        pedido = self.session.query(Pedido).filter_by(PedidoID=pedido_id).first()
        if pedido:
            # Actualiza el campo Enlace del pedido
            pedido.enlace = enlace
            self.session.commit()
            logger.info("Enlace guardado en pedido %s", pedido_id)
            return True
        else:
            logger.warning("No se encontró un pedido con el ID proporcionado.")
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
            logger.error("Error al verificar pedido pendiente para el cliente %s: %s", cliente_id, error)
            raise
    

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1), retry=retry_if_exception_type(SQLAlchemyError))
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
            logger.error("Error al obtener el pedido activo del usuario %s: %s", id_usuario, error)
            raise

    
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
                precio_unitario = Decimal(str(producto.Precio))
                subtotal = precio_unitario * cantidad
                detalle = PedidoDetalle(
                    PedidoID=pedido_id,
                    ProductoID=producto_id,
                    Cantidad=cantidad,
                    PrecioUnitario=precio_unitario,
                    NombreProducto=producto.Nombre,
                    Subtotal=subtotal,
                )
                detalles.append(detalle)
                total_agregado += subtotal

        if not detalles:
            return False

        try:
            self.session.add_all(detalles)
            pedido.Total += total_agregado
            self.session.commit()
            return True
        except (SQLAlchemyError, OperationalError) as error:
            self.session.rollback()
            logger.error("Error al agregar productos al pedido %s: %s", pedido_id, error)
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1), retry=retry_if_exception_type(SQLAlchemyError))
    def actualizar_estado(self, pedido_id, nuevo_estado):
        try:
            pedido = self.session.query(Pedido).filter_by(PedidoID=pedido_id).first()
            if not pedido:
                logger.warning("Pedido con ID %s no encontrado.", pedido_id)
                return False
            if not transicion_valida_pedido(pedido.Estado, nuevo_estado):
                logger.error(
                    "Transición de pedido inválida: %s → %s (pedido %s)",
                    pedido.Estado, nuevo_estado, pedido_id,
                )
                return False
            estado_anterior = pedido.Estado
            pedido.Estado = nuevo_estado
            self.session.add(HistorialEstadoPedido(
                pedido_id=pedido_id,
                estado_anterior=estado_anterior,
                estado_nuevo=nuevo_estado,
            ))
            self.session.commit()
            return True
        except SQLAlchemyError as error:
            self.session.rollback()
            logger.error("Error al actualizar el estado del pedido %s: %s", pedido_id, error)
            raise
    
    def guardar_forma_pago(self, pedido_id, forma_pago: str):
        pedido = self.session.query(Pedido).filter_by(PedidoID=pedido_id).first()
        if pedido:
            pedido.forma_pago = forma_pago
            self.session.commit()
            return True
        return False

    def guardar_coordenadas(self, pedido_id, lat: float, lng: float) -> bool:
        pedido = self.session.query(Pedido).filter_by(PedidoID=pedido_id).first()
        if pedido:
            pedido.lat_entrega = lat
            pedido.lng_entrega = lng
            self.session.commit()
            return True
        return False

    def guardar_redis_id(self, pedido_id, id_redis):
        pedido = self.session.query(Pedido).filter_by(PedidoID=pedido_id).first()
        if pedido:
            pedido.redisID = id_redis
            self.session.commit()
            return True
        return False

    def registrar_pago(self, pedido_id, importe_euros, referencia_externa=None, datos_raw=None):
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
            logger.info("Pago registrado para pedido %s (ref: %s)", pedido_id, referencia_externa)
            return True
        except SQLAlchemyError as error:
            self.session.rollback()
            logger.error("Error al registrar pago del pedido %s: %s", pedido_id, error)
            return False

    # -------------------------------------------------------------------------
    # Cancellation & item modification
    # -------------------------------------------------------------------------

    _MOTIVOS_CANCELACION = {
        'cliente_cancelo', 'falta_stock', 'direccion_incorrecta',
        'cliente_no_responde', 'pedido_duplicado', 'otro',
    }
    _ESTADOS_MODIFICABLES = {
        EstadoPedido.PAGADO.value,
        EstadoPedido.CONTRA_REEMBOLSO.value,
        EstadoPedido.EN_PREPARACION.value,
    }

    @staticmethod
    def _recalcular_total(session, pedido) -> None:
        """Recalculates Pedido.Total from the sum of current PedidoDetalle.Subtotal rows."""
        detalles = session.query(PedidoDetalle).filter_by(PedidoID=pedido.PedidoID).all()
        pedido.Total = sum((d.Subtotal for d in detalles if d.Subtotal), Decimal('0.00'))

    def cancelar_pedido(self, pedido_id: int, motivo: str, empleado_id: int = None) -> tuple:
        """Cancel an order. Returns (ok, msg, telefono_cliente).

        PAGADO orders transition to REEMBOLSADO (payment was taken).
        All other cancellable states transition to CANCELADO.
        """
        if motivo not in self._MOTIVOS_CANCELACION:
            return False, f"Motivo inválido. Válidos: {', '.join(sorted(self._MOTIVOS_CANCELACION))}", None

        s = self.session
        try:
            pedido = s.query(Pedido).filter_by(PedidoID=pedido_id).first()
            if not pedido:
                return False, "Pedido no encontrado", None

            if transicion_valida_pedido(pedido.Estado, EstadoPedido.CANCELADO):
                nuevo_estado = EstadoPedido.CANCELADO
            elif transicion_valida_pedido(pedido.Estado, EstadoPedido.REEMBOLSADO):
                nuevo_estado = EstadoPedido.REEMBOLSADO
            else:
                return False, f"No se puede cancelar un pedido en estado '{pedido.Estado}'", None

            estado_anterior = pedido.Estado
            pedido.Estado = nuevo_estado
            pedido.cancel_reason = motivo
            pedido.cancelled_by = empleado_id
            pedido.cancelled_at = datetime.utcnow()

            s.add(HistorialEstadoPedido(
                pedido_id=pedido_id,
                estado_anterior=estado_anterior,
                estado_nuevo=nuevo_estado,
                notas=f"Cancelado — motivo: {motivo}" + (
                    f" — por empleado #{empleado_id}" if empleado_id else ""
                ),
            ))
            s.add(AuditLog(
                pedido_id=pedido_id,
                empleado_id=empleado_id,
                accion='cancelar_pedido',
                detalles=json.dumps({'motivo': motivo, 'estado_anterior': estado_anterior}),
            ))
            s.commit()
            telefono = pedido.TelefonoEntrega
            return True, f"Pedido #{pedido_id} cancelado ({nuevo_estado.value})", telefono
        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error al cancelar pedido %s: %s", pedido_id, e)
            return False, "Error de base de datos", None

    def eliminar_item(self, pedido_id: int, detalle_id: int, empleado_id: int = None) -> tuple:
        """Remove a line item from an order and recalculate total. Returns (ok, msg)."""
        s = self.session
        try:
            pedido = s.query(Pedido).filter_by(PedidoID=pedido_id).first()
            if not pedido:
                return False, "Pedido no encontrado"
            if pedido.Estado not in self._ESTADOS_MODIFICABLES:
                return False, f"No se pueden modificar items en estado '{pedido.Estado}'"

            detalle = s.query(PedidoDetalle).filter_by(
                DetalleID=detalle_id, PedidoID=pedido_id
            ).first()
            if not detalle:
                return False, "Item no encontrado en este pedido"

            otros = s.query(PedidoDetalle).filter(
                PedidoDetalle.PedidoID == pedido_id,
                PedidoDetalle.DetalleID != detalle_id,
            ).count()
            if otros == 0:
                return False, "No se puede eliminar el único item. Cancela el pedido en su lugar."

            valor_anterior = {
                'detalle_id': detalle_id,
                'nombre': detalle.NombreProducto,
                'cantidad': detalle.Cantidad,
                'subtotal': float(detalle.Subtotal) if detalle.Subtotal else 0.0,
            }

            s.delete(detalle)
            s.flush()
            self._recalcular_total(s, pedido)

            s.add(AuditLog(
                pedido_id=pedido_id,
                empleado_id=empleado_id,
                accion='eliminar_item',
                detalles=json.dumps({
                    'item_eliminado': valor_anterior,
                    'nuevo_total': float(pedido.Total),
                }),
            ))
            s.commit()
            return True, f"Item '{valor_anterior['nombre']}' eliminado. Total recalculado: {float(pedido.Total):.2f}€"
        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error al eliminar item %s del pedido %s: %s", detalle_id, pedido_id, e)
            return False, "Error de base de datos"

    def sustituir_item(
        self,
        pedido_id: int,
        detalle_id: int,
        producto_sustituto_id: int,
        cantidad_a_sustituir: int = None,
        empleado_id: int = None,
    ) -> tuple:
        """Replace (fully or partially) a line item with another product.

        If cantidad_a_sustituir < detalle.Cantidad, the original line is split:
        the original keeps the remaining units and a new PedidoDetalle is created
        for the substitute product with the requested quantity.

        Returns (ok, msg).
        """
        s = self.session
        try:
            pedido = s.query(Pedido).filter_by(PedidoID=pedido_id).first()
            if not pedido:
                return False, "Pedido no encontrado"
            if pedido.Estado not in self._ESTADOS_MODIFICABLES:
                return False, f"No se pueden modificar items en estado '{pedido.Estado}'"

            detalle = s.query(PedidoDetalle).filter_by(
                DetalleID=detalle_id, PedidoID=pedido_id
            ).first()
            if not detalle:
                return False, "Item no encontrado en este pedido"

            sustituto = s.query(Producto).filter_by(ProductoID=producto_sustituto_id).first()
            if not sustituto:
                return False, "Producto sustituto no encontrado"

            qty = cantidad_a_sustituir if cantidad_a_sustituir is not None else detalle.Cantidad
            if qty <= 0 or qty > detalle.Cantidad:
                return False, f"Cantidad inválida. El item tiene {detalle.Cantidad} unidades."

            precio_original = detalle.PrecioUnitario or Decimal('0.00')
            precio_nuevo = Decimal(str(sustituto.Precio))

            valor_anterior = {
                'detalle_id': detalle_id,
                'producto_id': detalle.ProductoID,
                'nombre': detalle.NombreProducto,
                'cantidad': detalle.Cantidad,
                'precio_unitario': float(precio_original),
                'subtotal': float(detalle.Subtotal) if detalle.Subtotal else 0.0,
            }

            if qty == detalle.Cantidad:
                # --- Full replacement: update the existing line ---
                detalle.ProductoID = producto_sustituto_id
                detalle.NombreProducto = sustituto.Nombre
                detalle.PrecioUnitario = precio_nuevo
                detalle.Subtotal = precio_nuevo * qty
                if detalle.picking_item:
                    detalle.picking_item.producto_sustituto_id = producto_sustituto_id
                    detalle.picking_item.estado = 'sustituido'
                subtotal_nuevo = float(detalle.Subtotal)
            else:
                # --- Partial split: reduce original + create new line for substitute ---
                restante = detalle.Cantidad - qty
                detalle.Cantidad = restante
                detalle.Subtotal = precio_original * restante

                nuevo_detalle = PedidoDetalle(
                    PedidoID=pedido_id,
                    ProductoID=producto_sustituto_id,
                    Cantidad=qty,
                    PrecioUnitario=precio_nuevo,
                    NombreProducto=sustituto.Nombre,
                    Subtotal=precio_nuevo * qty,
                )
                s.add(nuevo_detalle)
                s.flush()  # get nuevo_detalle.DetalleID

                # If picking is active, register the new detalle as a picking item
                if pedido.picking and pedido.picking.estado not in ('completado', 'cancelado'):
                    s.add(PickingItem(
                        picking_id=pedido.picking.id,
                        pedido_detalle_id=nuevo_detalle.DetalleID,
                        estado='sustituido',
                        cantidad_encontrada=qty,
                        producto_sustituto_id=producto_sustituto_id,
                    ))
                subtotal_nuevo = float(precio_nuevo * qty)

            s.flush()
            self._recalcular_total(s, pedido)

            s.add(AuditLog(
                pedido_id=pedido_id,
                empleado_id=empleado_id,
                accion='sustituir_item',
                detalles=json.dumps({
                    'anterior': valor_anterior,
                    'sustituido': {
                        'producto_id': producto_sustituto_id,
                        'nombre': sustituto.Nombre,
                        'cantidad': qty,
                        'precio_unitario': float(precio_nuevo),
                        'subtotal': subtotal_nuevo,
                    },
                    'parcial': qty < valor_anterior['cantidad'],
                    'nuevo_total': float(pedido.Total),
                }),
            ))
            s.commit()
            parcial = qty < valor_anterior['cantidad']
            msg = (
                f"{qty}× '{valor_anterior['nombre']}' → '{sustituto.Nombre}'"
                + (f" (quedan {valor_anterior['cantidad'] - qty}× originales)" if parcial else "")
                + f". Total: {float(pedido.Total):.2f}€"
            )
            return True, msg
        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error al sustituir item %s del pedido %s: %s", detalle_id, pedido_id, e)
            return False, "Error de base de datos"

    def obtener_pedido(self, pedido_id):
        try:
            pedido = self.session.query(Pedido).filter_by(PedidoID=pedido_id).first()
            if not pedido:
                logger.warning("No se encontró un pedido con el ID %s.", pedido_id)
            return pedido
        except SQLAlchemyError as error:
            logger.error("Error al recuperar el pedido con ID %s: %s", pedido_id, error)
            raise



