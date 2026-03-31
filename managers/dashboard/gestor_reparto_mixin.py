"""Mixin: operaciones de reparto — asignación, entrega, cobro, cierre de caja."""
import logging
from datetime import date, datetime, timedelta
from threading import Thread

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload, selectinload

from managers.dashboard._helpers import (
    _iso,
    _TARANCON_LAT,
    _TARANCON_LNG,
    _ESTADOS_OPERATIVOS,
)
from models import (
    Empleado, HistorialEstadoPedido, Pedido, PedidoDetalle,
    Reparto, Rol,
)
from states import (
    EstadoPedido, EstadoReparto,
    transicion_valida_pedido,
)

logger = logging.getLogger(__name__)


class GestorRepartoMixin:

    def repartidores(self) -> dict:
        s = self.session
        hoy = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        empleados = s.query(Empleado).filter(Empleado.activo == True).all()

        # Pedidos PREPARADO sin repartidor: excluir solo los que ya tienen Reparto con repartidor asignado.
        # Cubre tanto el caso sin fila Reparto como el caso con fila Reparto pero repartidor_id=NULL
        # (completar_picking crea Reparto(repartidor_id=None) automáticamente).
        repartos_con_repartidor_ids = {
            r.pedido_id for r in s.query(Reparto.pedido_id).filter(
                Reparto.repartidor_id != None
            ).all()
        }
        preparados_sin_reparto = s.query(Pedido).filter(
            Pedido.Estado == EstadoPedido.PREPARADO.value,
            ~Pedido.PedidoID.in_(repartos_con_repartidor_ids) if repartos_con_repartidor_ids else True,
        ).all()

        lista_empleados = []
        for e in empleados:
            repartos_activos = s.query(Reparto).filter(
                Reparto.repartidor_id == e.EmpleadoID,
                Reparto.estado.in_([EstadoReparto.ASIGNADO.value, EstadoReparto.EN_CAMINO.value]),
            ).all()

            from sqlalchemy import func
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

            # Auto-actualizar estado en background: no bloquea la respuesta HTTP
            _repartidor_id = reparto.repartidor_id
            if _repartidor_id:
                def _actualizar_disponibilidad(emp_id=_repartidor_id):
                    from database import SessionLocal
                    _s = SessionLocal()
                    try:
                        _activos = _s.query(Reparto).filter(
                            Reparto.repartidor_id == emp_id,
                            Reparto.estado.in_([
                                EstadoReparto.ASIGNADO.value,
                                EstadoReparto.EN_CAMINO.value,
                            ]),
                        ).count()
                        if _activos == 0:
                            self._actualizar_estado_operativo(emp_id, 'disponible')
                    except Exception as e:
                        logger.warning("Error comprobando disponibilidad repartidor %s: %s", emp_id, e)
                    finally:
                        _s.close()
                Thread(target=_actualizar_disponibilidad, daemon=True).start()

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

    def repartos_del_repartidor(self, empleado_id: int) -> list:
        """Returns active and today's completed orders for a delivery driver."""
        s = self.session
        hoy_inicio = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        from sqlalchemy import or_, and_
        repartos = s.query(Reparto).options(
            joinedload(Reparto.pedido).options(
                joinedload(Pedido.cliente),
                selectinload(Pedido.pagos),
                selectinload(Pedido.detalles).joinedload(PedidoDetalle.producto),
            )
        ).filter(
            Reparto.repartidor_id == empleado_id,
            or_(
                Reparto.estado.in_([
                    EstadoReparto.ASIGNADO.value,
                    EstadoReparto.EN_CAMINO.value,
                ]),
                and_(
                    Reparto.estado.in_([
                        EstadoReparto.ENTREGADO.value,
                        EstadoReparto.NO_ENTREGADO.value,
                    ]),
                    Reparto.created_at >= hoy_inicio,
                ),
            ),
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
                    "label": "Cobrar",
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

    def repartos_sin_asignar(self) -> list[dict]:
        """Pedidos PREPARADO sin repartidor asignado.
        Incluye tanto pedidos con Reparto PENDIENTE como pedidos sin Reparto todavía.
        """
        s = self.session
        ahora = datetime.utcnow()
        resultado = []

        # Pedidos PREPARADO con Reparto PENDIENTE y sin repartidor
        repartos = (
            s.query(Reparto)
            .join(Pedido, Pedido.PedidoID == Reparto.pedido_id)
            .filter(
                Reparto.repartidor_id == None,
                Reparto.estado == EstadoReparto.PENDIENTE.value,
                Pedido.Estado == EstadoPedido.PREPARADO.value,
            )
            .all()
        )
        pedido_ids_con_reparto = set()
        for r in repartos:
            pedido_ids_con_reparto.add(r.pedido_id)
            resultado.append({
                'pedido_id':          r.pedido_id,
                'n_items':            len(r.pedido.detalles) if r.pedido else 0,
                'direccion_entrega':  r.pedido.DireccionEntrega if r.pedido else '—',
                'segundos_esperando': int((ahora - r.created_at).total_seconds()) if r.created_at else 0,
                'lat':                r.pedido.lat_entrega if r.pedido else None,
                'lng':                r.pedido.lng_entrega if r.pedido else None,
            })

        # Pedidos PREPARADO sin ningún Reparto (auto-creación no ocurrió o falló)
        pedidos_sin_reparto = (
            s.query(Pedido)
            .outerjoin(Reparto, Reparto.pedido_id == Pedido.PedidoID)
            .filter(
                Pedido.Estado == EstadoPedido.PREPARADO.value,
                Reparto.id == None,
            )
            .all()
        )
        for p in pedidos_sin_reparto:
            if p.PedidoID not in pedido_ids_con_reparto:
                resultado.append({
                    'pedido_id':          p.PedidoID,
                    'n_items':            len(p.detalles) if p.detalles else 0,
                    'direccion_entrega':  p.DireccionEntrega or '—',
                    'segundos_esperando': int((ahora - p.FechaCreacion).total_seconds()) if p.FechaCreacion else 0,
                    'lat':                p.lat_entrega,
                    'lng':                p.lng_entrega,
                })

        return sorted(resultado, key=lambda x: x['segundos_esperando'], reverse=True)

    def reclamar_reparto(self, pedido_id: int, empleado_id: int) -> tuple[bool, str]:
        """
        Asigna el reparto al empleado de forma atómica usando pedido_id.
        Crea el Reparto si no existe todavía.
        Nota: no transiciona Pedido.Estado a EN_REPARTO — esa responsabilidad
        recae en la ruta de blueprint que llama a este método.
        Returns:
            (True,  'ok')            — asignado correctamente
            (False, 'no_encontrado') — pedido_id no existe o no está en PREPARADO
            (False, 'ya_cogido')     — otro repartidor se adelantó
            (False, 'error')         — error de BD
        """
        s = self.session
        try:
            # Una sola query: Pedido + Reparto (outer join) en vez de dos queries separadas
            fila = (
                s.query(Pedido, Reparto)
                .outerjoin(Reparto, Reparto.pedido_id == Pedido.PedidoID)
                .filter(Pedido.PedidoID == pedido_id)
                .first()
            )
            if not fila or fila[0].Estado != EstadoPedido.PREPARADO.value:
                return False, 'no_encontrado'

            pedido, reparto = fila
            if reparto:
                # Ya existe — intentar asignar atómicamente
                if reparto.repartidor_id is not None:
                    return False, 'ya_cogido'
                resultado = (
                    s.query(Reparto)
                    .filter(
                        Reparto.pedido_id == pedido_id,
                        Reparto.repartidor_id == None,
                    )
                    .update(
                        {'repartidor_id': empleado_id, 'estado': EstadoReparto.ASIGNADO.value},
                        synchronize_session=False,
                    )
                )
                s.commit()
                if resultado == 0:
                    return False, 'ya_cogido'
            else:
                # No existe — crear y asignar directamente
                s.add(Reparto(
                    pedido_id=pedido_id,
                    repartidor_id=empleado_id,
                    estado=EstadoReparto.ASIGNADO.value,
                ))
                try:
                    s.commit()
                except IntegrityError:
                    s.rollback()
                    return False, 'ya_cogido'

            self._actualizar_estado_operativo(empleado_id, 'ocupado')
            return True, 'ok'

        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error reclamando reparto pedido %s: %s", pedido_id, e)
            return False, 'error'
