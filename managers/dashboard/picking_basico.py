"""Picking — operaciones de consulta: listados y búsquedas."""
import logging

from managers.dashboard._helpers import (
    _iso,
    _ESTADOS_LISTOS_PARA_PICKING,
)
from models import Pedido, PickingPedido, Producto
from states import EstadoPicking, EstadoPedido

logger = logging.getLogger(__name__)


class GestorPickingBasicoMixin:

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

    def pickings_sin_asignar(self) -> list[dict]:
        """Pedidos con PickingPedido creado pero sin picker asignado.
        Solo incluye pedidos en estado activo (Pagado, contra_reembolso, en_preparacion).
        """
        from datetime import datetime
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
