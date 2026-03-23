"""Mixin: operaciones de picking — asignación, reclamación, completado."""
import logging
from datetime import datetime
from threading import Thread

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from managers.dashboard._helpers import (
    _iso,
    _ESTADOS_LISTOS_PARA_PICKING,
)
from models import (
    Empleado, HistorialEstadoPedido, Pedido,
    PickingItem, PickingPedido, Producto, Reparto,
)
from states import (
    EstadoPedido, EstadoPicking, EstadoReparto,
    transicion_valida_pedido,
)

logger = logging.getLogger(__name__)


class GestorPickingMixin:

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

            # Si se está asignando un picker y el pedido aún está en PAGADO/CONTRA_REEMBOLSO
            # (porque _asegurar_picking_si_procede creó el PickingPedido antes de que hubiera picker),
            # transicionar el pedido a EN_PREPARACION para que completar_picking pueda avanzar a PREPARADO.
            if nuevo_empleado_id:
                pedido = s.query(Pedido).filter_by(PedidoID=picking.pedido_id).first()
                if pedido and transicion_valida_pedido(pedido.Estado, EstadoPedido.EN_PREPARACION.value):
                    estado_anterior = pedido.Estado
                    pedido.Estado = EstadoPedido.EN_PREPARACION.value
                    s.add(HistorialEstadoPedido(
                        pedido_id=pedido.PedidoID,
                        estado_anterior=estado_anterior,
                        estado_nuevo=EstadoPedido.EN_PREPARACION.value,
                        notas=f"Picking asignado desde dashboard — picker #{nuevo_empleado_id}",
                    ))

            s.commit()
            if nuevo_empleado_id:
                self._actualizar_estado_operativo(nuevo_empleado_id, 'ocupado')
                return True, "Picker asignado correctamente"
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
            pedido_id_para_reparto = None  # capturar antes del commit para evitar lazy-load post-expire
            if pedido and transicion_valida_pedido(pedido.Estado, EstadoPedido.PREPARADO.value):
                estado_anterior = pedido.Estado
                pedido.Estado = EstadoPedido.PREPARADO.value
                pedido_id_para_reparto = pedido.PedidoID
                s.add(HistorialEstadoPedido(
                    pedido_id=pedido.PedidoID,
                    estado_anterior=estado_anterior,
                    estado_nuevo=EstadoPedido.PREPARADO.value,
                    notas="Picking completado",
                ))

            s.commit()

            if pedido_id_para_reparto:
                try:
                    reparto_existente = s.query(Reparto).filter_by(pedido_id=pedido_id_para_reparto).first()
                    if not reparto_existente:
                        s.add(Reparto(
                            pedido_id=pedido_id_para_reparto,
                            repartidor_id=None,
                            estado=EstadoReparto.PENDIENTE.value,
                        ))
                        s.commit()
                        logger.info("REPARTO_CREADO pedido=%s", pedido_id_para_reparto)
                except Exception as _exc:
                    s.rollback()
                    if isinstance(_exc, IntegrityError):
                        logger.info("Reparto ya creado concurrentemente para pedido %s", pedido_id_para_reparto)
                    else:
                        logger.warning("No se pudo crear Reparto para pedido %s: %s", pedido_id_para_reparto, _exc)

            # Descontar stock en background — no bloquea la respuesta HTTP
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
                def _descontar(items=items_para_stock):
                    from database import SessionLocal
                    from models import Producto
                    from sqlalchemy.exc import SQLAlchemyError
                    s = SessionLocal()
                    try:
                        for item in items:
                            p = s.query(Producto).filter_by(ProductoID=item["producto_id"]).first()
                            if not p:
                                continue
                            if item["estado"] == "encontrado":
                                cantidad = item["cantidad_encontrada"] or item["cantidad_pedida"]
                                p.Stock = max(0, p.Stock - cantidad)
                                if p.Stock == 0:
                                    p.Disponible = False
                            elif item["estado"] == "sin_stock":
                                p.Stock = 0
                                p.Disponible = False
                        s.commit()
                    except SQLAlchemyError as e:
                        s.rollback()
                        logger.error("Error descontando stock picking: %s", e)
                    finally:
                        s.close()
                Thread(target=_descontar, daemon=True).start()

            # Auto-actualizar estado en background: no bloquea la respuesta HTTP
            _picker_id = picking.empleado_id
            if _picker_id:
                def _actualizar_disponibilidad_picker(emp_id=_picker_id):
                    from database import SessionLocal
                    _s = SessionLocal()
                    try:
                        _activos = _s.query(PickingPedido).filter(
                            PickingPedido.empleado_id == emp_id,
                            PickingPedido.estado.in_([
                                EstadoPicking.PENDIENTE.value,
                                EstadoPicking.EN_PROCESO.value,
                                EstadoPicking.CON_INCIDENCIAS.value,
                            ]),
                        ).count()
                        if _activos == 0:
                            self._actualizar_estado_operativo(emp_id, 'disponible')
                    except Exception as e:
                        logger.warning("Error comprobando disponibilidad picker %s: %s", emp_id, e)
                    finally:
                        _s.close()
                Thread(target=_actualizar_disponibilidad_picker, daemon=True).start()

            telefono = pedido.TelefonoEntrega if pedido else None
            return True, "Picking completado", telefono
        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error completando picking %s: %s", picking_id, e)
            return False, "Error de base de datos", None

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
        Asigna el picking al empleado de forma atómica, avanza el estado a EN_PROCESO
        y transiciona el Pedido padre a EN_PREPARACION.
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

            pedido_id_para_transicion = picking.pedido_id

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

            if resultado == 0:
                return False, 'ya_cogido'

            # 3. Transicionar el Pedido a EN_PREPARACION en la misma transacción
            pedido = s.query(Pedido).filter_by(PedidoID=pedido_id_para_transicion).first()
            if pedido and transicion_valida_pedido(pedido.Estado, EstadoPedido.EN_PREPARACION.value):
                estado_anterior = pedido.Estado
                pedido.Estado = EstadoPedido.EN_PREPARACION.value
                s.add(HistorialEstadoPedido(
                    pedido_id=pedido.PedidoID,
                    estado_anterior=estado_anterior,
                    estado_nuevo=EstadoPedido.EN_PREPARACION.value,
                    notas=f"Picking iniciado — picker #{empleado_id}",
                ))

            # Un solo commit: picking + pedido juntos, o nada
            s.commit()

            # 4. Actualizar estado operativo del picker
            self._actualizar_estado_operativo(empleado_id, 'ocupado')
            return True, 'ok'

        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error reclamando picking %s: %s", picking_id, e)
            return False, 'error'
