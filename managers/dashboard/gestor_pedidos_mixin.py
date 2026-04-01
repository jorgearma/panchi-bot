"""Mixin: consultas de pedidos activos, métricas diarias, alertas e historial."""
import logging
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func

from managers.dashboard._helpers import (
    _iso, _COLORES_ESTADO, _UMBRALES_RETRASO, _ESTADOS_OPERATIVOS,
)
from models import (
    HistorialEstadoPedido, Pedido, PedidoDetalle,
    PickingPedido, Producto, Reparto,
)
from states import EstadoPedido, EstadoPicking, EstadoReparto

logger = logging.getLogger(__name__)


class GestorPedidosMixin:

    def metricas(self) -> dict:
        """Resume los KPIs operativos principales del dashboard."""
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

    def pedidos_activos(self, estado: str = None) -> list:
        """Lista pedidos activos con su contexto operativo actual."""
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
                    "notas": p.picking.notas,
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

    def alertas(self) -> list:
        """Genera alertas por retrasos, reparto pendiente y stock bajo."""
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

        # Prepared orders with no delivery driver assigned (Reparto PENDIENTE sin repartidor_id)
        for r in s.query(Reparto).filter(
            Reparto.repartidor_id == None,
            Reparto.estado == EstadoReparto.PENDIENTE.value,
        ).join(Pedido, Pedido.PedidoID == Reparto.pedido_id).filter(
            Pedido.Estado == EstadoPedido.PREPARADO.value,
        ).all():
            p = r.pedido
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
        """Devuelve los ultimos cambios de estado registrados."""
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

    def historial_pedidos(
        self,
        desde: str = None,
        hasta: str = None,
        estado: str = None,
        forma_pago: str = None,
        q: str = None,
        page: int = 1,
        per_page: int = 25,
    ) -> dict:
        """Pagina el historial de pedidos con filtros basicos."""
        from math import ceil
        from sqlalchemy import or_
        from models import Usuario

        estados_finales = [
            EstadoPedido.ENTREGADO.value,
            EstadoPedido.CANCELADO.value,
            EstadoPedido.REEMBOLSADO.value,
        ]

        per_page = min(per_page, 100)
        s = self.session

        query = s.query(Pedido)

        if desde:
            try:
                dt_desde = datetime.strptime(desde, '%Y-%m-%d')
                query = query.filter(Pedido.FechaCreacion >= dt_desde)
            except ValueError:
                pass

        if hasta:
            try:
                dt_hasta = datetime.strptime(hasta, '%Y-%m-%d') + timedelta(days=1)
                query = query.filter(Pedido.FechaCreacion < dt_hasta)
            except ValueError:
                pass

        if estado:
            query = query.filter(Pedido.Estado == estado)
        else:
            query = query.filter(Pedido.Estado.in_(estados_finales))

        if forma_pago:
            query = query.filter(Pedido.forma_pago == forma_pago)

        if q:
            q_strip = q.strip()
            if q_strip.isdigit():
                query = query.filter(Pedido.PedidoID == int(q_strip))
            else:
                q_escaped = q_strip.replace('%', r'\%').replace('_', r'\_')
                query = query.outerjoin(Usuario, Pedido.ClienteID == Usuario.id).filter(
                    or_(
                        Usuario.nombre.ilike(f'%{q_escaped}%', escape='\\'),
                        Pedido.TelefonoEntrega.ilike(f'%{q_escaped}%', escape='\\'),
                    )
                )

        total = query.count()
        pages = ceil(total / per_page) if total else 1

        pedidos = (
            query
            .order_by(Pedido.FechaCreacion.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        resultado = []
        for p in pedidos:
            resultado.append({
                "pedido_id": p.PedidoID,
                "cliente_nombre": p.cliente.nombre if p.cliente else "—",
                "cliente_telefono": p.TelefonoEntrega,
                "estado": p.Estado,
                "forma_pago": p.forma_pago or "online",
                "total": float(p.Total) if p.Total else 0.0,
                "fecha_creacion": _iso(p.FechaCreacion),
                "fecha_actualizacion": _iso(p.FechaActualizacion),
                "notas": p.Notas,
                "cancel_reason": p.cancel_reason,
            })

        return {"pedidos": resultado, "total": total, "page": page, "pages": pages}

    def detalle_pedido(self, pedido_id: int) -> dict | None:
        """Devuelve el detalle operativo completo de un pedido."""
        s = self.session
        p = s.query(Pedido).filter_by(PedidoID=pedido_id).first()
        if not p:
            return None

        items = [
            {
                "detalle_id": d.DetalleID,
                "nombre": d.NombreProducto or (d.producto.Nombre if d.producto else "—"),
                "cantidad": d.Cantidad,
                "precio_unitario": float(d.PrecioUnitario) if d.PrecioUnitario else 0.0,
                "subtotal": float(d.Subtotal) if d.Subtotal else 0.0,
            }
            for d in p.detalles
        ]

        historial = [
            {
                "estado_anterior": h.estado_anterior,
                "estado_nuevo": h.estado_nuevo,
                "cambiado_en": _iso(h.cambiado_en),
                "notas": h.notas,
            }
            for h in sorted(p.historial_estados, key=lambda h: h.cambiado_en or datetime.min)
        ]

        picking = None
        if p.picking:
            pk = p.picking
            picking = {
                "estado": pk.estado,
                "picker_nombre": (
                    f"{pk.empleado.Nombre} {pk.empleado.Apellido}" if pk.empleado else None
                ),
                "asignado_en": _iso(pk.created_at),
                "iniciado_en": _iso(pk.iniciado_en),
                "completado_en": _iso(pk.completado_en),
            }

        reparto = None
        if p.reparto:
            rp = p.reparto
            reparto = {
                "estado": rp.estado,
                "repartidor_nombre": (
                    f"{rp.repartidor.Nombre} {rp.repartidor.Apellido}" if rp.repartidor else None
                ),
                "hora_salida": _iso(rp.hora_salida),
                "hora_entrega_real": _iso(rp.hora_entrega_real),
                "metodo_cobro": rp.metodo_cobro,
                "importe_cobrado": float(rp.importe_cobrado) if rp.importe_cobrado else None,
            }

        pedido_dict = {
            "pedido_id": p.PedidoID,
            "cliente_nombre": p.cliente.nombre if p.cliente else "—",
            "cliente_telefono": p.TelefonoEntrega,
            "direccion_entrega": p.DireccionEntrega,
            "estado": p.Estado,
            "forma_pago": p.forma_pago or "online",
            "total": float(p.Total) if p.Total else 0.0,
            "fecha_creacion": _iso(p.FechaCreacion),
            "fecha_actualizacion": _iso(p.FechaActualizacion),
            "notas": p.Notas,
            "cancel_reason": p.cancel_reason,
        }

        return {
            "pedido": pedido_dict,
            "items": items,
            "historial": historial,
            "picking": picking,
            "reparto": reparto,
        }
