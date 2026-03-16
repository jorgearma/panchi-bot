import json
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, DECIMAL, Boolean, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class Usuario(Base):
    __tablename__ = 'usuarios'
    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(255), nullable=False)
    numero_cliente = Column(String(50), nullable=False, unique=True)
    direccion = Column(String(255), nullable=True)
    pedidos = relationship("Pedido", back_populates="cliente", cascade="all, delete-orphan")


class Pedido(Base):
    __tablename__ = 'pedidos'

    PedidoID = Column(Integer, primary_key=True, autoincrement=True, nullable=False, server_default="IDENTITY(2000,1)")
    ClienteID = Column(Integer, ForeignKey('usuarios.id'), nullable=False)
    FechaCreacion = Column(DateTime, default=datetime.utcnow)
    FechaActualizacion = Column(DateTime, nullable=True, onupdate=datetime.utcnow)
    Estado = Column(String(20), default='Pendiente')
    Total = Column(DECIMAL(18, 2), default=0.0)
    DireccionEntrega = Column(String(255), nullable=False)
    TelefonoEntrega = Column(String(50), nullable=False)
    enlace = Column(String(255), nullable=True)
    redisID = Column(String(255), nullable=True)
    estadopago = Column(String(255), nullable=True)
    estadoauxiliar = Column(String(255), nullable=True)

    cliente = relationship("Usuario", back_populates="pedidos")
    detalles = relationship("PedidoDetalle", back_populates="pedido", cascade="all, delete-orphan")
    pagos = relationship("Pago", back_populates="pedido")
    historial_estados = relationship("HistorialEstadoPedido", back_populates="pedido", order_by="HistorialEstadoPedido.cambiado_en")


class PedidoDetalle(Base):
    __tablename__ = 'pedido_detalles'

    DetalleID = Column(Integer, primary_key=True, autoincrement=True)
    PedidoID = Column(Integer, ForeignKey('pedidos.PedidoID'), nullable=False)
    ProductoID = Column(Integer, ForeignKey('productos.ProductoID'), nullable=False)
    Cantidad = Column(Integer, nullable=False)
    PrecioUnitario = Column(DECIMAL(10, 2), nullable=True)   # snapshot del precio en el momento de la compra
    NombreProducto = Column(String(255), nullable=True)      # snapshot del nombre en el momento de la compra
    Subtotal = Column(DECIMAL(18, 2), nullable=False)

    pedido = relationship("Pedido", back_populates="detalles")
    producto = relationship("Producto", back_populates="detalles")


class Categoria(Base):
    __tablename__ = 'categorias'

    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(100), nullable=False, unique=True)
    orden_display = Column(Integer, nullable=False, default=0)
    activa = Column(Boolean, nullable=False, default=True)

    productos = relationship("Producto", back_populates="categoria_rel")


class Producto(Base):
    __tablename__ = 'productos'

    ProductoID = Column(Integer, primary_key=True, autoincrement=True)
    categoria_id = Column(Integer, ForeignKey('categorias.id'), nullable=True)  # nullable hasta migrar datos
    Nombre = Column(String(255), nullable=False, unique=True)
    Precio = Column(DECIMAL(10, 2), nullable=False)
    Categoria = Column(String(50), nullable=False)   # legacy — usar categoria_id en código nuevo
    Ingredientes = Column(String(255), nullable=True)
    Ubicacion = Column(String(255), nullable=True)
    Stock = Column(Integer, nullable=False, default=0)
    ImagenURL = Column(String(255), nullable=True)
    Descripcion = Column(String(500), nullable=True)
    Descuento = Column(DECIMAL(10, 2), nullable=True, default=0.00)
    Disponible = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True, onupdate=datetime.utcnow)

    categoria_rel = relationship("Categoria", back_populates="productos")
    detalles = relationship("PedidoDetalle", back_populates="producto", cascade="all, delete-orphan")


class Empleado(Base):
    __tablename__ = 'empleados'

    EmpleadoID = Column(Integer, primary_key=True, autoincrement=True)
    Nombre = Column(String(255), nullable=False)
    Apellido = Column(String(255), nullable=False)
    Email = Column(String(255), nullable=False, unique=True)
    Telefono = Column(String(50), nullable=True)
    Direccion = Column(String(255), nullable=True)
    Puesto = Column(String(100), nullable=False)
    Salario = Column(DECIMAL(10, 2), nullable=False, default=0.00)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True, onupdate=datetime.utcnow)


class Pago(Base):
    """Registro de cada pago procesado. Un pedido puede tener múltiples intentos."""
    __tablename__ = 'pagos'

    id = Column(Integer, primary_key=True, autoincrement=True)
    pedido_id = Column(Integer, ForeignKey('pedidos.PedidoID'), nullable=False)
    proveedor = Column(String(50), nullable=False, default='monei')
    referencia_externa = Column(String(255), nullable=True, unique=True)  # Monei payment ID
    estado = Column(String(30), nullable=False)                           # completado, fallido, reembolsado...
    importe = Column(DECIMAL(18, 2), nullable=False)
    importe_reembolsado = Column(DECIMAL(18, 2), nullable=False, default=0.00)
    moneda = Column(String(3), nullable=False, default='EUR')
    datos_raw = Column(Text, nullable=True)                               # payload completo del webhook
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True, onupdate=datetime.utcnow)

    pedido = relationship("Pedido", back_populates="pagos")


class HistorialEstadoPedido(Base):
    """Trazabilidad completa de cada cambio de estado de un pedido."""
    __tablename__ = 'historial_estados_pedido'

    id = Column(Integer, primary_key=True, autoincrement=True)
    pedido_id = Column(Integer, ForeignKey('pedidos.PedidoID'), nullable=False)
    estado_anterior = Column(String(30), nullable=False)
    estado_nuevo = Column(String(30), nullable=False)
    cambiado_en = Column(DateTime, default=datetime.utcnow, nullable=False)
    notas = Column(String(500), nullable=True)

    pedido = relationship("Pedido", back_populates="historial_estados")
