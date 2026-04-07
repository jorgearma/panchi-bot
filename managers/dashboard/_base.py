import logging
from collections import defaultdict
from datetime import datetime
from threading import Thread

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
        """Actualiza estado_operativo en background con su propia sesión de BD.

        Los estados en_pausa y desconectado son manuales — el sistema no los sobreescribe.
        Corre en un thread daemon para no bloquear la respuesta HTTP.
        """
        if not empleado_id:
            return
        estados_protegidos = self._ESTADOS_PROTEGIDOS

        def _ejecutar():
            """Aplica el cambio de estado sin bloquear la petición."""
            from database import SessionLocal
            s = SessionLocal()
            try:
                s.query(Empleado).filter(
                    Empleado.EmpleadoID == empleado_id,
                    Empleado.estado_operativo.notin_(estados_protegidos),
                ).update({'estado_operativo': nuevo_estado}, synchronize_session=False)
                s.commit()
            except Exception as e:
                logger.warning("No se pudo actualizar estado_operativo de empleado %s: %s", empleado_id, e)
                s.rollback()
            finally:
                s.close()

        Thread(target=_ejecutar, daemon=True).start()

    def _tiempo_medio(self, desde: datetime, estado_inicio: EstadoPedido, estado_fin: EstadoPedido):
        """Calcula el tiempo medio en minutos entre dos estados usando un self-join en SQL Server.

        Una sola query en lugar de 1 query por pedido (N+1 anterior).
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
        """
        empty: dict = defaultdict(lambda: {'activos': [], 'completados': []})
        if not ids:
            return empty

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
        """
        empty: dict = defaultdict(lambda: {'activos': [], 'entregados': []})
        if not ids:
            return empty

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
