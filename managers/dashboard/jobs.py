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


