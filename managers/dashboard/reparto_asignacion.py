"""Reparto — asignación de repartidores y listados."""
import logging
from datetime import datetime, date

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from managers.dashboard._helpers import _iso
from models import CheckIn, Empleado, Pedido, Reparto, Turno
from states import EstadoPedido, EstadoReparto

logger = logging.getLogger(__name__)


class GestorRepartoAsignacionMixin:

    def repartidores(self) -> dict:
        """Resume repartidores y pedidos listos para asignar."""
        s = self.session
        hoy = date.today()
        hoy_dt = datetime.combine(hoy, datetime.min.time())

        # Solo empleados con turno HOY (no cancelado)
        ids_con_turno = {
            t.empleado_id for t in s.query(Turno.empleado_id).filter(
                Turno.fecha == hoy,
                Turno.estado != 'cancelado',
            ).all()
        }

        empleados = s.query(Empleado).filter(
            Empleado.activo == True,
            Empleado.EmpleadoID.in_(ids_con_turno) if ids_con_turno else False,
        ).all()

        # Check-ins abiertos hoy (fin == None)
        # CheckIn.fecha se graba en UTC (datetime.utcnow().date()), usar la misma referencia.
        hoy_utc = datetime.utcnow().date()
        checkins_abiertos = {
            ci.empleado_id for ci in s.query(CheckIn.empleado_id).filter(
                CheckIn.fecha == hoy_utc,
                CheckIn.fin == None,
            ).all()
        }

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

            entregados_hoy = s.query(func.count(Reparto.id)).filter(
                Reparto.repartidor_id == e.EmpleadoID,
                Reparto.estado == EstadoReparto.ENTREGADO.value,
                Reparto.hora_entrega_real >= hoy_dt,
            ).scalar() or 0

            pedidos_activos_data = [
                {
                    "reparto_id": r.id,
                    "pedido_id": r.pedido_id,
                    "estado_reparto": r.estado,
                    "direccion": r.pedido.DireccionEntrega if r.pedido else "—",
                    "hora_salida": _iso(r.hora_salida),
                    "hora_estimada_entrega": _iso(r.hora_estimada_entrega),
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
                "tiene_checkin": e.EmpleadoID in checkins_abiertos,
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

    def asignar_repartidor(self, pedido_id: int, empleado_id: int) -> tuple:
        """Asigna un repartidor a un pedido preparado."""
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
