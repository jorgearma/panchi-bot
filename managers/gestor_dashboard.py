import logging
import random
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

# Tarancón coordinates (center)
_TARANCON_LAT = 40.0041
_TARANCON_LNG = -2.9980

_COLORES_ESTADO = {
    EstadoPedido.PAGADO.value: "#10b981",
    EstadoPedido.EN_PREPARACION.value: "#3b82f6",
    EstadoPedido.PREPARADO.value: "#6366f1",
    EstadoPedido.EN_REPARTO.value: "#f97316",
}

# Minutes before an order in a state is flagged as delayed
_UMBRALES_RETRASO = {
    EstadoPedido.PAGADO.value: (10, "warning", "pagado sin iniciar picking"),
    EstadoPedido.EN_PREPARACION.value: (30, "warning", "en preparación"),
    EstadoPedido.PREPARADO.value: (15, "error", "preparado sin repartidor"),
    EstadoPedido.EN_REPARTO.value: (60, "error", "en reparto"),
}

_ESTADOS_OPERATIVOS = [
    EstadoPedido.PAGADO.value,
    EstadoPedido.EN_PREPARACION.value,
    EstadoPedido.PREPARADO.value,
    EstadoPedido.EN_REPARTO.value,
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
                    "iniciado_en": p.picking.iniciado_en.isoformat() if p.picking.iniciado_en else None,
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
                    "hora_salida": p.reparto.hora_salida.isoformat() if p.reparto.hora_salida else None,
                }

            umbral_info = _UMBRALES_RETRASO.get(p.Estado)
            es_alerta = bool(umbral_info and minutos_en_estado and minutos_en_estado > umbral_info[0])

            resultado.append({
                "pedido_id": p.PedidoID,
                "cliente_nombre": p.cliente.nombre if p.cliente else "—",
                "cliente_telefono": p.TelefonoEntrega,
                "direccion_entrega": p.DireccionEntrega,
                "estado": p.Estado,
                "total": float(p.Total) if p.Total else 0.0,
                "fecha_creacion": p.FechaCreacion.isoformat() if p.FechaCreacion else None,
                "minutos_activo": minutos,
                "minutos_en_estado": minutos_en_estado,
                "picking": picking_data,
                "reparto": reparto_data,
                "es_alerta": es_alerta,
            })

        return resultado

    def picking_activo(self) -> list:
        s = self.session
        resultado = []

        # Orders paid but not yet assigned to a picker
        pickings_existentes_ids = [pk.pedido_id for pk in s.query(PickingPedido.pedido_id).all()]
        pagados_sin_picking = s.query(Pedido).filter(
            Pedido.Estado == EstadoPedido.PAGADO.value,
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
                "fecha_creacion": p.FechaCreacion.isoformat() if p.FechaCreacion else None,
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
                "iniciado_en": pk.iniciado_en.isoformat() if pk.iniciado_en else None,
                "fecha_creacion": pk.created_at.isoformat() if pk.created_at else None,
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
                    "hora_salida": r.hora_salida.isoformat() if r.hora_salida else None,
                    "hora_estimada_entrega": (
                        r.hora_estimada_entrega.isoformat() if r.hora_estimada_entrega else None
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
                    "fecha_creacion": p.FechaCreacion.isoformat() if p.FechaCreacion else None,
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
                            "creada_en": ahora.isoformat(),
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
                "creada_en": ahora.isoformat(),
            })

        # Low stock
        for prod in s.query(Producto).filter(Producto.Stock < 5, Producto.Disponible == True).all():
            resultado.append({
                "tipo": "stock_bajo",
                "nivel": "info" if prod.Stock > 0 else "warning",
                "producto_id": prod.ProductoID,
                "mensaje": f"'{prod.Nombre}' — Stock: {prod.Stock} unidades",
                "creada_en": ahora.isoformat(),
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
                "timestamp": e.cambiado_en.isoformat() if e.cambiado_en else None,
                "pedido_id": e.pedido_id,
                "estado_anterior": e.estado_anterior,
                "estado_nuevo": e.estado_nuevo,
                "notas": e.notas,
            }
            for e in eventos
        ]

    def mapa(self) -> dict:
        """Returns map data. Coordinates are simulated until real geocoding is added.
        TODO: Replace lat/lng generation with Google Maps Geocoding API using DireccionEntrega.
        """
        pedidos = self.session.query(Pedido).filter(
            Pedido.Estado.in_(_ESTADOS_OPERATIVOS)
        ).all()

        puntos = []
        for p in pedidos:
            # TODO: geocode p.DireccionEntrega via Google Maps
            lat = _TARANCON_LAT + random.uniform(-0.015, 0.015)
            lng = _TARANCON_LNG + random.uniform(-0.020, 0.020)
            puntos.append({
                "pedido_id": p.PedidoID,
                "estado": p.Estado,
                "direccion": p.DireccionEntrega,
                "lat": round(lat, 6),
                "lng": round(lng, 6),
                "color": _COLORES_ESTADO.get(p.Estado, "#6b7280"),
                "total": float(p.Total) if p.Total else 0.0,
                "simulado": True,
            })

        return {
            "centro": {"lat": _TARANCON_LAT, "lng": _TARANCON_LNG},
            "pedidos": puntos,
            "repartidores": [],  # TODO: add GPS tracking
        }

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
            if pedido.Estado != EstadoPedido.PAGADO.value:
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
        s = self.session
        try:
            picking = s.query(PickingPedido).filter_by(id=picking_id).first()
            if not picking:
                return False, "Picking no encontrado"

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
            return True, "Picking completado"
        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error completando picking %s: %s", picking_id, e)
            return False, "Error de base de datos"

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
        s = self.session
        try:
            reparto = s.query(Reparto).filter_by(id=reparto_id).first()
            if not reparto:
                return False, "Reparto no encontrado"

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
            return True, "Repartidor marcado como en camino"
        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error marcando salida reparto %s: %s", reparto_id, e)
            return False, "Error de base de datos"

    def marcar_entregado(self, reparto_id: int) -> tuple:
        s = self.session
        try:
            reparto = s.query(Reparto).filter_by(id=reparto_id).first()
            if not reparto:
                return False, "Reparto no encontrado"

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
            return True, "Pedido marcado como entregado"
        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error marcando entregado reparto %s: %s", reparto_id, e)
            return False, "Error de base de datos"
