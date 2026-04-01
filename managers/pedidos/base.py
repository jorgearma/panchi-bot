from decimal import Decimal

from database import get_db
from states import EstadoPedido


class GestorPedidosBase:
    _MOTIVOS_CANCELACION = {
        'cliente_cancelo',
        'falta_stock',
        'direccion_incorrecta',
        'cliente_no_responde',
        'pedido_duplicado',
        'otro',
    }
    _ESTADOS_MODIFICABLES = {
        EstadoPedido.PAGADO.value,
        EstadoPedido.CONTRA_REEMBOLSO.value,
        EstadoPedido.EN_PREPARACION.value,
    }

    @property
    def session(self):
        """Devuelve la sesión activa de base de datos."""
        return get_db()

    @staticmethod
    def _to_decimal(value) -> Decimal:
        """Normaliza un valor numerico a Decimal."""
        return Decimal(str(value or 0))
