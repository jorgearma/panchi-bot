import logging
from datetime import datetime
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

        # Active pickings
        pickings = s.query(PickingPedido).filter(
            PickingPedido.estado.in_([
                EstadoPicking.PENDIENTE.value,
                EstadoPicking.EN_PROCESO.value,
                EstadoPicking.CON_INCIDENCIAS.value,
            ])
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
            return True, "Picker asignado correctamente"
        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error asignando picker para pedido %s: %s", pedido_id, e)
            return False, "Error de base de datos"

    def completar_picking(self, picking_id: int) -> tuple:
        """Returns (ok, msg, telefono_cliente). telefono_cliente is None on error."""
        s = self.session
        try:
            picking = s.query(PickingPedido).filter_by(id=picking_id).first()
            if not picking:
                return False, "Picking no encontrado", None

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
                    "nombre": nombre or "—",
                    "cantidad": item.pedido_detalle.Cantidad if item.pedido_detalle else 0,
                    "ubicacion": ubicacion,
                    "imagen": imagen,
                    "estado": item.estado,
                    "cantidad_encontrada": item.cantidad_encontrada,
                    "notas": item.notas,
                })

            pendientes = sum(1 for i in items_data if i["estado"] == "pendiente")
            resultado.append({
                "picking_id": pk.id,
                "pedido_id": pk.pedido_id,
                "estado": pk.estado,
                "direccion_entrega": pk.pedido.DireccionEntrega if pk.pedido else "—",
                "cliente_nombre": pk.pedido.cliente.nombre if pk.pedido and pk.pedido.cliente else "—",
                "total": float(pk.pedido.Total) if pk.pedido and pk.pedido.Total else 0.0,
                "iniciado_en": _iso(pk.iniciado_en),
                "items": items_data,
                "items_total": len(items_data),
                "items_pendientes": pendientes,
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

    def actualizar_item_picking(self, item_id: int, estado: str, cantidad_encontrada: int = None, notas: str = None) -> tuple:
        """Updates a single picking item state."""
        ESTADOS_VALIDOS = {"encontrado", "sin_stock", "sustituido", "pendiente"}
        if estado not in ESTADOS_VALIDOS:
            return False, f"Estado inválido. Válidos: {', '.join(ESTADOS_VALIDOS)}"

        s = self.session
        try:
            item = s.query(PickingItem).filter_by(id=item_id).first()
            if not item:
                return False, "Item no encontrado"

            item.estado = estado
            if cantidad_encontrada is not None:
                item.cantidad_encontrada = cantidad_encontrada
            if notas is not None:
                item.notas = notas

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
            telefono = pedido.TelefonoEntrega if pedido else None
            return True, "Pedido marcado como entregado", telefono
        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error marcando entregado reparto %s: %s", reparto_id, e)
            return False, "Error de base de datos", None
