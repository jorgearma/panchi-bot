import json
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, DECIMAL, Boolean, Text, Float, Date, Time
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


# ---------------------------------------------------------------------------
# Clientes / Usuarios
# ---------------------------------------------------------------------------

class Usuario(Base):
    __tablename__ = 'usuarios'
    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(255), nullable=False)
    numero_cliente = Column(String(50), nullable=False, unique=True)
    direccion = Column(String(255), nullable=True)

    pedidos = relationship("Pedido", back_populates="cliente", cascade="all, delete-orphan")
    incidencias = relationship("Incidencia", back_populates="cliente")


# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------

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
    categoria_id = Column(Integer, ForeignKey('categorias.id'), nullable=True)
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


# ---------------------------------------------------------------------------
# Pedidos
# ---------------------------------------------------------------------------

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
    forma_pago = Column(String(20), nullable=True, default='online')  # online | efectivo | tarjeta
    lat_entrega = Column(Float, nullable=True)
    lng_entrega = Column(Float, nullable=True)
    cancel_reason = Column(String(50), nullable=True)
    cancelled_by = Column(Integer, ForeignKey('empleados.EmpleadoID'), nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    Notas = Column(String(300), nullable=True)

    cliente = relationship("Usuario", back_populates="pedidos")
    detalles = relationship("PedidoDetalle", back_populates="pedido", cascade="all, delete-orphan")
    pagos = relationship("Pago", back_populates="pedido")
    historial_estados = relationship("HistorialEstadoPedido", back_populates="pedido", order_by="HistorialEstadoPedido.cambiado_en")
    picking = relationship("PickingPedido", back_populates="pedido", uselist=False)
    reparto = relationship("Reparto", back_populates="pedido", uselist=False)
    incidencias = relationship("Incidencia", back_populates="pedido")


class PedidoDetalle(Base):
    __tablename__ = 'pedido_detalles'

    DetalleID = Column(Integer, primary_key=True, autoincrement=True)
    PedidoID = Column(Integer, ForeignKey('pedidos.PedidoID'), nullable=False)
    ProductoID = Column(Integer, ForeignKey('productos.ProductoID'), nullable=False)
    Cantidad = Column(Integer, nullable=False)
    PrecioUnitario = Column(DECIMAL(10, 2), nullable=True)
    NombreProducto = Column(String(255), nullable=True)
    Subtotal = Column(DECIMAL(18, 2), nullable=False)

    pedido = relationship("Pedido", back_populates="detalles")
    producto = relationship("Producto", back_populates="detalles")
    picking_item = relationship("PickingItem", back_populates="pedido_detalle", uselist=False)


# ---------------------------------------------------------------------------
# Pagos y auditoría
# ---------------------------------------------------------------------------

class Pago(Base):
    """Registro de cada pago procesado. Un pedido puede tener múltiples intentos."""
    __tablename__ = 'pagos'

    id = Column(Integer, primary_key=True, autoincrement=True)
    pedido_id = Column(Integer, ForeignKey('pedidos.PedidoID'), nullable=False)
    proveedor = Column(String(50), nullable=False, default='monei')
    referencia_externa = Column(String(255), nullable=True, unique=True)
    estado = Column(String(30), nullable=False)
    importe = Column(DECIMAL(18, 2), nullable=False)
    importe_reembolsado = Column(DECIMAL(18, 2), nullable=False, default=0.00)
    moneda = Column(String(3), nullable=False, default='EUR')
    datos_raw = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True, onupdate=datetime.utcnow)

    pedido = relationship("Pedido", back_populates="pagos")


class AuditLog(Base):
    """Registro de auditoría para cambios operativos en pedidos (cancelaciones, modificaciones de items)."""
    __tablename__ = 'audit_log'

    id = Column(Integer, primary_key=True, autoincrement=True)
    pedido_id = Column(Integer, ForeignKey('pedidos.PedidoID'), nullable=True)
    empleado_id = Column(Integer, ForeignKey('empleados.EmpleadoID'), nullable=True)
    accion = Column(String(50), nullable=False)   # cancelar_pedido, eliminar_item, sustituir_item
    detalles = Column(Text, nullable=True)         # JSON con valores anteriores/nuevos
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    pedido = relationship("Pedido", backref="audit_logs")
    empleado = relationship("Empleado")


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


# ---------------------------------------------------------------------------
# Empleados y roles
# ---------------------------------------------------------------------------

class Rol(Base):
    """Roles internos del sistema: admin, picker, repartidor, supervisor."""
    __tablename__ = 'roles'

    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(100), nullable=False, unique=True)
    descripcion = Column(String(500), nullable=True)

    empleados = relationship("Empleado", back_populates="rol")


class Empleado(Base):
    __tablename__ = 'empleados'

    EmpleadoID = Column(Integer, primary_key=True, autoincrement=True)
    rol_id = Column(Integer, ForeignKey('roles.id'), nullable=True)   # nullable hasta asignar roles
    Nombre = Column(String(255), nullable=False)
    Apellido = Column(String(255), nullable=False)
    Email = Column(String(255), nullable=False, unique=True)
    Telefono = Column(String(50), nullable=True)
    Direccion = Column(String(255), nullable=True)
    Puesto = Column(String(100), nullable=False)                       # legacy — usar rol_id en código nuevo
    Salario = Column(DECIMAL(10, 2), nullable=False, default=0.00)
    activo = Column(Boolean, nullable=False, default=True)
    estado_operativo = Column(
        String(20),
        nullable=False,
        default='desconectado',
        server_default='desconectado',
    )
    password_hash = Column(String(255), nullable=True)                 # para login en dashboard
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True, onupdate=datetime.utcnow)

    rol_activo = Column(String(20), nullable=True)     # picker | repartidor | NULL

    rol = relationship("Rol", back_populates="empleados")
    pickings = relationship("PickingPedido", back_populates="empleado")
    repartos = relationship("Reparto", back_populates="repartidor")
    incidencias_asignadas = relationship("Incidencia", back_populates="asignado", foreign_keys="Incidencia.asignado_a")
    turnos = relationship('Turno', back_populates='empleado', order_by='Turno.fecha')
    capacidades = relationship('EmpleadoCapacidad', back_populates='empleado',
                               cascade='all, delete-orphan')


class EmpleadoCapacidad(Base):
    """Roles operativos que puede desempeñar un empleado (picker, repartidor)."""
    __tablename__ = 'empleado_capacidades'

    id          = Column(Integer, primary_key=True, autoincrement=True)
    empleado_id = Column(Integer, ForeignKey('empleados.EmpleadoID'), nullable=False)
    rol         = Column(String(20), nullable=False)   # 'picker' | 'repartidor'

    empleado = relationship('Empleado', back_populates='capacidades')

    __table_args__ = (
        __import__('sqlalchemy').UniqueConstraint('empleado_id', 'rol', name='uq_empleado_rol'),
    )


# ---------------------------------------------------------------------------
# Picking (preparación en almacén)
# ---------------------------------------------------------------------------

class PickingPedido(Base):
    """Estado de preparación de un pedido en almacén. Uno por pedido."""
    __tablename__ = 'picking_pedido'

    id = Column(Integer, primary_key=True, autoincrement=True)
    pedido_id = Column(Integer, ForeignKey('pedidos.PedidoID'), nullable=False, unique=True)
    empleado_id = Column(Integer, ForeignKey('empleados.EmpleadoID'), nullable=True)
    estado = Column(String(30), nullable=False, default='pendiente')
    iniciado_en = Column(DateTime, nullable=True)
    completado_en = Column(DateTime, nullable=True)
    notas = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    pedido = relationship("Pedido", back_populates="picking")
    empleado = relationship("Empleado", back_populates="pickings")
    items = relationship("PickingItem", back_populates="picking", cascade="all, delete-orphan")


class PickingItem(Base):
    """Estado de cada línea de producto durante el picking."""
    __tablename__ = 'picking_items'

    id = Column(Integer, primary_key=True, autoincrement=True)
    picking_id = Column(Integer, ForeignKey('picking_pedido.id'), nullable=False)
    pedido_detalle_id = Column(Integer, ForeignKey('pedido_detalles.DetalleID'), nullable=False)
    estado = Column(String(30), nullable=False, default='pendiente')   # pendiente, encontrado, sin_stock, sustituido
    cantidad_encontrada = Column(Integer, nullable=True)
    producto_sustituto_id = Column(Integer, ForeignKey('productos.ProductoID'), nullable=True)
    notas = Column(String(500), nullable=True)

    picking = relationship("PickingPedido", back_populates="items")
    pedido_detalle = relationship("PedidoDetalle", back_populates="picking_item")
    producto_sustituto = relationship("Producto", foreign_keys=[producto_sustituto_id])


# ---------------------------------------------------------------------------
# Reparto / delivery
# ---------------------------------------------------------------------------

class Reparto(Base):
    """Seguimiento de la entrega de un pedido. Uno por pedido."""
    __tablename__ = 'repartos'

    id = Column(Integer, primary_key=True, autoincrement=True)
    pedido_id = Column(Integer, ForeignKey('pedidos.PedidoID'), nullable=False, unique=True)
    repartidor_id = Column(Integer, ForeignKey('empleados.EmpleadoID'), nullable=True)
    estado = Column(String(30), nullable=False, default='pendiente')
    hora_salida = Column(DateTime, nullable=True)
    hora_estimada_entrega = Column(DateTime, nullable=True)
    hora_entrega_real = Column(DateTime, nullable=True)
    motivo_no_entrega = Column(String(500), nullable=True)
    prueba_entrega_url = Column(String(500), nullable=True)
    notas = Column(String(500), nullable=True)
    # Cobro presencial — rellenado por el repartidor al confirmar el pago
    # SQL: ALTER TABLE repartos ADD metodo_cobro VARCHAR(20), importe_cobrado DECIMAL(10,2),
    #      cambio_devuelto DECIMAL(10,2), importe_efectivo DECIMAL(10,2), importe_tarjeta DECIMAL(10,2)
    metodo_cobro    = Column(String(20),       nullable=True)   # efectivo | tarjeta | mixto
    importe_cobrado = Column(DECIMAL(10, 2),   nullable=True)   # total que cobró el repartidor
    cambio_devuelto = Column(DECIMAL(10, 2),   nullable=True)   # solo efectivo: cambio devuelto
    importe_efectivo = Column(DECIMAL(10, 2),  nullable=True)   # solo mixto: parte en efectivo
    importe_tarjeta  = Column(DECIMAL(10, 2),  nullable=True)   # solo mixto: parte en tarjeta
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True, onupdate=datetime.utcnow)

    pedido = relationship("Pedido", back_populates="reparto")
    repartidor = relationship("Empleado", back_populates="repartos")


# ---------------------------------------------------------------------------
# Incidencias
# ---------------------------------------------------------------------------

class Incidencia(Base):
    """Incidencia operativa ligada a un pedido o cliente."""
    __tablename__ = 'incidencias'

    id = Column(Integer, primary_key=True, autoincrement=True)
    pedido_id = Column(Integer, ForeignKey('pedidos.PedidoID'), nullable=True)
    cliente_id = Column(Integer, ForeignKey('usuarios.id'), nullable=True)
    asignado_a = Column(Integer, ForeignKey('empleados.EmpleadoID'), nullable=True)
    tipo = Column(String(50), nullable=False)          # entrega_fallida, producto_faltante, queja_cliente...
    descripcion = Column(Text, nullable=False)
    estado = Column(String(30), nullable=False, default='abierta')    # abierta, en_proceso, resuelta, cerrada
    resolucion = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    resuelta_en = Column(DateTime, nullable=True)

    pedido = relationship("Pedido", back_populates="incidencias")
    cliente = relationship("Usuario", back_populates="incidencias")
    asignado = relationship("Empleado", back_populates="incidencias_asignadas", foreign_keys=[asignado_a])


# ---------------------------------------------------------------------------
# Turnos
# ---------------------------------------------------------------------------

class Turno(Base):
    """Turno de trabajo de un empleado en una fecha concreta."""
    __tablename__ = 'turnos'

    id          = Column(Integer, primary_key=True, autoincrement=True)
    empleado_id = Column(Integer, ForeignKey('empleados.EmpleadoID'), nullable=False)
    fecha       = Column(Date, nullable=False)
    hora_inicio = Column(Time, nullable=False)
    hora_fin    = Column(Time, nullable=False)
    notas       = Column(String(255), nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow)

    empleado = relationship('Empleado', back_populates='turnos')
