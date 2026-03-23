"""
Crea 4 pedidos demo en estado `pagado`.

Uso:
    python3 scripts/crear_pedidos_demo_pagados.py

Qué crea:
1. Pedido `pagado` con pago registrado y picking pendiente
2. Pedido `pagado` con pago registrado y picking pendiente
3. Pedido `pagado` con pago registrado y picking pendiente
4. Pedido `pagado` con pago registrado y picking pendiente

El objetivo es poblar el dashboard con pedidos listos para entrar en cola de picking,
sin avanzar a preparacion ni reparto.
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
    HistorialEstadoPedido,
    Pago,
    Pedido,
    PedidoDetalle,
    PickingItem,
    PickingPedido,
    Producto,
    Usuario,
)
from states import EstadoPedido, EstadoPicking


SCRIPT_TAG = "seed_demo_pedidos_pagados_20260323"
BASE_PHONE = "+346000200"


def utc_now() -> datetime:
    """Devuelve un datetime UTC sin warning y compatible con columnas naive."""
    return datetime.now(UTC).replace(tzinfo=None)


def build_run_tag() -> str:
    """Genera una marca única por ejecución para evitar colisiones al reseedear."""
    return f"{SCRIPT_TAG}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"


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


def create_demo_user(session, idx: int) -> Usuario:
    numero_cliente = f"whatsapp:{BASE_PHONE}{idx:02d}"
    usuario = session.query(Usuario).filter_by(numero_cliente=numero_cliente).first()
    if usuario:
        return usuario
    usuario = Usuario(
        nombre=f"Cliente Demo Pagado {idx}",
        numero_cliente=numero_cliente,
        direccion=f"Calle Demo Pagado {idx}, Tarancon",
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


def create_pedido_base(session, usuario: Usuario, idx: int, run_tag: str) -> Pedido:
    pedido = Pedido(
        ClienteID=usuario.id,
        FechaCreacion=utc_now() - timedelta(minutes=idx * 5),
        Estado=EstadoPedido.PENDIENTE.value,
        Total=Decimal("0.00"),
        DireccionEntrega=usuario.direccion,
        TelefonoEntrega=usuario.numero_cliente.replace("whatsapp:", ""),
        enlace=f"demo://pedido/{run_tag}/{idx}",
        redisID=str(uuid.uuid4()),
        estadopago=None,
        estadoauxiliar=run_tag,
        forma_pago="online",
        lat_entrega=40.016 + idx / 1000,
        lng_entrega=-3.011 - idx / 1000,
        Notas=run_tag,
    )
    session.add(pedido)
    session.flush()
    return pedido


def seed_paid_order(session, idx: int, run_tag: str, productos: list[tuple[Producto, int]]) -> Pedido:
    usuario = create_demo_user(session, idx)
    pedido = create_pedido_base(session, usuario, idx, run_tag)

    detalles = [add_detalle(session, pedido.PedidoID, producto, cantidad) for producto, cantidad in productos]
    pedido.Total = sum((detalle.Subtotal for detalle in detalles), Decimal("0.00"))

    add_historial(session, pedido.PedidoID, EstadoPedido.PENDIENTE.value, EstadoPedido.ENLACE.value, "Pedido demo pagado: enlace generado")
    add_historial(session, pedido.PedidoID, EstadoPedido.ENLACE.value, EstadoPedido.ENLACE2.value, "Pedido demo pagado: carrito confirmado")
    add_historial(session, pedido.PedidoID, EstadoPedido.ENLACE2.value, EstadoPedido.CONFIRMANDO_PAGO.value, "Pedido demo pagado: pago iniciado")

    pedido.Estado = EstadoPedido.PAGADO.value
    pedido.estadopago = "SUCCEEDED"
    add_historial(session, pedido.PedidoID, EstadoPedido.CONFIRMANDO_PAGO.value, EstadoPedido.PAGADO.value, "Pedido demo pagado: pago completado")

    session.add(Pago(
        pedido_id=pedido.PedidoID,
        proveedor="monei",
        referencia_externa=f"{run_tag}-pago-{idx}",
        estado="completado",
        importe=pedido.Total,
        importe_reembolsado=Decimal("0.00"),
        moneda="EUR",
        datos_raw='{"demo": true, "tipo": "solo_pagado"}',
    ))

    picking = PickingPedido(
        pedido_id=pedido.PedidoID,
        empleado_id=None,
        estado=EstadoPicking.PENDIENTE.value,
        created_at=utc_now(),
    )
    session.add(picking)
    session.flush()

    for detalle in detalles:
        session.add(PickingItem(
            picking_id=picking.id,
            pedido_detalle_id=detalle.DetalleID,
            estado="pendiente",
            cantidad_encontrada=None,
            producto_sustituto_id=None,
            notas=None,
        ))

    return pedido


def main() -> int:
    app = create_app()

    with app.app_context():
        conectar_bd1()
        session = get_db()
        run_tag = build_run_tag()

        try:
            categoria = ensure_categoria(session)
            producto_1 = ensure_producto(session, categoria, "Demo Tomate Frito", "3.50", 100, "A-01")
            producto_2 = ensure_producto(session, categoria, "Demo Pasta Fresca", "4.20", 100, "A-02")
            producto_3 = ensure_producto(session, categoria, "Demo Queso Curado", "5.80", 100, "A-03")

            pedidos = [
                seed_paid_order(session, 1, run_tag, [(producto_1, 2), (producto_2, 1)]),
                seed_paid_order(session, 2, run_tag, [(producto_2, 2), (producto_3, 1)]),
                seed_paid_order(session, 3, run_tag, [(producto_1, 1), (producto_3, 2)]),
                seed_paid_order(session, 4, run_tag, [(producto_1, 1), (producto_2, 1), (producto_3, 1)]),
            ]

            session.commit()

            print(f"Pedidos demo pagados listos para run_tag={run_tag}:")
            for pedido in pedidos:
                print(f"  - Pedido #{pedido.PedidoID}: estado={pedido.Estado} total={pedido.Total} cliente_id={pedido.ClienteID}")
        except Exception:
            session.rollback()
            raise

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
