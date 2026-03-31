"""Reparto — cobro y cierre de caja del repartidor."""
import logging
from datetime import date, datetime, timedelta

from sqlalchemy.exc import SQLAlchemyError

from managers.dashboard._helpers import _iso
from models import Reparto
from states import EstadoReparto

logger = logging.getLogger(__name__)


class GestorRepartoCobroMixin:

    def registrar_cobro(
        self,
        reparto_id: int,
        metodo_cobro: str,
        importe_cobrado: float,
        cambio_devuelto: float | None = None,
        importe_efectivo: float | None = None,
        importe_tarjeta: float | None = None,
    ) -> tuple:
        """Persists the payment collection made by the delivery driver."""
        METODOS_VALIDOS = {'efectivo', 'tarjeta', 'mixto'}
        if metodo_cobro not in METODOS_VALIDOS:
            return False, f"Método inválido. Válidos: {', '.join(METODOS_VALIDOS)}"

        s = self.session
        try:
            reparto = s.query(Reparto).filter_by(id=reparto_id).first()
            if not reparto:
                return False, "Reparto no encontrado"

            reparto.metodo_cobro     = metodo_cobro
            reparto.importe_cobrado  = importe_cobrado
            reparto.cambio_devuelto  = cambio_devuelto
            reparto.importe_efectivo = importe_efectivo
            reparto.importe_tarjeta  = importe_tarjeta
            s.commit()
            return True, "Cobro registrado"
        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error registrando cobro reparto %s: %s", reparto_id, e)
            return False, "Error de base de datos"

    def cierre_caja_repartidor(self, repartidor_id: int, fecha: date | None = None) -> dict:
        """Returns cash-closing summary for a repartidor on a given day (default: today UTC)."""
        if fecha is None:
            fecha = datetime.utcnow().date()

        dia_inicio = datetime.combine(fecha, datetime.min.time())
        dia_fin    = dia_inicio + timedelta(days=1)

        s = self.session
        repartos = (
            s.query(Reparto)
            .filter(
                Reparto.repartidor_id == repartidor_id,
                Reparto.estado == EstadoReparto.ENTREGADO.value,
                Reparto.hora_entrega_real >= dia_inicio,
                Reparto.hora_entrega_real < dia_fin,
            )
            .order_by(Reparto.hora_entrega_real)
            .all()
        )

        online_list, efectivo_list, tarjeta_list, mixto_list, sin_registro = [], [], [], [], []

        for r in repartos:
            pedido = r.pedido
            if not pedido:
                continue
            if r.metodo_cobro == 'efectivo':
                efectivo_list.append(r)
            elif r.metodo_cobro == 'tarjeta':
                tarjeta_list.append(r)
            elif r.metodo_cobro == 'mixto':
                mixto_list.append(r)
            else:
                # Sin cobro registrado — inferir del pedido
                pago_ok = next((p for p in pedido.pagos if p.estado == 'completado'), None)
                if pago_ok or getattr(pedido, 'forma_pago', 'online') == 'online':
                    online_list.append(r)
                else:
                    sin_registro.append(r)

        # Efectivo total a entregar al local = efectivo puro + parte efectivo de mixto
        total_efectivo = round(
            sum(float(r.importe_cobrado or 0) for r in efectivo_list)
            + sum(float(r.importe_efectivo or 0) for r in mixto_list),
            2,
        )
        total_tarjeta = round(
            sum(float(r.importe_cobrado or 0) for r in tarjeta_list)
            + sum(float(r.importe_tarjeta or 0) for r in mixto_list),
            2,
        )

        def _detalle(r):
            """Normaliza el detalle de cobro de un reparto."""
            pedido = r.pedido
            return {
                "reparto_id":    r.id,
                "pedido_id":     pedido.PedidoID if pedido else None,
                "cliente":       pedido.cliente.nombre if pedido and pedido.cliente else "—",
                "hora_entrega":  _iso(r.hora_entrega_real),
                "metodo_cobro":  r.metodo_cobro,
                "importe":       float(pedido.Total) if pedido and pedido.Total else 0.0,
                "importe_cobrado":  float(r.importe_cobrado or 0),
                "cambio_devuelto":  float(r.cambio_devuelto or 0),
                "importe_efectivo": float(r.importe_efectivo or 0),
                "importe_tarjeta":  float(r.importe_tarjeta or 0),
            }

        return {
            "fecha":          fecha.isoformat(),
            "repartidor_id":  repartidor_id,
            "total_pedidos":  len(repartos),
            "online":         {"count": len(online_list),   "total": 0.0},
            "efectivo":       {"count": len(efectivo_list), "total": round(sum(float(r.importe_cobrado or 0) for r in efectivo_list), 2)},
            "tarjeta":        {"count": len(tarjeta_list),  "total": round(sum(float(r.importe_cobrado or 0) for r in tarjeta_list), 2)},
            "mixto":          {
                "count":    len(mixto_list),
                "efectivo": round(sum(float(r.importe_efectivo or 0) for r in mixto_list), 2),
                "tarjeta":  round(sum(float(r.importe_tarjeta  or 0) for r in mixto_list), 2),
            },
            "sin_registro":   {"count": len(sin_registro)},
            "total_efectivo_a_entregar": total_efectivo,
            "total_tarjeta_registrado":  total_tarjeta,
            "detalle": [_detalle(r) for r in repartos],
        }
