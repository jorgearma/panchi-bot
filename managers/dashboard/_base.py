import logging
from collections import defaultdict
from datetime import datetime

from sqlalchemy import and_, or_, text
from sqlalchemy import func
from sqlalchemy.orm import aliased, joinedload

from models import Empleado, HistorialEstadoPedido, PickingPedido, Reparto, Pedido
from states import EstadoPedido, EstadoPicking, EstadoReparto

logger = logging.getLogger(__name__)


class GestorDashboardBase:

    @property
    def session(self):
        """Devuelve la sesión activa de base de datos."""
        from database import get_db
        return get_db()

    _ESTADOS_PROTEGIDOS = frozenset({'en_pausa', 'desconectado'})

    def _actualizar_estado_operativo(self, empleado_id: int, nuevo_estado: str) -> None:
        """Encola actualización de estado_operativo en RQ.

        Los estados en_pausa y desconectado son manuales — el sistema no los sobreescribe.
        Usa RQ para reintentos automáticos si la BD falla.

        Args:
            empleado_id: ID del empleado (validado)
            nuevo_estado: Nuevo estado operativo (ej: "recibiendo_pedidos")
        """
        if not isinstance(empleado_id, int) or empleado_id <= 0:
            logger.warning("empleado_id inválido: %s", empleado_id)
            return
        if not nuevo_estado or not isinstance(nuevo_estado, str):
            logger.warning("nuevo_estado inválido: %s", nuevo_estado)
            return

        from message_queue import queue_dashboard
        from managers.dashboard.jobs import actualizar_estado_operativo_job
        from utils.rq_callbacks import on_job_failure

        job = queue_dashboard.enqueue(
            actualizar_estado_operativo_job,
            empleado_id,
            nuevo_estado,
            on_failure=on_job_failure,
            retry=3,
            failure_ttl=86400,
        )
        logger.debug(
            "Encolado update estado_operativo: empleado %s → %s (job_id=%s)",
            empleado_id, nuevo_estado, job.id,
        )

    def _tiempo_medio(self, desde: datetime, estado_inicio: EstadoPedido, estado_fin: EstadoPedido):
        """Calcula el tiempo medio en minutos entre dos estados usando un self-join en SQL Server.

        Una sola query en lugar de 1 query por pedido (N+1 anterior).

        Note: uses a SQL Server DATEDIFF self-join. If a pedido has multiple estado_inicio
        events (re-entry), all pairs are included in the average. Safe under the current
        state machine which does not allow state re-entry.
        """
        s = self.session
        h_fin = aliased(HistorialEstadoPedido)
        h_ini = aliased(HistorialEstadoPedido)

        result = (
            s.query(
                func.avg(
                    func.datediff(text('minute'), h_ini.cambiado_en, h_fin.cambiado_en)
                )
            )
            .select_from(h_fin)
            .join(h_ini, and_(
                h_ini.pedido_id == h_fin.pedido_id,
                h_ini.estado_nuevo == estado_inicio.value,
                h_ini.cambiado_en <= h_fin.cambiado_en,
            ))
            .filter(
                h_fin.estado_nuevo == estado_fin.value,
                h_fin.cambiado_en >= desde,
            )
            .scalar()
        )
        return round(float(result), 1) if result is not None else None

    def _batch_pickings(
        self,
        ids: list,
        estados_activos: list,
        desde: datetime,
    ) -> dict:
        """Carga pickings activos + completados hoy para una lista de empleado_ids en una sola query.

        Returns:
            defaultdict con clave empleado_id → {'activos': [...], 'completados': [...]}
            Los 'completados' son los finalizados desde `desde`.
            Los objetos PickingPedido vienen con `items` eager-loaded.

        Note: estados_activos must contain string values (e.g. EstadoPicking.X.value),
        not enum members. If a pedido re-enters a state multiple times (not possible
        under the current state machine), each re-entry is treated as a separate 'activo'.
        """
        if not ids:
            return defaultdict(lambda: {'activos': [], 'completados': []})

        rows = (
            self.session.query(PickingPedido)
            .options(joinedload(PickingPedido.items))
            .filter(
                PickingPedido.empleado_id.in_(ids),
                or_(
                    PickingPedido.estado.in_(estados_activos),
                    and_(
                        PickingPedido.estado == EstadoPicking.COMPLETADO.value,
                        PickingPedido.completado_en >= desde,
                    ),
                ),
            )
            .all()
        )

        result: dict = defaultdict(lambda: {'activos': [], 'completados': []})
        for pk in rows:
            if pk.estado in estados_activos:
                result[pk.empleado_id]['activos'].append(pk)
            else:
                result[pk.empleado_id]['completados'].append(pk)
        return result

    def _batch_repartos(
        self,
        ids: list,
        estados_activos: list,
        desde: datetime,
    ) -> dict:
        """Carga repartos activos + entregados hoy para una lista de repartidor_ids en una sola query.

        Returns:
            defaultdict con clave repartidor_id → {'activos': [...], 'entregados': [...]}
            Los objetos Reparto vienen con pedido y pedido.cliente eager-loaded.

        Note: estados_activos must contain string values (e.g. EstadoReparto.X.value),
        not enum members. If a reparto re-enters a state multiple times (not possible
        under the current state machine), each re-entry is treated as a separate 'activo'.
        """
        if not ids:
            return defaultdict(lambda: {'activos': [], 'entregados': []})

        rows = (
            self.session.query(Reparto)
            .options(
                joinedload(Reparto.pedido).joinedload(Pedido.cliente)
            )
            .filter(
                Reparto.repartidor_id.in_(ids),
                or_(
                    Reparto.estado.in_(estados_activos),
                    and_(
                        Reparto.estado == EstadoReparto.ENTREGADO.value,
                        Reparto.hora_entrega_real >= desde,
                    ),
                ),
            )
            .all()
        )

        result: dict = defaultdict(lambda: {'activos': [], 'entregados': []})
        for r in rows:
            if r.estado in estados_activos:
                result[r.repartidor_id]['activos'].append(r)
            else:
                result[r.repartidor_id]['entregados'].append(r)
        return result
