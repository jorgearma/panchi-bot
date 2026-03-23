"""
Crea 4 pedidos demo completos en la base de datos con sus tablas relacionadas.

Uso:
    python3 scripts/crear_pedidos_demo.py

Qué crea:
1. Pedido `pagado` con pago registrado y picking pendiente
2. Pedido `en_preparacion` con picker asignado
3. Pedido `preparado` con picking completado y reparto pendiente
4. Pedido `en_reparto` con repartidor asignado y salida registrada

El objetivo es que estos pedidos se comporten como pedidos reales en dashboard,
picker y repartidor, sin depender del flujo HTTP/WhatsApp.
"""
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from main import create_app
from database import conectar_bd1, get_db
from models import (
    Categoria,
    Empleado,
    HistorialEstadoPedido,
    Pago,
    Pedido,
    PedidoDetalle,
    PickingItem,
    PickingPedido,
    Producto,
    Reparto,
    Rol,
    Usuario,
)
from states import EstadoPedido, EstadoPicking, EstadoReparto


SCRIPT_TAG = "seed_demo_pedidos_20260323"
BASE_PHONE = "+346000100"


def utc_now() -> datetime:
    """Devuelve un datetime UTC sin warning y compatible con columnas naive."""
    return datetime.now(UTC).replace(tzinfo=None)


def ensure_role(session, nombre: str, descripcion: str) -> Rol:
    role = session.query(Rol).filter_by(nombre=nombre).first()
    if role:
        return role
    role = Rol(nombre=nombre, descripcion=descripcion)
    session.add(role)
    session.flush()
    return role


def ensure_categoria(session) -> Categoria:
    categoria = session.query(Categoria).filter_by(nombre="Demo").first()
    if categoria:
        return categoria
    categoria = Categoria(nombre="Demo", orden_display=999, activa=True)
    session.add(categoria)
    session.flush()
    return categoria


def ensure_producto(
    session,
    categoria: Categoria,
    nombre: str,
    precio: str,
    stock: int,
    ubicacion: str,
) -> Producto:
    producto = session.query(Producto).filter_by(Nombre=nombre).first()
    if producto:
        return producto
    producto = Producto(
        categoria_id=categoria.id,
        Nombre=nombre,
        Precio=Decimal(precio),
        Categoria=categoria.nombre,
        Ingredientes="demo",
        Ubicacion=ubicacion,
        Stock=stock,
        ImagenURL=None,
        Descripcion=f"Producto demo {SCRIPT_TAG}",
        Descuento=Decimal("0.00"),
        Disponible=True,
    )
    session.add(producto)
    session.flush()
    return producto


def ensure_empleado(
    session,
    rol: Rol,
    nombre: str,
    apellido: str,
    email: str,
    puesto_legacy: str,
) -> Empleado:
    empleado = session.query(Empleado).filter_by(Email=email).first()
    if empleado:
        return empleado
    empleado = Empleado(
        rol_id=rol.id,
        Nombre=nombre,
        Apellido=apellido,
        Email=email,
        Telefono=None,
        Direccion="Base demo",
        Puesto=puesto_legacy,
        Salario=Decimal("0.00"),
        activo=True,
        estado_operativo="disponible",
        password_hash=None,
        rol_activo=rol.nombre if rol.nombre in {"picker", "repartidor"} else None,
    )
    session.add(empleado)
    session.flush()
    return empleado


def create_demo_user(session, idx: int) -> Usuario:
    numero_cliente = f"whatsapp:{BASE_PHONE}{idx:02d}"
    usuario = session.query(Usuario).filter_by(numero_cliente=numero_cliente).first()
    if usuario:
        return usuario
    usuario = Usuario(
        nombre=f"Cliente Demo {idx}",
        numero_cliente=numero_cliente,
        direccion=f"Calle Demo {idx}, Tarancon",
    )
    session.add(usuario)
    session.flush()
    return usuario


def add_historial(session, pedido_id: int, estado_anterior: str, estado_nuevo: str, notas: str) -> None:
    session.add(HistorialEstadoPedido(
        pedido_id=pedido_id,
        estado_anterior=estado_anterior,
        estado_nuevo=estado_nuevo,
        notas=notas,
    ))


def add_detalle(session, pedido_id: int, producto: Producto, cantidad: int) -> PedidoDetalle:
    precio_unitario = Decimal(str(producto.Precio))
    subtotal = precio_unitario * cantidad
    detalle = PedidoDetalle(
        PedidoID=pedido_id,
        ProductoID=producto.ProductoID,
        Cantidad=cantidad,
        PrecioUnitario=precio_unitario,
        NombreProducto=producto.Nombre,
        Subtotal=subtotal,
    )
    session.add(detalle)
    session.flush()
    return detalle


def create_pedido_base(session, usuario: Usuario, idx: int) -> Pedido:
    pedido = Pedido(
        ClienteID=usuario.id,
        FechaCreacion=utc_now() - timedelta(minutes=idx * 7),
        Estado=EstadoPedido.PENDIENTE.value,
        Total=Decimal("0.00"),
        DireccionEntrega=usuario.direccion,
        TelefonoEntrega=usuario.numero_cliente.replace("whatsapp:", ""),
        enlace=f"demo://pedido/{SCRIPT_TAG}/{idx}",
        redisID=str(uuid.uuid4()),
        estadopago=None,
        estadoauxiliar=SCRIPT_TAG,
        forma_pago="online",
        lat_entrega=40.006 + idx / 1000,
        lng_entrega=-3.001 - idx / 1000,
        Notas=SCRIPT_TAG,
    )
    session.add(pedido)
    session.flush()
    return pedido


def seed_one_order(
    session,
    idx: int,
    final_state: str,
    productos: list[tuple[Producto, int]],
    picker: Empleado | None,
    repartidor: Empleado | None,
) -> Pedido:
    usuario = create_demo_user(session, idx)

    existente = (
        session.query(Pedido)
        .filter_by(ClienteID=usuario.id, Notas=SCRIPT_TAG)
        .order_by(Pedido.PedidoID.desc())
        .first()
    )
    if existente:
        return existente

    pedido = create_pedido_base(session, usuario, idx)

    detalles = [add_detalle(session, pedido.PedidoID, producto, cantidad) for producto, cantidad in productos]
    pedido.Total = sum((detalle.Subtotal for detalle in detalles), Decimal("0.00"))

    add_historial(session, pedido.PedidoID, EstadoPedido.PENDIENTE.value, EstadoPedido.ENLACE.value, "Pedido demo: enlace generado")
    add_historial(session, pedido.PedidoID, EstadoPedido.ENLACE.value, EstadoPedido.ENLACE2.value, "Pedido demo: carrito confirmado")
    add_historial(session, pedido.PedidoID, EstadoPedido.ENLACE2.value, EstadoPedido.CONFIRMANDO_PAGO.value, "Pedido demo: pago iniciado")

    pedido.Estado = EstadoPedido.PAGADO.value
    pedido.estadopago = "SUCCEEDED"
    add_historial(session, pedido.PedidoID, EstadoPedido.CONFIRMANDO_PAGO.value, EstadoPedido.PAGADO.value, "Pedido demo: pago completado")

    session.add(Pago(
        pedido_id=pedido.PedidoID,
        proveedor="monei",
        referencia_externa=f"{SCRIPT_TAG}-pago-{idx}",
        estado="completado",
        importe=pedido.Total,
        importe_reembolsado=Decimal("0.00"),
        moneda="EUR",
        datos_raw='{"demo": true}',
    ))

    picking = PickingPedido(
        pedido_id=pedido.PedidoID,
        empleado_id=None,
        estado=EstadoPicking.PENDIENTE.value,
        created_at=utc_now(),
    )
    session.add(picking)
    session.flush()

    picking_items = []
    for detalle in detalles:
        item = PickingItem(
            picking_id=picking.id,
            pedido_detalle_id=detalle.DetalleID,
            estado="pendiente",
            cantidad_encontrada=None,
            producto_sustituto_id=None,
            notas=None,
        )
        session.add(item)
        picking_items.append((item, detalle))

    if final_state == EstadoPedido.PAGADO.value:
        return pedido

    pedido.Estado = EstadoPedido.EN_PREPARACION.value
    picking.empleado_id = picker.EmpleadoID if picker else None
    picking.estado = EstadoPicking.EN_PROCESO.value
    picking.iniciado_en = utc_now() - timedelta(minutes=5)
    add_historial(session, pedido.PedidoID, EstadoPedido.PAGADO.value, EstadoPedido.EN_PREPARACION.value, "Pedido demo: picking iniciado")

    if final_state == EstadoPedido.EN_PREPARACION.value:
        return pedido

    pedido.Estado = EstadoPedido.PREPARADO.value
    picking.estado = EstadoPicking.COMPLETADO.value
    picking.completado_en = utc_now() - timedelta(minutes=2)
    add_historial(session, pedido.PedidoID, EstadoPedido.EN_PREPARACION.value, EstadoPedido.PREPARADO.value, "Pedido demo: picking completado")

    for item, detalle in picking_items:
        item.estado = "encontrado"
        item.cantidad_encontrada = detalle.Cantidad

    reparto = Reparto(
        pedido_id=pedido.PedidoID,
        repartidor_id=None,
        estado=EstadoReparto.PENDIENTE.value,
    )
    session.add(reparto)
    session.flush()

    if final_state == EstadoPedido.PREPARADO.value:
        return pedido

    pedido.Estado = EstadoPedido.EN_REPARTO.value
    reparto.repartidor_id = repartidor.EmpleadoID if repartidor else None
    reparto.estado = EstadoReparto.EN_CAMINO.value
    reparto.hora_salida = utc_now() - timedelta(minutes=1)
    reparto.hora_estimada_entrega = utc_now() + timedelta(minutes=18)
    add_historial(session, pedido.PedidoID, EstadoPedido.PREPARADO.value, EstadoPedido.EN_REPARTO.value, "Pedido demo: repartidor en camino")
    return pedido


def main() -> int:
    app = create_app()

    with app.app_context():
        conectar_bd1()
        session = get_db()

        try:
            role_admin = ensure_role(session, "admin", "Acceso total")
            role_picker = ensure_role(session, "picker", "Preparacion de pedidos")
            role_repartidor = ensure_role(session, "repartidor", "Entrega de pedidos")

            categoria = ensure_categoria(session)
            producto_1 = ensure_producto(session, categoria, "Demo Tomate Frito", "3.50", 100, "A-01")
            producto_2 = ensure_producto(session, categoria, "Demo Pasta Fresca", "4.20", 100, "A-02")
            producto_3 = ensure_producto(session, categoria, "Demo Queso Curado", "5.80", 100, "A-03")

            ensure_empleado(session, role_admin, "Admin", "Demo", "admin.demo@panchi.local", "admin")
            picker = ensure_empleado(session, role_picker, "Paula", "Picker", "picker.demo@panchi.local", "picker")
            repartidor = ensure_empleado(session, role_repartidor, "Raul", "Repartidor", "repartidor.demo@panchi.local", "repartidor")

            pedidos = [
                seed_one_order(
                    session,
                    idx=1,
                    final_state=EstadoPedido.PAGADO.value,
                    productos=[(producto_1, 2), (producto_2, 1)],
                    picker=picker,
                    repartidor=repartidor,
                ),
                seed_one_order(
                    session,
                    idx=2,
                    final_state=EstadoPedido.EN_PREPARACION.value,
                    productos=[(producto_2, 2), (producto_3, 1)],
                    picker=picker,
                    repartidor=repartidor,
                ),
                seed_one_order(
                    session,
                    idx=3,
                    final_state=EstadoPedido.PREPARADO.value,
                    productos=[(producto_1, 1), (producto_3, 2)],
                    picker=picker,
                    repartidor=repartidor,
                ),
                seed_one_order(
                    session,
                    idx=4,
                    final_state=EstadoPedido.EN_REPARTO.value,
                    productos=[(producto_1, 1), (producto_2, 1), (producto_3, 1)],
                    picker=picker,
                    repartidor=repartidor,
                ),
            ]

            session.commit()

            print("Pedidos demo listos:")
            for pedido in pedidos:
                print(f"  - Pedido #{pedido.PedidoID}: estado={pedido.Estado} total={pedido.Total} cliente_id={pedido.ClienteID}")
        except Exception:
            session.rollback()
            raise

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
