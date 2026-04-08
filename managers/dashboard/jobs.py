# managers/dashboard/jobs.py
"""Jobs RQ centralizados para side effects del dashboard.

Estos jobs se ejecutan en los workers (background), no en el request.
Cada job:
  - No usa self ni accede a estado global de la app.
  - Crea su propia sesión de BD (SessionLocal).
  - Levanta excepción si falla (RQ reintenta automáticamente).
  - Tiene @sentry_job para métricas de performance.
"""
import logging

from sqlalchemy.exc import SQLAlchemyError

from states import EstadoPicking
from utils.rq_callbacks import sentry_job

logger = logging.getLogger(__name__)


@sentry_job(op_name="rq.notificar_picker")
def notificar_picker_job(picker_telefono: str, pedido_id: int) -> None:
    """Envía WhatsApp al picker notificando que tiene un nuevo pedido asignado.

    Args:
        picker_telefono: Teléfono del picker (formato E.164, ej: +34600000001)
        pedido_id: ID del pedido asignado
    """
    from services.whatsapp_service import enviar_mensaje_whatsapp

    mensaje = f"🛒 Tienes un nuevo pedido asignado: #{pedido_id}. Ve al dashboard para verlo."
    enviar_mensaje_whatsapp(mensaje, picker_telefono)
    logger.info("Notificación picker enviada: pedido %s → %s", pedido_id, picker_telefono)


@sentry_job(op_name="rq.notificar_repartidor")
def notificar_repartidor_job(repartidor_telefono: str, pedido_id: int) -> None:
    """Envía WhatsApp al repartidor notificando que tiene un pedido para repartir.

    Args:
        repartidor_telefono: Teléfono del repartidor (formato E.164)
        pedido_id: ID del pedido asignado
    """
    from services.whatsapp_service import enviar_mensaje_whatsapp

    mensaje = f"🚴 Tienes un pedido listo para repartir: #{pedido_id}. Ve al dashboard para verlo."
    enviar_mensaje_whatsapp(mensaje, repartidor_telefono)
    logger.info("Notificación repartidor enviada: pedido %s → %s", pedido_id, repartidor_telefono)


@sentry_job(op_name="rq.descontar_stock")
def descontar_stock_picking_job(picking_id: int) -> None:
    """Descuenta stock de los productos tras completar un picking.

    Recibe picking_id (int), NO la lista de items precalculada.
    Razón: si RQ reintenta, el job re-lee el estado actual de BD.
    La idempotencia la garantiza PickingPedido.stock_descontado.

    Args:
        picking_id: ID del PickingPedido completado
    """
    from database import SessionLocal
    from models import PickingPedido, Producto

    s = SessionLocal()
    try:
        picking = s.query(PickingPedido).filter_by(id=picking_id).first()
        if not picking:
            logger.warning("descontar_stock_picking_job: picking %s no encontrado", picking_id)
            return

        if picking.stock_descontado:
            logger.info("descontar_stock_picking_job: picking %s ya procesado — skip", picking_id)
            return

        if picking.estado != EstadoPicking.COMPLETADO.value:
            logger.warning(
                "descontar_stock_picking_job: picking %s en estado '%s', no COMPLETADO — skip",
                picking_id, picking.estado,
            )
            return

        for item in picking.items:
            if not item.pedido_detalle or not item.pedido_detalle.ProductoID:
                continue

            p = (
                s.query(Producto)
                .filter_by(ProductoID=item.pedido_detalle.ProductoID)
                .with_for_update()
                .first()
            )
            if not p:
                continue

            if item.estado == "encontrado":
                cantidad = item.cantidad_encontrada or item.pedido_detalle.Cantidad
                p.Stock = max(0, p.Stock - cantidad)
                if p.Stock == 0:
                    p.Disponible = False
            elif item.estado == "sin_stock":
                p.Stock = 0
                p.Disponible = False

        picking.stock_descontado = True
        s.commit()
        logger.info("Stock descontado OK: picking %s", picking_id)

    except SQLAlchemyError as e:
        s.rollback()
        logger.error("Error descontando stock picking %s: %s", picking_id, e, exc_info=True)
        raise  # RQ reintenta automáticamente
    finally:
        s.close()


@sentry_job(op_name="rq.actualizar_estado_operativo")
def actualizar_estado_operativo_job(empleado_id: int, nuevo_estado: str) -> None:
    """Actualiza estado_operativo del empleado de forma segura.

    Estados en_pausa y desconectado son manuales — el sistema no los sobreescribe.

    Args:
        empleado_id: ID del empleado
        nuevo_estado: Nuevo estado (ej: "disponible", "ocupado")
    """
    from database import SessionLocal
    from models import Empleado

    _ESTADOS_PROTEGIDOS = frozenset({'en_pausa', 'desconectado'})

    s = SessionLocal()
    try:
        updated = s.query(Empleado).filter(
            Empleado.EmpleadoID == empleado_id,
            Empleado.estado_operativo.notin_(_ESTADOS_PROTEGIDOS),
        ).update({'estado_operativo': nuevo_estado}, synchronize_session=False)
        s.commit()

        if updated > 0:
            logger.info("Estado actualizado: empleado %s → %s", empleado_id, nuevo_estado)
        else:
            logger.warning(
                "Estado protegido: empleado %s está en pausa/desconectado, no se actualizó",
                empleado_id,
            )
    except SQLAlchemyError as e:
        s.rollback()
        logger.error("Error actualizando estado empleado %s: %s", empleado_id, e, exc_info=True)
        raise  # RQ reintenta automáticamente
    finally:
        s.close()
