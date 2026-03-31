"""Reparto — tracking: mapa, estado de rutas, entrega."""
import logging
from datetime import datetime
from threading import Thread

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload, selectinload

from managers.dashboard._helpers import (
    _iso,
    _TARANCON_LAT,
    _TARANCON_LNG,
    _ESTADOS_OPERATIVOS,
)
from models import (
    HistorialEstadoPedido, Pedido, PedidoDetalle, Reparto,
)
from states import EstadoPedido, EstadoReparto, transicion_valida_pedido

logger = logging.getLogger(__name__)


class GestorRepartoTrackingMixin:

    def mapa(self) -> dict:
        """Devuelve los puntos activos para el mapa operativo."""
        pedidos = self.session.query(Pedido).filter(
            Pedido.Estado.in_(_ESTADOS_OPERATIVOS)
        ).all()

        puntos = []
        for p in pedidos:
            if p.lat_entrega is None or p.lng_entrega is None:
                continue
            puntos.append({
                "pedido_id": p.PedidoID,
                "estado": p.Estado,
                "direccion": p.DireccionEntrega,
                "lat": p.lat_entrega,
                "lng": p.lng_entrega,
                "fecha_creacion": _iso(p.FechaCreacion),
                "total": float(p.Total) if p.Total else 0.0,
            })

        return {
            "centro": {"lat": _TARANCON_LAT, "lng": _TARANCON_LNG},
            "pedidos": puntos,
            "repartidores": [],
        }

    def repartos_del_repartidor(self, empleado_id: int) -> list:
        """Returns active and today's completed orders for a delivery driver."""
        from sqlalchemy import or_, and_
        s = self.session
        hoy_inicio = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        repartos = s.query(Reparto).options(
            joinedload(Reparto.pedido).options(
                joinedload(Pedido.cliente),
                selectinload(Pedido.pagos),
                selectinload(Pedido.detalles).joinedload(PedidoDetalle.producto),
            )
        ).filter(
            Reparto.repartidor_id == empleado_id,
            or_(
                Reparto.estado.in_([
                    EstadoReparto.ASIGNADO.value,
                    EstadoReparto.EN_CAMINO.value,
                ]),
                and_(
                    Reparto.estado.in_([
                        EstadoReparto.ENTREGADO.value,
                        EstadoReparto.NO_ENTREGADO.value,
                    ]),
                    Reparto.created_at >= hoy_inicio,
                ),
            ),
        ).order_by(Reparto.created_at.desc()).all()

        resultado = []
        for r in repartos:
            pedido = r.pedido
            if not pedido:
                continue

            # Payment info: check Pago table first, then forma_pago field
            pago_completado = next(
                (p for p in pedido.pagos if p.estado == 'completado'), None
            )
            if pago_completado:
                info_pago = {
                    "estado": "pagado_online",
                    "label": "Pagado online",
                    "importe": float(pago_completado.importe),
                    "proveedor": pago_completado.proveedor,
                }
            elif getattr(pedido, 'forma_pago', None) == 'efectivo':
                info_pago = {
                    "estado": "cobrar_efectivo",
                    "label": "Cobrar",
                    "importe": float(pedido.Total) if pedido.Total else 0.0,
                    "proveedor": None,
                }
            elif getattr(pedido, 'forma_pago', None) == 'tarjeta':
                info_pago = {
                    "estado": "cobrar_tarjeta",
                    "label": "Cobrar con datáfono",
                    "importe": float(pedido.Total) if pedido.Total else 0.0,
                    "proveedor": None,
                }
            else:
                info_pago = {
                    "estado": "pagado_online",
                    "label": "Pagado online",
                    "importe": float(pedido.Total) if pedido.Total else 0.0,
                    "proveedor": "monei",
                }

            items = [
                {
                    "nombre": d.NombreProducto or (d.producto.Nombre if d.producto else "—"),
                    "cantidad": d.Cantidad,
                    "subtotal": float(d.Subtotal) if d.Subtotal else 0.0,
                }
                for d in pedido.detalles
            ]

            resultado.append({
                "reparto_id": r.id,
                "pedido_id": pedido.PedidoID,
                "estado_reparto": r.estado,
                "estado_pedido": pedido.Estado,
                "cliente_nombre": pedido.cliente.nombre if pedido.cliente else "—",
                "cliente_telefono": pedido.TelefonoEntrega,
                "direccion_entrega": pedido.DireccionEntrega,
                "lat": pedido.lat_entrega,
                "lng": pedido.lng_entrega,
                "total": float(pedido.Total) if pedido.Total else 0.0,
                "pago": info_pago,
                "items": items,
                "fecha_creacion": _iso(pedido.FechaCreacion),
                "hora_salida": _iso(r.hora_salida),
                "hora_estimada_entrega": _iso(r.hora_estimada_entrega),
                "hora_entrega_real": _iso(r.hora_entrega_real),
                "motivo_no_entrega": r.motivo_no_entrega,
                "notas": r.notas,
            })

        return resultado

    def marcar_salida_reparto(self, reparto_id: int) -> tuple:
        """Returns (ok, msg, telefono_cliente). telefono_cliente is None on error."""
        s = self.session
        try:
            reparto = s.query(Reparto).filter_by(id=reparto_id).first()
            if not reparto:
                return False, "Reparto no encontrado", None

            reparto.estado = EstadoReparto.EN_CAMINO.value
            reparto.hora_salida = datetime.utcnow()

            pedido = reparto.pedido
            if pedido and transicion_valida_pedido(pedido.Estado, EstadoPedido.EN_REPARTO.value):
                estado_anterior = pedido.Estado
                pedido.Estado = EstadoPedido.EN_REPARTO.value
                s.add(HistorialEstadoPedido(
                    pedido_id=pedido.PedidoID,
                    estado_anterior=estado_anterior,
                    estado_nuevo=EstadoPedido.EN_REPARTO.value,
                    notas="Repartidor en camino",
                ))

            s.commit()
            telefono = pedido.TelefonoEntrega if pedido else None
            return True, "Repartidor marcado como en camino", telefono
        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error marcando salida reparto %s: %s", reparto_id, e)
            return False, "Error de base de datos", None

    def marcar_no_entregado(self, reparto_id: int, motivo: str) -> tuple:
        """Marks a delivery as not delivered. Updates reparto only — pedido state stays as-is
        so the ops team can handle it from the dashboard."""
        s = self.session
        try:
            reparto = s.query(Reparto).filter_by(id=reparto_id).first()
            if not reparto:
                return False, "Reparto no encontrado"
            if reparto.estado not in (EstadoReparto.EN_CAMINO.value, EstadoReparto.ENTREGADO.value):
                return False, f"Estado actual '{reparto.estado}' no permite marcar como no entregado"

            reparto.estado = EstadoReparto.NO_ENTREGADO.value
            reparto.motivo_no_entrega = motivo

            pedido = reparto.pedido
            s.commit()
            telefono = pedido.TelefonoEntrega if pedido else None
            return True, "Marcado como no entregado", telefono
        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error marcando no entregado reparto %s: %s", reparto_id, e)
            return False, "Error de base de datos", None

    def marcar_entregado(self, reparto_id: int) -> tuple:
        """Returns (ok, msg, telefono_cliente). telefono_cliente is None on error."""
        s = self.session
        try:
            reparto = s.query(Reparto).filter_by(id=reparto_id).first()
            if not reparto:
                return False, "Reparto no encontrado", None

            # Guard: para contra reembolso (efectivo/tarjeta), el cobro debe estar registrado
            forma_pago = reparto.pedido.forma_pago if reparto.pedido else None
            if forma_pago in ('efectivo', 'tarjeta') and reparto.metodo_cobro is None:
                return False, "Debes registrar el cobro antes de marcar como entregado", None

            reparto.estado = EstadoReparto.ENTREGADO.value
            reparto.hora_entrega_real = datetime.utcnow()

            pedido = reparto.pedido
            if pedido and transicion_valida_pedido(pedido.Estado, EstadoPedido.ENTREGADO.value):
                estado_anterior = pedido.Estado
                pedido.Estado = EstadoPedido.ENTREGADO.value
                s.add(HistorialEstadoPedido(
                    pedido_id=pedido.PedidoID,
                    estado_anterior=estado_anterior,
                    estado_nuevo=EstadoPedido.ENTREGADO.value,
                    notas="Entregado al cliente",
                ))

            s.commit()

            # Auto-actualizar estado en background: no bloquea la respuesta HTTP
            _repartidor_id = reparto.repartidor_id
            if _repartidor_id:
                def _actualizar_disponibilidad(emp_id=_repartidor_id):
                    """Marca disponible al repartidor si ya no tiene rutas activas."""
                    from database import SessionLocal
                    _s = SessionLocal()
                    try:
                        _activos = _s.query(Reparto).filter(
                            Reparto.repartidor_id == emp_id,
                            Reparto.estado.in_([
                                EstadoReparto.ASIGNADO.value,
                                EstadoReparto.EN_CAMINO.value,
                            ]),
                        ).count()
                        if _activos == 0:
                            self._actualizar_estado_operativo(emp_id, 'disponible')
                    except Exception as e:
                        logger.warning("Error comprobando disponibilidad repartidor %s: %s", emp_id, e)
                    finally:
                        _s.close()
                Thread(target=_actualizar_disponibilidad, daemon=True).start()

            telefono = pedido.TelefonoEntrega if pedido else None
            return True, "Pedido marcado como entregado", telefono
        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error marcando entregado reparto %s: %s", reparto_id, e)
            return False, "Error de base de datos", None
