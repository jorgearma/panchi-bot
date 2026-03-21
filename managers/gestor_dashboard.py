import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from models import (
    Empleado, HistorialEstadoPedido, Incidencia, Pedido, PickingItem,
    PickingPedido, Producto, Reparto, Rol,
)
from states import (
    ESTADOS_TERMINALES_PEDIDO, EstadoPedido, EstadoPicking, EstadoReparto,
    transicion_valida_pedido,
)

logger = logging.getLogger(__name__)


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


class GestorDashboard:

    @property
    def session(self):
        from database import get_db
        return get_db()

    _ESTADOS_PROTEGIDOS = frozenset({'en_pausa', 'desconectado'})

    def _actualizar_estado_operativo(self, empleado_id: int, nuevo_estado: str) -> None:
        """Actualiza estado_operativo solo si el estado actual no está protegido.

        Los estados en_pausa y desconectado son manuales — el sistema no los sobreescribe.
        Llamar DESPUÉS del commit de la operación principal, dentro del mismo request.
        """
        if not empleado_id:
            return
        try:
            empleado = self.session.query(Empleado).filter_by(EmpleadoID=empleado_id).first()
            if empleado and empleado.estado_operativo not in self._ESTADOS_PROTEGIDOS:
                empleado.estado_operativo = nuevo_estado
                self.session.commit()
        except Exception as e:
            logger.warning("No se pudo actualizar estado_operativo de empleado %s: %s", empleado_id, e)

    # -------------------------------------------------------------------------
    # Read methods
    # -------------------------------------------------------------------------

    def metricas(self) -> dict:
        hoy = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        s = self.session

        pedidos_hoy = s.query(func.count(Pedido.PedidoID)).filter(
            Pedido.FechaCreacion >= hoy
        ).scalar() or 0

        pedidos_activos = s.query(func.count(Pedido.PedidoID)).filter(
            Pedido.Estado.in_(_ESTADOS_OPERATIVOS)
        ).scalar() or 0

        en_preparacion = s.query(func.count(Pedido.PedidoID)).filter(
            Pedido.Estado == EstadoPedido.EN_PREPARACION.value
        ).scalar() or 0

        en_reparto = s.query(func.count(Pedido.PedidoID)).filter(
            Pedido.Estado == EstadoPedido.EN_REPARTO.value
        ).scalar() or 0

        entregados_hoy = s.query(func.count(Pedido.PedidoID)).filter(
            Pedido.Estado == EstadoPedido.ENTREGADO.value,
            Pedido.FechaActualizacion >= hoy,
        ).scalar() or 0

        pickers_activos = s.query(func.count(PickingPedido.id)).filter(
            PickingPedido.estado == EstadoPicking.EN_PROCESO.value
        ).scalar() or 0

        repartidores_activos = s.query(func.count(Reparto.id)).filter(
            Reparto.estado == EstadoReparto.EN_CAMINO.value
        ).scalar() or 0

        ingresos_hoy = s.query(func.sum(Pedido.Total)).filter(
            Pedido.FechaCreacion >= hoy,
            Pedido.Estado.in_(_ESTADOS_OPERATIVOS + [EstadoPedido.ENTREGADO.value]),
        ).scalar() or Decimal("0.00")

        # Cancelaciones hoy agrupadas por motivo
        cancelados_hoy = (
            s.query(Pedido.cancel_reason, func.count(Pedido.PedidoID))
            .filter(
                Pedido.Estado == EstadoPedido.CANCELADO.value,
                Pedido.FechaActualizacion >= hoy,
            )
            .group_by(Pedido.cancel_reason)
            .all()
        )
        cancelaciones_hoy = {(m or 'sin_motivo'): c for m, c in cancelados_hoy}

        # Ingresos por método de cobro hoy (repartos entregados hoy)
        ingresos_metodo = (
            s.query(Reparto.metodo_cobro, func.sum(Reparto.importe_cobrado))
            .filter(
                Reparto.estado == EstadoReparto.ENTREGADO.value,
                Reparto.hora_entrega_real >= hoy,
            )
            .group_by(Reparto.metodo_cobro)
            .all()
        )
        ingresos_por_metodo = {
            (m or 'online'): float(v or 0) for m, v in ingresos_metodo
        }

        return {
            "pedidos_hoy": pedidos_hoy,
            "pedidos_activos": pedidos_activos,
            "en_preparacion": en_preparacion,
            "en_reparto": en_reparto,
            "entregados_hoy": entregados_hoy,
            "pickers_activos": pickers_activos,
            "repartidores_activos": repartidores_activos,
            "tiempo_medio_preparacion_min": self._tiempo_medio(
                hoy, EstadoPedido.EN_PREPARACION, EstadoPedido.PREPARADO
            ),
            "tiempo_medio_entrega_min": self._tiempo_medio(
                hoy, EstadoPedido.EN_REPARTO, EstadoPedido.ENTREGADO
            ),
            "ingresos_hoy_eur": float(ingresos_hoy),
            "cancelaciones_hoy": cancelaciones_hoy,
            "ingresos_por_metodo": ingresos_por_metodo,
        }

    def _tiempo_medio(self, desde: datetime, estado_inicio: EstadoPedido, estado_fin: EstadoPedido):
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

    def pedidos_activos(self, estado: str = None) -> list:
        s = self.session
        ahora = datetime.utcnow()

        query = s.query(Pedido).filter(Pedido.Estado.in_(_ESTADOS_OPERATIVOS))
        if estado:
            query = query.filter(Pedido.Estado == estado)
        pedidos = query.order_by(Pedido.FechaCreacion.asc()).all()

        resultado = []
        for p in pedidos:
            minutos = int((ahora - p.FechaCreacion).total_seconds() / 60) if p.FechaCreacion else None
            ref = p.FechaActualizacion or p.FechaCreacion
            minutos_en_estado = int((ahora - ref).total_seconds() / 60) if ref else None

            picking_data = None
            if p.picking:
                picking_data = {
                    "id": p.picking.id,
                    "estado": p.picking.estado,
                    "picker_nombre": (
                        f"{p.picking.empleado.Nombre} {p.picking.empleado.Apellido}"
                        if p.picking.empleado else None
                    ),
                    "asignado_en": _iso(p.picking.created_at),
                    "iniciado_en": _iso(p.picking.iniciado_en),
                    "completado_en": _iso(p.picking.completado_en),
                }

            reparto_data = None
            if p.reparto:
                reparto_data = {
                    "id": p.reparto.id,
                    "estado": p.reparto.estado,
                    "repartidor_nombre": (
                        f"{p.reparto.repartidor.Nombre} {p.reparto.repartidor.Apellido}"
                        if p.reparto.repartidor else None
                    ),
                    "repartidor_telefono": (
                        p.reparto.repartidor.Telefono if p.reparto.repartidor else None
                    ),
                    "asignado_en": _iso(p.reparto.created_at),
                    "hora_salida": _iso(p.reparto.hora_salida),
                    "hora_estimada_entrega": _iso(p.reparto.hora_estimada_entrega),
                }

            umbral_info = _UMBRALES_RETRASO.get(p.Estado)
            es_alerta = bool(umbral_info and minutos_en_estado and minutos_en_estado > umbral_info[0])

            resultado.append({
                "pedido_id": p.PedidoID,
                "cliente_nombre": p.cliente.nombre if p.cliente else "—",
                "cliente_telefono": p.TelefonoEntrega,
                "direccion_entrega": p.DireccionEntrega,
                "estado": p.Estado,
                "forma_pago": p.forma_pago or "online",
                "total": float(p.Total) if p.Total else 0.0,
                "fecha_creacion": _iso(p.FechaCreacion),
                "minutos_activo": minutos,
                "minutos_en_estado": minutos_en_estado,
                "items": [
                    {
                        "detalle_id": d.DetalleID,
                        "nombre": d.NombreProducto or (d.producto.Nombre if d.producto else "—"),
                        "cantidad": d.Cantidad,
                        "precio_unitario": float(d.PrecioUnitario) if d.PrecioUnitario else 0.0,
                        "subtotal": float(d.Subtotal) if d.Subtotal else 0.0,
                    }
                    for d in p.detalles
                ],
                "lat": p.lat_entrega,
                "lng": p.lng_entrega,
                "picking": picking_data,
                "reparto": reparto_data,
                "es_alerta": es_alerta,
            })

        return resultado

    def picking_activo(self) -> list:
        s = self.session
        resultado = []

        # Orders ready for picking (pagado online o contra reembolso) sin picker asignado aún
        pickings_existentes_ids = [pk.pedido_id for pk in s.query(PickingPedido.pedido_id).all()]
        pagados_sin_picking = s.query(Pedido).filter(
            Pedido.Estado.in_(_ESTADOS_LISTOS_PARA_PICKING),
            ~Pedido.PedidoID.in_(pickings_existentes_ids) if pickings_existentes_ids else True,
        ).all()

        for p in pagados_sin_picking:
            items = [
                {
                    "detalle_id": d.DetalleID,
                    "nombre": d.NombreProducto or (d.producto.Nombre if d.producto else "—"),
                    "cantidad": d.Cantidad,
                    "ubicacion": d.producto.Ubicacion if d.producto else None,
                    "estado": "pendiente",
                    "cantidad_encontrada": None,
                }
                for d in p.detalles
            ]
            resultado.append({
                "tipo": "sin_asignar",
                "pedido_id": p.PedidoID,
                "picking_id": None,
                "estado_picking": None,
                "empleado": None,
                "items": items,
                "items_total": len(items),
                "items_pendientes": len(items),
                "items_completados": 0,
                "fecha_creacion": _iso(p.FechaCreacion),
            })

        # Active pickings — only those with a picker assigned
        pickings = s.query(PickingPedido).filter(
            PickingPedido.estado.in_([
                EstadoPicking.PENDIENTE.value,
                EstadoPicking.EN_PROCESO.value,
                EstadoPicking.CON_INCIDENCIAS.value,
            ]),
            PickingPedido.empleado_id != None,
        ).order_by(PickingPedido.created_at.asc()).all()

        for pk in pickings:
            items_data = []
            for item in pk.items:
                nombre = (item.pedido_detalle.NombreProducto if item.pedido_detalle else None)
                if not nombre and item.pedido_detalle and item.pedido_detalle.producto:
                    nombre = item.pedido_detalle.producto.Nombre
                ubicacion = (
                    item.pedido_detalle.producto.Ubicacion
                    if item.pedido_detalle and item.pedido_detalle.producto else None
                )
                items_data.append({
                    "item_id": item.id,
                    "detalle_id": item.pedido_detalle_id,
                    "nombre": nombre or "—",
                    "cantidad": item.pedido_detalle.Cantidad if item.pedido_detalle else 0,
                    "ubicacion": ubicacion,
                    "estado": item.estado,
                    "cantidad_encontrada": item.cantidad_encontrada,
                    "notas": item.notas,
                })

            pendientes = sum(1 for i in items_data if i["estado"] == "pendiente")
            completados = sum(1 for i in items_data if i["estado"] in ("encontrado", "sustituido"))

            empleado_data = None
            if pk.empleado:
                empleado_data = {
                    "id": pk.empleado.EmpleadoID,
                    "nombre": f"{pk.empleado.Nombre} {pk.empleado.Apellido}",
                }

            resultado.append({
                "tipo": "activo",
                "pedido_id": pk.pedido_id,
                "picking_id": pk.id,
                "estado_picking": pk.estado,
                "empleado": empleado_data,
                "items": items_data,
                "items_total": len(items_data),
                "items_pendientes": pendientes,
                "items_completados": completados,
                "iniciado_en": _iso(pk.iniciado_en),
                "fecha_creacion": _iso(pk.created_at),
                "cliente_nombre": pk.pedido.cliente.nombre if pk.pedido and pk.pedido.cliente else "—",
                "direccion_entrega": pk.pedido.DireccionEntrega if pk.pedido else None,
                "total": float(pk.pedido.Total) if pk.pedido and pk.pedido.Total else 0,
                "estado_pedido": pk.pedido.Estado if pk.pedido else None,
                "asignado_en": _iso(pk.created_at),
                "notas": pk.notas,
            })

        # Sin picker: PickingPedido exists (estado=PENDIENTE, empleado_id=NULL)
        sin_picker_qs = (
            s.query(PickingPedido)
            .filter(
                PickingPedido.estado == EstadoPicking.PENDIENTE.value,
                PickingPedido.empleado_id == None,
            )
            .all()
        )

        for pk in sin_picker_qs:
            items_data = []
            for item in pk.items:
                nombre = (item.pedido_detalle.NombreProducto if item.pedido_detalle else None)
                if not nombre and item.pedido_detalle and item.pedido_detalle.producto:
                    nombre = item.pedido_detalle.producto.Nombre
                ubicacion = (
                    item.pedido_detalle.producto.Ubicacion
                    if item.pedido_detalle and item.pedido_detalle.producto else None
                )
                items_data.append({
                    "item_id": item.id,
                    "detalle_id": item.pedido_detalle_id,
                    "nombre": nombre or "—",
                    "cantidad": item.pedido_detalle.Cantidad if item.pedido_detalle else 0,
                    "ubicacion": ubicacion,
                    "estado": item.estado,
                    "cantidad_encontrada": item.cantidad_encontrada,
                    "notas": item.notas,
                })

            pendientes = sum(1 for i in items_data if i["estado"] == "pendiente")
            completados = sum(1 for i in items_data if i["estado"] in ("encontrado", "sustituido"))

            resultado.append({
                "tipo": "sin_picker",
                "pedido_id": pk.pedido_id,
                "picking_id": pk.id,
                "estado_picking": pk.estado,
                "empleado": None,
                "items": items_data,
                "items_total": len(items_data),
                "items_pendientes": pendientes,
                "items_completados": completados,
                "iniciado_en": _iso(pk.iniciado_en),
                "fecha_creacion": _iso(pk.created_at),
                "cliente_nombre": pk.pedido.cliente.nombre if pk.pedido and pk.pedido.cliente else "—",
                "direccion_entrega": pk.pedido.DireccionEntrega if pk.pedido else None,
                "total": float(pk.pedido.Total) if pk.pedido and pk.pedido.Total else 0,
                "estado_pedido": pk.pedido.Estado if pk.pedido else None,
                "asignado_en": None,
                "notas": pk.notas,
            })

        return resultado

    def repartidores(self) -> dict:
        s = self.session
        hoy = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        empleados = s.query(Empleado).filter(Empleado.activo == True).all()

        repartos_asignados_ids = [r.pedido_id for r in s.query(Reparto.pedido_id).all()]
        preparados_sin_reparto = s.query(Pedido).filter(
            Pedido.Estado == EstadoPedido.PREPARADO.value,
            ~Pedido.PedidoID.in_(repartos_asignados_ids) if repartos_asignados_ids else True,
        ).all()

        lista_empleados = []
        for e in empleados:
            repartos_activos = s.query(Reparto).filter(
                Reparto.repartidor_id == e.EmpleadoID,
                Reparto.estado.in_([EstadoReparto.ASIGNADO.value, EstadoReparto.EN_CAMINO.value]),
            ).all()

            entregados_hoy = s.query(func.count(Reparto.id)).filter(
                Reparto.repartidor_id == e.EmpleadoID,
                Reparto.estado == EstadoReparto.ENTREGADO.value,
                Reparto.hora_entrega_real >= hoy,
            ).scalar() or 0

            pedidos_activos_data = [
                {
                    "reparto_id": r.id,
                    "pedido_id": r.pedido_id,
                    "estado_reparto": r.estado,
                    "direccion": r.pedido.DireccionEntrega if r.pedido else "—",
                    "hora_salida": _iso(r.hora_salida),
                    "hora_estimada_entrega": (
                        _iso(r.hora_estimada_entrega)
                    ),
                    "total": float(r.pedido.Total) if r.pedido and r.pedido.Total else 0.0,
                }
                for r in repartos_activos
            ]

            lista_empleados.append({
                "empleado_id": e.EmpleadoID,
                "nombre": f"{e.Nombre} {e.Apellido}",
                "telefono": e.Telefono,
                "activo": e.activo,
                "rol": e.rol.nombre if e.rol else e.Puesto,
                "pedidos_activos": pedidos_activos_data,
                "entregados_hoy": entregados_hoy,
            })

        return {
            "empleados": lista_empleados,
            "pedidos_sin_asignar": [
                {
                    "pedido_id": p.PedidoID,
                    "direccion": p.DireccionEntrega,
                    "total": float(p.Total) if p.Total else 0.0,
                    "fecha_creacion": _iso(p.FechaCreacion),
                }
                for p in preparados_sin_reparto
            ],
        }

    def alertas(self) -> list:
        s = self.session
        ahora = datetime.utcnow()
        resultado = []

        for estado, (umbral, nivel, desc) in _UMBRALES_RETRASO.items():
            pedidos = s.query(Pedido).filter(Pedido.Estado == estado).all()
            for p in pedidos:
                ref = p.FechaActualizacion or p.FechaCreacion
                if ref:
                    minutos = (ahora - ref).total_seconds() / 60
                    if minutos > umbral:
                        resultado.append({
                            "tipo": "pedido_retrasado",
                            "nivel": nivel,
                            "pedido_id": p.PedidoID,
                            "mensaje": f"Pedido #{p.PedidoID} lleva {int(minutos)}min {desc}",
                            "minutos": int(minutos),
                            "creada_en": _iso(ahora),
                        })

        # Prepared orders with no delivery driver
        repartos_asignados_ids = [r.pedido_id for r in s.query(Reparto.pedido_id).all()]
        for p in s.query(Pedido).filter(
            Pedido.Estado == EstadoPedido.PREPARADO.value,
            ~Pedido.PedidoID.in_(repartos_asignados_ids) if repartos_asignados_ids else True,
        ).all():
            resultado.append({
                "tipo": "sin_repartidor",
                "nivel": "error",
                "pedido_id": p.PedidoID,
                "mensaje": f"Pedido #{p.PedidoID} preparado pero sin repartidor asignado",
                "creada_en": _iso(ahora),
            })

        # Low stock
        for prod in s.query(Producto).filter(Producto.Stock < 5, Producto.Disponible == True).all():
            resultado.append({
                "tipo": "stock_bajo",
                "nivel": "info" if prod.Stock > 0 else "warning",
                "producto_id": prod.ProductoID,
                "mensaje": f"'{prod.Nombre}' — Stock: {prod.Stock} unidades",
                "creada_en": _iso(ahora),
            })

        nivel_orden = {"error": 0, "warning": 1, "info": 2}
        resultado.sort(key=lambda x: nivel_orden.get(x["nivel"], 3))
        return resultado

    def eventos(self, limit: int = 50) -> list:
        eventos = (
            self.session.query(HistorialEstadoPedido)
            .order_by(HistorialEstadoPedido.cambiado_en.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": e.id,
                "timestamp": _iso(e.cambiado_en),
                "pedido_id": e.pedido_id,
                "estado_anterior": e.estado_anterior,
                "estado_nuevo": e.estado_nuevo,
                "notas": e.notas,
            }
            for e in eventos
        ]

    def mapa(self) -> dict:
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

    def buscar_productos(self, q: str = '') -> list:
        """Returns products for substitute selection in the dashboard."""
        query = self.session.query(Producto).filter(Producto.Disponible == True)
        if q:
            query = query.filter(Producto.Nombre.contains(q))
        return [
            {
                "id": p.ProductoID,
                "nombre": p.Nombre,
                "precio": float(p.Precio),
                "stock": p.Stock,
            }
            for p in query.order_by(Producto.Nombre).limit(20).all()
        ]

    def empleados_disponibles(self, rol: str = None) -> list:
        query = self.session.query(Empleado).filter(Empleado.activo == True)
        if rol:
            query = query.join(Rol, Empleado.rol_id == Rol.id).filter(Rol.nombre == rol)
        return [
            {
                "id": e.EmpleadoID,
                "nombre": f"{e.Nombre} {e.Apellido}",
                "telefono": e.Telefono,
                "rol": e.rol.nombre if e.rol else e.Puesto,
            }
            for e in query.order_by(Empleado.Nombre).all()
        ]

    def monitor_empleados(self) -> dict:
        """Aggregated real-time data for the operations monitoring dashboard."""
        s = self.session
        ahora = datetime.utcnow()
        hoy = ahora.replace(hour=0, minute=0, second=0, microsecond=0)

        estados_activos_picking = [
            EstadoPicking.PENDIENTE.value,
            EstadoPicking.EN_PROCESO.value,
            EstadoPicking.CON_INCIDENCIAS.value,
        ]
        estados_activos_reparto = [EstadoReparto.ASIGNADO.value, EstadoReparto.EN_CAMINO.value]

        empleados = s.query(Empleado).filter(Empleado.activo == True).order_by(Empleado.Nombre).all()

        pickers_data = []
        repartidores_data = []

        for e in empleados:
            nombre_rol = (e.rol.nombre.lower() if e.rol else (e.Puesto or "").lower())
            es_picker = "picker" in nombre_rol
            es_repartidor = "repartidor" in nombre_rol or "reparto" in nombre_rol

            # If rol doesn't say clearly, infer from activity
            if not es_picker and not es_repartidor:
                tiene_picking = s.query(PickingPedido.id).filter(
                    PickingPedido.empleado_id == e.EmpleadoID
                ).first()
                tiene_reparto = s.query(Reparto.id).filter(
                    Reparto.repartidor_id == e.EmpleadoID
                ).first()
                es_picker = bool(tiene_picking)
                es_repartidor = bool(tiene_reparto)

            # ── PICKER ────────────────────────────────────────────────────────
            if es_picker:
                pickings_activos = s.query(PickingPedido).filter(
                    PickingPedido.empleado_id == e.EmpleadoID,
                    PickingPedido.estado.in_(estados_activos_picking),
                ).order_by(PickingPedido.created_at.asc()).all()

                completados_hoy = s.query(PickingPedido).filter(
                    PickingPedido.empleado_id == e.EmpleadoID,
                    PickingPedido.estado == EstadoPicking.COMPLETADO.value,
                    PickingPedido.completado_en >= hoy,
                ).all()

                # Avg picking time (min)
                tiempos = [
                    (pk.completado_en - pk.iniciado_en).total_seconds() / 60
                    for pk in completados_hoy
                    if pk.iniciado_en and pk.completado_en
                ]
                tiempo_medio = round(sum(tiempos) / len(tiempos)) if tiempos else None

                # Incidents today (sin_stock + sustituido items)
                ids_picking_hoy = (
                    [pk.id for pk in completados_hoy] + [pk.id for pk in pickings_activos]
                )
                incidencias_hoy = 0
                if ids_picking_hoy:
                    incidencias_hoy = s.query(func.count(PickingItem.id)).filter(
                        PickingItem.picking_id.in_(ids_picking_hoy),
                        PickingItem.estado.in_(["sin_stock", "sustituido"]),
                    ).scalar() or 0

                # Current picking detail
                pickings_activos_data = []
                for pk in pickings_activos:
                    total_items = len(pk.items)
                    completados_items = sum(
                        1 for i in pk.items if i.estado in ("encontrado", "sustituido")
                    )
                    sin_stock_items = sum(1 for i in pk.items if i.estado == "sin_stock")
                    minutos_activo = (
                        int((ahora - pk.iniciado_en).total_seconds() / 60)
                        if pk.iniciado_en else None
                    )
                    pickings_activos_data.append({
                        "picking_id": pk.id,
                        "pedido_id": pk.pedido_id,
                        "estado": pk.estado,
                        "iniciado_en": _iso(pk.iniciado_en),
                        "minutos_activo": minutos_activo,
                        "items_total": total_items,
                        "items_completados": completados_items,
                        "items_sin_stock": sin_stock_items,
                        "progreso_pct": (
                            round(completados_items / total_items * 100) if total_items else 0
                        ),
                    })

                # Status
                n_activos = len(pickings_activos)
                if n_activos >= 3:
                    estado = "sobrecargado"
                elif n_activos >= 1:
                    estado = "activo"
                elif completados_hoy:
                    estado = "inactivo"
                else:
                    estado = "sin_carga"

                # Last activity
                todos_pk = pickings_activos + completados_hoy
                ultima_actividad = None
                if todos_pk:
                    ts_vals = [
                        pk.completado_en or pk.iniciado_en or pk.created_at
                        for pk in todos_pk
                        if pk.completado_en or pk.iniciado_en or pk.created_at
                    ]
                    ultima_actividad = max(ts_vals) if ts_vals else None

                rendimiento = None
                if tiempo_medio is not None:
                    rendimiento = "rapido" if tiempo_medio < 15 else ("lento" if tiempo_medio > 30 else "normal")

                historial_picker = []
                for pk in sorted(completados_hoy, key=lambda x: x.completado_en or x.created_at, reverse=True):
                    dur = None
                    if pk.iniciado_en and pk.completado_en:
                        dur = int((pk.completado_en - pk.iniciado_en).total_seconds() / 60)
                    historial_picker.append({
                        "pedido_id": pk.pedido_id,
                        "completado_en": _iso(pk.completado_en),
                        "duracion_min": dur,
                    })

                pickers_data.append({
                    "empleado_id": e.EmpleadoID,
                    "nombre": f"{e.Nombre} {e.Apellido}",
                    "telefono": e.Telefono,
                    "estado": estado,
                    "estado_operativo": e.estado_operativo,
                    "pedidos_activos": n_activos,
                    "completados_hoy": len(completados_hoy),
                    "pickings_activos": pickings_activos_data,
                    "historial_hoy": historial_picker,
                    "tiempo_medio_min": tiempo_medio,
                    "ultima_actividad": _iso(ultima_actividad),
                    "incidencias_hoy": incidencias_hoy,
                    "rendimiento": rendimiento,
                })

            # ── REPARTIDOR ────────────────────────────────────────────────────
            if es_repartidor:
                repartos_activos = s.query(Reparto).filter(
                    Reparto.repartidor_id == e.EmpleadoID,
                    Reparto.estado.in_(estados_activos_reparto),
                ).all()

                entregados_hoy = s.query(Reparto).filter(
                    Reparto.repartidor_id == e.EmpleadoID,
                    Reparto.estado == EstadoReparto.ENTREGADO.value,
                    Reparto.hora_entrega_real >= hoy,
                ).all()

                # Avg delivery time
                tiempos = [
                    (r.hora_entrega_real - r.hora_salida).total_seconds() / 60
                    for r in entregados_hoy
                    if r.hora_salida and r.hora_entrega_real
                ]
                tiempo_medio = round(sum(tiempos) / len(tiempos)) if tiempos else None

                # All active deliveries
                entregas_activas = []
                for r in sorted(repartos_activos, key=lambda x: x.hora_salida or x.created_at or ahora, reverse=True):
                    minutos_en_ruta = (
                        int((ahora - r.hora_salida).total_seconds() / 60)
                        if r.hora_salida else None
                    )
                    entregas_activas.append({
                        "reparto_id": r.id,
                        "pedido_id": r.pedido_id,
                        "estado": r.estado,
                        "hora_salida": _iso(r.hora_salida),
                        "minutos_en_ruta": minutos_en_ruta,
                        "direccion": r.pedido.DireccionEntrega if r.pedido else "—",
                        "total": float(r.pedido.Total) if r.pedido and r.pedido.Total else 0.0,
                        "forma_pago": r.pedido.forma_pago if r.pedido else None,
                    })

                # Idle time
                tiempo_inactivo_min = None
                if not repartos_activos and entregados_hoy:
                    ultimo = max(entregados_hoy, key=lambda r: r.hora_entrega_real or r.created_at)
                    ref = ultimo.hora_entrega_real or ultimo.created_at
                    if ref:
                        tiempo_inactivo_min = int((ahora - ref).total_seconds() / 60)

                # Status
                n_activos = len(repartos_activos)
                if n_activos >= 3:
                    estado = "sobrecargado"
                elif n_activos >= 1:
                    estado = "activo"
                elif entregados_hoy:
                    estado = "inactivo"
                else:
                    estado = "sin_carga"

                # Last activity
                todos_r = repartos_activos + entregados_hoy
                ultima_actividad = None
                if todos_r:
                    ts_vals = [
                        r.hora_entrega_real or r.hora_salida or r.created_at
                        for r in todos_r
                        if r.hora_entrega_real or r.hora_salida or r.created_at
                    ]
                    ultima_actividad = max(ts_vals) if ts_vals else None

                rendimiento = None
                if tiempo_medio is not None:
                    rendimiento = "rapido" if tiempo_medio < 20 else ("lento" if tiempo_medio > 40 else "normal")

                carga = "alta" if n_activos >= 3 else ("media" if n_activos == 2 else "ligera")

                historial_repartidor = []
                for r in sorted(entregados_hoy, key=lambda x: x.hora_entrega_real or x.created_at, reverse=True):
                    dur = None
                    if r.hora_salida and r.hora_entrega_real:
                        dur = int((r.hora_entrega_real - r.hora_salida).total_seconds() / 60)
                    historial_repartidor.append({
                        "pedido_id": r.pedido_id,
                        "entregado_en": _iso(r.hora_entrega_real),
                        "duracion_min": dur,
                        "total": float(r.pedido.Total) if r.pedido and r.pedido.Total else 0.0,
                        "forma_pago": r.pedido.forma_pago if r.pedido else None,
                    })

                repartidores_data.append({
                    "empleado_id": e.EmpleadoID,
                    "nombre": f"{e.Nombre} {e.Apellido}",
                    "telefono": e.Telefono,
                    "estado": estado,
                    "estado_operativo": e.estado_operativo,
                    "pedidos_activos": n_activos,
                    "entregados_hoy": len(entregados_hoy),
                    "entregas_activas": entregas_activas,
                    "historial_hoy": historial_repartidor,
                    "tiempo_medio_min": tiempo_medio,
                    "tiempo_inactivo_min": tiempo_inactivo_min,
                    "ultima_actividad": _iso(ultima_actividad),
                    "rendimiento": rendimiento,
                    "carga": carga,
                })

        # Pipeline counts
        pipeline = {}
        estados_pipeline = [
            EstadoPedido.PAGADO.value,
            EstadoPedido.CONTRA_REEMBOLSO.value,
            EstadoPedido.EN_PREPARACION.value,
            EstadoPedido.PREPARADO.value,
            EstadoPedido.EN_REPARTO.value,
        ]
        for estado_val in estados_pipeline:
            pipeline[estado_val] = s.query(func.count(Pedido.PedidoID)).filter(
                Pedido.Estado == estado_val
            ).scalar() or 0
        pipeline[EstadoPedido.ENTREGADO.value] = s.query(func.count(Pedido.PedidoID)).filter(
            Pedido.Estado == EstadoPedido.ENTREGADO.value,
            Pedido.FechaActualizacion >= hoy,
        ).scalar() or 0

        incidencias_abiertas = s.query(func.count(Incidencia.id)).filter(
            Incidencia.estado.in_(["abierta", "en_proceso"])
        ).scalar() or 0

        # Orders waiting for a picker (pagado / contra-reembolso, no picking assigned yet)
        picking_ids_asignados = [pk.pedido_id for pk in s.query(PickingPedido.pedido_id).all()]
        sin_picker = s.query(Pedido).filter(
            Pedido.Estado.in_(_ESTADOS_LISTOS_PARA_PICKING),
            ~Pedido.PedidoID.in_(picking_ids_asignados) if picking_ids_asignados else True,
        ).order_by(Pedido.FechaCreacion.asc()).all()

        pedidos_sin_picker = [
            {
                "pedido_id": p.PedidoID,
                "cliente_nombre": p.cliente.nombre if p.cliente else "—",
                "total": float(p.Total) if p.Total else 0.0,
                "forma_pago": p.forma_pago or "online",
                "fecha_creacion": _iso(p.FechaCreacion),
                "minutos_espera": int((ahora - p.FechaCreacion).total_seconds() / 60) if p.FechaCreacion else None,
                "n_items": len(p.detalles),
            }
            for p in sin_picker
        ]

        # Orders ready (preparado) with no rider assigned yet
        reparto_ids_asignados = [r.pedido_id for r in s.query(Reparto.pedido_id).all()]
        sin_repartidor = s.query(Pedido).filter(
            Pedido.Estado == EstadoPedido.PREPARADO.value,
            ~Pedido.PedidoID.in_(reparto_ids_asignados) if reparto_ids_asignados else True,
        ).order_by(Pedido.FechaCreacion.asc()).all()

        pedidos_sin_repartidor = [
            {
                "pedido_id": p.PedidoID,
                "cliente_nombre": p.cliente.nombre if p.cliente else "—",
                "direccion": p.DireccionEntrega,
                "total": float(p.Total) if p.Total else 0.0,
                "forma_pago": p.forma_pago or "online",
                "fecha_creacion": _iso(p.FechaCreacion),
                "minutos_espera": int((ahora - p.FechaCreacion).total_seconds() / 60) if p.FechaCreacion else None,
            }
            for p in sin_repartidor
        ]

        return {
            "pickers": pickers_data,
            "repartidores": repartidores_data,
            "pipeline": pipeline,
            "pedidos_sin_picker": pedidos_sin_picker,
            "pedidos_sin_repartidor": pedidos_sin_repartidor,
            "incidencias_abiertas": incidencias_abiertas,
            "ts": _iso(ahora),
        }

    # -------------------------------------------------------------------------
    # Write methods
    # -------------------------------------------------------------------------

    def asignar_picker(self, pedido_id: int, empleado_id: int) -> tuple:
        s = self.session
        try:
            pedido = s.query(Pedido).filter_by(PedidoID=pedido_id).first()
            if not pedido:
                return False, "Pedido no encontrado"
            if pedido.Estado not in _ESTADOS_LISTOS_PARA_PICKING:
                return False, f"Estado actual '{pedido.Estado}' no permite asignar picking"

            empleado = s.query(Empleado).filter_by(EmpleadoID=empleado_id, activo=True).first()
            if not empleado:
                return False, "Empleado no encontrado o inactivo"

            picking = s.query(PickingPedido).filter_by(pedido_id=pedido_id).first()
            if picking:
                picking.empleado_id = empleado_id
                picking.estado = EstadoPicking.EN_PROCESO.value
                picking.iniciado_en = datetime.utcnow()
            else:
                picking = PickingPedido(
                    pedido_id=pedido_id,
                    empleado_id=empleado_id,
                    estado=EstadoPicking.EN_PROCESO.value,
                    iniciado_en=datetime.utcnow(),
                )
                s.add(picking)
                s.flush()
                for detalle in pedido.detalles:
                    s.add(PickingItem(
                        picking_id=picking.id,
                        pedido_detalle_id=detalle.DetalleID,
                        estado="pendiente",
                    ))

            if transicion_valida_pedido(pedido.Estado, EstadoPedido.EN_PREPARACION.value):
                estado_anterior = pedido.Estado
                pedido.Estado = EstadoPedido.EN_PREPARACION.value
                s.add(HistorialEstadoPedido(
                    pedido_id=pedido_id,
                    estado_anterior=estado_anterior,
                    estado_nuevo=EstadoPedido.EN_PREPARACION.value,
                    notas=f"Picking iniciado — picker #{empleado_id}",
                ))

            s.commit()
            self._actualizar_estado_operativo(empleado_id, 'ocupado')
            return True, "Picker asignado correctamente"
        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error asignando picker para pedido %s: %s", pedido_id, e)
            return False, "Error de base de datos"

    def reasignar_picker(self, picking_id: int, nuevo_empleado_id: int | None) -> tuple:
        s = self.session
        _ESTADOS_REASIGNABLES = {
            EstadoPicking.PENDIENTE.value,
            EstadoPicking.EN_PROCESO.value,
            EstadoPicking.CON_INCIDENCIAS.value,
        }
        try:
            picking = s.query(PickingPedido).filter_by(id=picking_id).first()
            if not picking:
                return False, "Picking no encontrado"

            if picking.estado not in _ESTADOS_REASIGNABLES:
                return False, f"No se puede reasignar un picking en estado '{picking.estado}'"

            if nuevo_empleado_id is not None:
                empleado = s.query(Empleado).filter_by(EmpleadoID=nuevo_empleado_id, activo=True).first()
                if not empleado:
                    return False, "Empleado no válido o inactivo"

            if nuevo_empleado_id == picking.empleado_id:
                return False, "El picker ya está asignado a este pedido"

            anterior_nombre = (
                f"{picking.empleado.Nombre} {picking.empleado.Apellido}"
                if picking.empleado else "sin asignar"
            )
            if nuevo_empleado_id is not None:
                nuevo_empleado = s.query(Empleado).filter_by(EmpleadoID=nuevo_empleado_id).first()
                nuevo_nombre = f"{nuevo_empleado.Nombre} {nuevo_empleado.Apellido}"
            else:
                nuevo_nombre = "sin asignar"

            timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
            entrada_log = f"[{timestamp}] {anterior_nombre} → {nuevo_nombre}"
            picking.notas = (picking.notas + "\n" + entrada_log).strip() if picking.notas else entrada_log

            picking.empleado_id = nuevo_empleado_id
            picking.estado = EstadoPicking.EN_PROCESO.value if nuevo_empleado_id else EstadoPicking.PENDIENTE.value

            s.commit()
            if nuevo_empleado_id:
                return True, "Picker reasignado correctamente"
            return True, "Picker eliminado del picking"
        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error reasignando picker para picking %s: %s", picking_id, e)
            return False, "Error interno"

    def completar_picking(self, picking_id: int, picker_id: int | None = None) -> tuple:
        """Returns (ok, msg, telefono_cliente). telefono_cliente is None on error."""
        s = self.session
        try:
            picking = s.query(PickingPedido).filter_by(id=picking_id).first()
            if not picking:
                return False, "Picking no encontrado", None

            if picker_id is not None and picking.empleado_id != picker_id:
                return False, "Este picking fue reasignado a otro picker", None

            picking.estado = EstadoPicking.COMPLETADO.value
            picking.completado_en = datetime.utcnow()

            pedido = picking.pedido
            if pedido and transicion_valida_pedido(pedido.Estado, EstadoPedido.PREPARADO.value):
                estado_anterior = pedido.Estado
                pedido.Estado = EstadoPedido.PREPARADO.value
                s.add(HistorialEstadoPedido(
                    pedido_id=pedido.PedidoID,
                    estado_anterior=estado_anterior,
                    estado_nuevo=EstadoPedido.PREPARADO.value,
                    notas="Picking completado",
                ))

            s.commit()

            # Descontar stock después del commit del picking
            items_para_stock = [
                {
                    "producto_id": item.pedido_detalle.ProductoID if item.pedido_detalle else None,
                    "cantidad_pedida": item.pedido_detalle.Cantidad if item.pedido_detalle else 0,
                    "cantidad_encontrada": item.cantidad_encontrada,
                    "estado": item.estado,
                }
                for item in picking.items
                if item.pedido_detalle and item.pedido_detalle.ProductoID
            ]
            if items_para_stock:
                from managers.gestor_productos import ProductoManager
                ProductoManager().descontar_stock_picking(items_para_stock)

            # Auto-actualizar estado: volver a disponible si no quedan pickings activos
            _picker_id = picking.empleado_id
            if _picker_id:
                _pickings_activos = s.query(PickingPedido).filter(
                    PickingPedido.empleado_id == _picker_id,
                    PickingPedido.estado.in_([
                        EstadoPicking.PENDIENTE.value,
                        EstadoPicking.EN_PROCESO.value,
                        EstadoPicking.CON_INCIDENCIAS.value,
                    ]),
                ).count()
                if _pickings_activos == 0:
                    self._actualizar_estado_operativo(_picker_id, 'disponible')

            telefono = pedido.TelefonoEntrega if pedido else None
            return True, "Picking completado", telefono
        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error completando picking %s: %s", picking_id, e)
            return False, "Error de base de datos", None

    def asignar_repartidor(self, pedido_id: int, empleado_id: int) -> tuple:
        s = self.session
        try:
            pedido = s.query(Pedido).filter_by(PedidoID=pedido_id).first()
            if not pedido:
                return False, "Pedido no encontrado"
            if pedido.Estado != EstadoPedido.PREPARADO.value:
                return False, f"Estado actual '{pedido.Estado}' no permite asignar reparto"

            empleado = s.query(Empleado).filter_by(EmpleadoID=empleado_id, activo=True).first()
            if not empleado:
                return False, "Empleado no encontrado o inactivo"

            reparto = s.query(Reparto).filter_by(pedido_id=pedido_id).first()
            if reparto:
                reparto.repartidor_id = empleado_id
                reparto.estado = EstadoReparto.ASIGNADO.value
            else:
                s.add(Reparto(
                    pedido_id=pedido_id,
                    repartidor_id=empleado_id,
                    estado=EstadoReparto.ASIGNADO.value,
                ))

            s.commit()
            self._actualizar_estado_operativo(empleado_id, 'ocupado')
            return True, "Repartidor asignado correctamente"
        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error asignando repartidor para pedido %s: %s", pedido_id, e)
            return False, "Error de base de datos"

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

    # -------------------------------------------------------------------------
    # Picker methods
    # -------------------------------------------------------------------------

    def pickings_del_picker(self, empleado_id: int) -> list:
        """Returns active pickings assigned to a specific picker."""
        s = self.session
        pickings = s.query(PickingPedido).filter(
            PickingPedido.empleado_id == empleado_id,
            PickingPedido.estado.in_([
                EstadoPicking.EN_PROCESO.value,
                EstadoPicking.CON_INCIDENCIAS.value,
            ]),
        ).order_by(PickingPedido.iniciado_en.asc()).all()

        resultado = []
        for pk in pickings:
            items_data = []
            for item in pk.items:
                nombre = item.pedido_detalle.NombreProducto if item.pedido_detalle else None
                if not nombre and item.pedido_detalle and item.pedido_detalle.producto:
                    nombre = item.pedido_detalle.producto.Nombre
                ubicacion = (
                    item.pedido_detalle.producto.Ubicacion
                    if item.pedido_detalle and item.pedido_detalle.producto else None
                )
                imagen = (
                    item.pedido_detalle.producto.ImagenURL
                    if item.pedido_detalle and item.pedido_detalle.producto else None
                )
                items_data.append({
                    "item_id": item.id,
                    "producto_id": item.pedido_detalle.ProductoID if item.pedido_detalle else None,
                    "nombre": nombre or "—",
                    "cantidad": item.pedido_detalle.Cantidad if item.pedido_detalle else 0,
                    "ubicacion": ubicacion,
                    "imagen": imagen,
                    "estado": item.estado,
                    "cantidad_encontrada": item.cantidad_encontrada,
                    "notas": item.notas,
                })

            pendientes = sum(1 for i in items_data if i["estado"] == "pendiente")
            listos = len(items_data) - pendientes
            resultado.append({
                "picking_id": pk.id,
                "pedido_id": pk.pedido_id,
                "estado": pk.estado,
                "direccion_entrega": pk.pedido.DireccionEntrega if pk.pedido else "—",
                "cliente_nombre": pk.pedido.cliente.nombre if pk.pedido and pk.pedido.cliente else "—",
                "cliente_telefono": pk.pedido.TelefonoEntrega if pk.pedido else None,
                "total": float(pk.pedido.Total) if pk.pedido and pk.pedido.Total else 0.0,
                "iniciado_en": _iso(pk.iniciado_en),
                "items": items_data,
                "items_total": len(items_data),
                "items_listos": listos,
                "items_pendientes": pendientes,
                "picking_completo": pendientes == 0 and len(items_data) > 0,
                "listo_para_finalizar": pendientes == 0,
            })
        return resultado

    # -------------------------------------------------------------------------
    # Repartidor methods
    # -------------------------------------------------------------------------

    def repartos_del_repartidor(self, empleado_id: int) -> list:
        """Returns active and recently delivered orders for a delivery driver."""
        s = self.session
        repartos = s.query(Reparto).filter(
            Reparto.repartidor_id == empleado_id,
            Reparto.estado.in_([
                EstadoReparto.ASIGNADO.value,
                EstadoReparto.EN_CAMINO.value,
                EstadoReparto.ENTREGADO.value,
                EstadoReparto.NO_ENTREGADO.value,
            ]),
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
                    "label": "Cobrar en efectivo",
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

    def actualizar_item_picking(self, item_id: int, estado: str, cantidad_encontrada: int = None, notas: str = None, producto_sustituto_id: int = None, picker_id: int | None = None) -> tuple:
        """Updates a single picking item state."""
        ESTADOS_VALIDOS = {"encontrado", "sin_stock", "sustituido", "pendiente"}
        if estado not in ESTADOS_VALIDOS:
            return False, f"Estado inválido. Válidos: {', '.join(ESTADOS_VALIDOS)}"

        s = self.session
        try:
            item = s.query(PickingItem).filter_by(id=item_id).first()
            if not item:
                return False, "Item no encontrado"

            if picker_id is not None and item.picking and item.picking.empleado_id != picker_id:
                return False, "Este picking fue reasignado a otro picker"

            item.estado = estado
            if cantidad_encontrada is not None:
                item.cantidad_encontrada = cantidad_encontrada
            if notas is not None:
                item.notas = notas
            if producto_sustituto_id is not None:
                from models import Producto
                prod = s.query(Producto).filter_by(ProductoID=producto_sustituto_id, Disponible=True).first()
                if not prod:
                    return False, "Producto sustituto no encontrado"
                item.producto_sustituto_id = producto_sustituto_id

            s.commit()
            return True, "Item actualizado"
        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error actualizando item %s: %s", item_id, e)
            return False, "Error de base de datos"

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

            # Auto-actualizar estado: volver a disponible si no quedan repartos activos
            _repartidor_id = reparto.repartidor_id
            if _repartidor_id:
                _repartos_activos = s.query(Reparto).filter(
                    Reparto.repartidor_id == _repartidor_id,
                    Reparto.estado.in_([
                        EstadoReparto.ASIGNADO.value,
                        EstadoReparto.EN_CAMINO.value,
                    ]),
                ).count()
                if _repartos_activos == 0:
                    self._actualizar_estado_operativo(_repartidor_id, 'disponible')

            telefono = pedido.TelefonoEntrega if pedido else None
            return True, "Pedido marcado como entregado", telefono
        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error marcando entregado reparto %s: %s", reparto_id, e)
            return False, "Error de base de datos", None

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

    def pickings_sin_asignar(self) -> list[dict]:
        """Pedidos con PickingPedido creado pero sin picker asignado.
        Solo incluye pedidos en estado activo (Pagado, contra_reembolso, en_preparacion).
        """
        s = self.session
        estados_activos = [
            EstadoPedido.PAGADO.value,
            EstadoPedido.CONTRA_REEMBOLSO.value,
            EstadoPedido.EN_PREPARACION.value,
        ]
        pickings = (
            s.query(PickingPedido)
            .join(Pedido, Pedido.PedidoID == PickingPedido.pedido_id)
            .filter(
                PickingPedido.empleado_id == None,
                PickingPedido.estado == EstadoPicking.PENDIENTE.value,
                Pedido.Estado.in_(estados_activos),
            )
            .order_by(PickingPedido.created_at.asc())
            .all()
        )
        ahora = datetime.utcnow()
        return [
            {
                'picking_id':         p.id,
                'pedido_id':          p.pedido_id,
                'n_items':            len(p.items),
                'segundos_esperando': int((ahora - p.created_at).total_seconds()),
            }
            for p in pickings
        ]

    def reclamar_picking(self, picking_id: int, empleado_id: int) -> tuple[bool, str]:
        """
        Asigna el picking al empleado de forma atómica y avanza el estado a EN_PROCESO.
        Nota: no transiciona el estado del Pedido padre — eso lo hace asignar_picker.
        Returns:
            (True,  'ok')            — asignado correctamente
            (False, 'no_encontrado') — picking_id no existe
            (False, 'ya_cogido')     — otro picker se adelantó (rowcount == 0)
            (False, 'error')         — error de BD
        """
        s = self.session
        try:
            # 1. Verificar existencia antes del UPDATE para dar error preciso
            picking = s.query(PickingPedido).filter_by(id=picking_id).first()
            if not picking:
                return False, 'no_encontrado'

            # 2. UPDATE atómico — solo actualiza si sigue libre
            resultado = (
                s.query(PickingPedido)
                .filter(
                    PickingPedido.id == picking_id,
                    PickingPedido.empleado_id == None,
                    PickingPedido.estado == EstadoPicking.PENDIENTE.value,
                )
                .update(
                    {
                        'empleado_id': empleado_id,
                        'estado': EstadoPicking.EN_PROCESO.value,
                        'iniciado_en': datetime.utcnow(),
                    },
                    synchronize_session=False,
                )
            )
            s.commit()

            if resultado == 0:
                return False, 'ya_cogido'

            # 3. Actualizar estado operativo del picker
            self._actualizar_estado_operativo(empleado_id, 'ocupado')
            return True, 'ok'

        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error reclamando picking %s: %s", picking_id, e)
            return False, 'error'
