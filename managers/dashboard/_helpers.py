"""Constantes y helpers de módulo compartidos por todos los mixins del dashboard."""
# También importados por managers/metricas/empleados_mixin.py para evitar divergencias
# en el cálculo de tiempos de operación.

from states import EstadoPedido


def _dur_picking(pk) -> float | None:
    """Duración de un PickingPedido en minutos (iniciado_en → completado_en), o None."""
    if pk.iniciado_en and pk.completado_en:
        return (pk.completado_en - pk.iniciado_en).total_seconds() / 60
    return None


def _dur_reparto(r) -> float | None:
    """Duración de un Reparto en minutos (hora_salida → hora_entrega_real), o None."""
    if r.hora_salida and r.hora_entrega_real:
        return (r.hora_entrega_real - r.hora_salida).total_seconds() / 60
    return None


def _iso(dt) -> str | None:
    """Serializes a UTC datetime to ISO 8601 with 'Z' suffix.
    Without 'Z', browsers interpret the string as local time instead of UTC,
    causing a 1-hour (or 2-hour in summer) offset in all time calculations.
    """
    return dt.isoformat() + 'Z' if dt else None


# Tarancón coordinates (center)
_TARANCON_LAT = 40.0041
_TARANCON_LNG = -2.9980

_COLORES_ESTADO = {
    EstadoPedido.PAGADO.value:           "#10b981",
    EstadoPedido.CONTRA_REEMBOLSO.value: "#8b5cf6",
    EstadoPedido.EN_PREPARACION.value:   "#3b82f6",
    EstadoPedido.PREPARADO.value:        "#6366f1",
    EstadoPedido.EN_REPARTO.value:       "#f97316",
}

# Minutes before an order in a state is flagged as delayed
_UMBRALES_RETRASO = {
    EstadoPedido.PAGADO.value:           (10, "warning", "pagado sin iniciar picking"),
    EstadoPedido.CONTRA_REEMBOLSO.value: (10, "warning", "contra reembolso sin iniciar picking"),
    EstadoPedido.EN_PREPARACION.value:   (30, "warning", "en preparación"),
    EstadoPedido.PREPARADO.value:        (15, "error",   "preparado sin repartidor"),
    EstadoPedido.EN_REPARTO.value:       (60, "error",   "en reparto"),
}

# Estados que deben aparecer en el panel operativo
_ESTADOS_OPERATIVOS = [
    EstadoPedido.PAGADO.value,
    EstadoPedido.CONTRA_REEMBOLSO.value,
    EstadoPedido.EN_PREPARACION.value,
    EstadoPedido.PREPARADO.value,
    EstadoPedido.EN_REPARTO.value,
]

# Estados que necesitan que se les asigne picking (listos para preparar)
_ESTADOS_LISTOS_PARA_PICKING = [
    EstadoPedido.PAGADO.value,
    EstadoPedido.CONTRA_REEMBOLSO.value,
]
