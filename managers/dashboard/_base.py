import logging
from datetime import datetime
from threading import Thread

from models import Empleado, HistorialEstadoPedido
from states import EstadoPedido

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
                empleado = s.query(Empleado).filter_by(EmpleadoID=empleado_id).first()
                if empleado and empleado.estado_operativo not in estados_protegidos:
                    empleado.estado_operativo = nuevo_estado
                    s.commit()
            except Exception as e:
                logger.warning("No se pudo actualizar estado_operativo de empleado %s: %s", empleado_id, e)
                s.rollback()
            finally:
                s.close()

        Thread(target=_ejecutar, daemon=True).start()

    def _tiempo_medio(self, desde: datetime, estado_inicio: EstadoPedido, estado_fin: EstadoPedido):
        """Calcula el tiempo medio en minutos entre dos estados."""
        s = self.session
        finales = s.query(HistorialEstadoPedido).filter(
            HistorialEstadoPedido.estado_nuevo == estado_fin.value,
            HistorialEstadoPedido.cambiado_en >= desde,
        ).all()

        tiempos = []
        for final in finales:
            inicio = (
                s.query(HistorialEstadoPedido)
                .filter(
                    HistorialEstadoPedido.pedido_id == final.pedido_id,
                    HistorialEstadoPedido.estado_nuevo == estado_inicio.value,
                    HistorialEstadoPedido.cambiado_en <= final.cambiado_en,
                )
                .order_by(HistorialEstadoPedido.cambiado_en.desc())
                .first()
            )
            if inicio:
                delta = (final.cambiado_en - inicio.cambiado_en).total_seconds() / 60
                tiempos.append(delta)

        return round(sum(tiempos) / len(tiempos)) if tiempos else None
