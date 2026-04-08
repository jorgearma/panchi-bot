"""Picking — operaciones de flujo: asignación, reclamación, completado."""
import logging
import time
from datetime import datetime

from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from managers.dashboard._helpers import _ESTADOS_LISTOS_PARA_PICKING
from models import (
    Empleado, HistorialEstadoPedido, Pedido,
    PickingItem, PickingPedido, Reparto,
)
from states import (
    EstadoPedido, EstadoPicking, EstadoReparto,
    transicion_valida_pedido,
)

logger = logging.getLogger(__name__)

_retry_db = retry(
    retry=retry_if_exception_type(OperationalError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    reraise=True,
)


class GestorPickingFlujoMixin:

    @_retry_db
    def asignar_picker(self, pedido_id: int, empleado_id: int) -> tuple:
        """Asigna un picker al pedido e inicia el picking."""
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

            # Side effects post-commit (best effort — picking ya confirmado en BD)
            try:
                from message_queue import queue_whatsapp
                from managers.dashboard.jobs import notificar_picker_job
                from utils.rq_callbacks import on_job_failure
                queue_whatsapp.enqueue(
                    notificar_picker_job,
                    empleado.Telefono,
                    pedido_id,
                    on_failure=on_job_failure,
                    retry=3,
                    failure_ttl=86400,
                )
            except Exception as e:
                logger.warning("No se pudo encolar notificación picker para pedido %s: %s", pedido_id, e)

            self._actualizar_estado_operativo(empleado_id, 'ocupado')
            return True, "Picker asignado correctamente"

        except OperationalError:
            s.rollback()
            raise  # tenacity necesita que se propague para reintentar

        except IntegrityError:
            s.rollback()
            logger.info("IntegrityError picking pedido %s — race condition resuelta", pedido_id)
            return True, "Picker asignado correctamente"

        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error asignando picker para pedido %s: %s", pedido_id, e)
            return False, "Error de base de datos"

    @_retry_db
    def reasignar_picker(self, picking_id: int, nuevo_empleado_id: int | None) -> tuple:
        """Cambia el picker asignado o deja el picking libre."""
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

        except OperationalError:
            s.rollback()
            raise  # tenacity reintenta

        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error reasignando picker para picking %s: %s", picking_id, e)
            return False, "Error interno"

    def completar_picking(self, picking_id: int, picker_id: int | None = None) -> tuple:
        """Returns (ok, msg, telefono_cliente). telefono_cliente is None on error.

        No usa @_retry_db porque tiene lógica post-commit (crear Reparto, encolar RQ).
        Un retry reiniciaría todo incluyendo lo ya hecho. El backoff es manual solo
        en el bloque del commit principal.
        """
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
            pedido_id_para_reparto = None
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

        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error completando picking %s: %s", picking_id, e)
            return False, "Error de base de datos", None

        # Backoff manual: OperationalError solo en el commit principal
        _picker_id = picking.empleado_id
        intentos = 0
        while intentos < 3:
            try:
                s.commit()
                break
            except OperationalError:
                s.rollback()
                intentos += 1
                if intentos >= 3:
                    logger.error("completar_picking %s falló 3 veces por OperationalError", picking_id)
                    return False, "Error de base de datos", None
                time.sleep(2 ** intentos)
            except IntegrityError:
                s.rollback()
                return False, "Error de integridad", None
            except SQLAlchemyError as e:
                s.rollback()
                logger.error("Error completando picking %s: %s", picking_id, e)
                return False, "Error de base de datos", None

        # Post-commit: crear Reparto + encolar side effects
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

        # Descontar stock → RQ (pasa picking_id int, no lista — idempotencia garantizada)
        try:
            from message_queue import queue_dashboard
            from managers.dashboard.jobs import descontar_stock_picking_job
            from utils.rq_callbacks import on_job_failure
            queue_dashboard.enqueue(
                descontar_stock_picking_job,
                picking_id,
                on_failure=on_job_failure,
                retry=3,
                failure_ttl=86400,
            )
        except Exception as e:
            logger.warning("No se pudo encolar descontar_stock para picking %s: %s", picking_id, e)

        # Disponibilidad picker — expire_all fuerza recarga desde BD (evita caché post-commit)
        if _picker_id:
            s.expire_all()
            activos = s.query(PickingPedido).filter(
                PickingPedido.empleado_id == _picker_id,
                PickingPedido.estado.in_([
                    EstadoPicking.PENDIENTE.value,
                    EstadoPicking.EN_PROCESO.value,
                    EstadoPicking.CON_INCIDENCIAS.value,
                ]),
            ).count()
            if activos == 0:
                self._actualizar_estado_operativo(_picker_id, 'disponible')

        return True, "Picking completado", None

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

    def asignar_cocina_equipo(self, pedido_id: int) -> tuple:
        """Restaurant mode: acepta el pedido en nombre de todo el equipo de cocina activo.

        Crea un único PickingPedido (por la restricción unique en pedido_id) asignado al
        primer cocinero disponible, y registra los nombres de todo el equipo en `notas`.
        Retorna (ok, mensaje, [nombres_equipo]).
        """
        s = self.session
        try:
            pedido = s.query(Pedido).filter_by(PedidoID=pedido_id).first()
            if not pedido:
                return False, "Pedido no encontrado", []
            if pedido.Estado not in _ESTADOS_LISTOS_PARA_PICKING:
                return False, f"Estado '{pedido.Estado}' no permite asignar cocina", []

            # 1º opción: cocineros con check-in activo (rol_activo='picker', no desconectados)
            from models import Rol
            cocineros = (
                s.query(Empleado)
                .filter(
                    Empleado.activo == True,
                    Empleado.rol_activo == 'picker',
                    Empleado.estado_operativo.notin_(['desconectado']),
                )
                .order_by(Empleado.EmpleadoID)
                .all()
            )

            # Fallback: empleados con Rol.nombre='picker' aunque no tengan check-in activo
            if not cocineros:
                cocineros = (
                    s.query(Empleado)
                    .join(Empleado.rol)
                    .filter(
                        Empleado.activo == True,
                        Rol.nombre == 'picker',
                    )
                    .order_by(Empleado.EmpleadoID)
                    .all()
                )

            if not cocineros:
                return False, "No hay cocineros disponibles. Crea empleados con rol 'picker'.", []

            principal = cocineros[0]
            nombres = [f"{c.Nombre} {c.Apellido}" for c in cocineros]
            nota_equipo = "Equipo cocina: " + ", ".join(nombres)

            picking = s.query(PickingPedido).filter_by(pedido_id=pedido_id).first()
            if picking:
                picking.empleado_id = principal.EmpleadoID
                picking.estado = EstadoPicking.EN_PROCESO.value
                picking.iniciado_en = datetime.utcnow()
                picking.notas = nota_equipo
            else:
                picking = PickingPedido(
                    pedido_id=pedido_id,
                    empleado_id=principal.EmpleadoID,
                    estado=EstadoPicking.EN_PROCESO.value,
                    iniciado_en=datetime.utcnow(),
                    notas=nota_equipo,
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
                    notas=f"Aceptado en cocina — {nota_equipo}",
                ))

            s.commit()
            for c in cocineros:
                self._actualizar_estado_operativo(c.EmpleadoID, 'ocupado')

            n = len(cocineros)
            msg = f"Pedido aceptado por cocina ({n} cocinero{'s' if n > 1 else ''})"
            return True, msg, nombres
        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error asignando cocina equipo para pedido %s: %s", pedido_id, e)
            return False, "Error de base de datos", []

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
