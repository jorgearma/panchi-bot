from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, DECIMAL ,Boolean
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
    Estado = Column(String(20), default='Pendiente')
    Total = Column(DECIMAL(18, 2), default=0.0)
    DireccionEntrega = Column(String(255), nullable=False)
    TelefonoEntrega = Column(String(50), nullable=False)
    enlace = Column(String(255), nullable=True)
    redisID = Column(String(255), nullable=True)

    cliente = relationship("Usuario", back_populates="pedidos")  
    detalles = relationship("PedidoDetalle", back_populates="pedido", cascade="all, delete-orphan")  # ✅ Relación agregada

class PedidoDetalle(Base):
    __tablename__ = 'pedido_detalles'  # ✅ Cambiado a minúsculas
    
    DetalleID = Column(Integer, primary_key=True, autoincrement=True)
    PedidoID = Column(Integer, ForeignKey('pedidos.PedidoID'), nullable=False)
    ProductoID = Column(Integer, ForeignKey('productos.ProductoID'), nullable=False)  # ✅ Corregido el nombre de la tabla
    Cantidad = Column(Integer, nullable=False)
    Subtotal = Column(DECIMAL(18, 2), nullable=False)
    
    pedido = relationship("Pedido", back_populates="detalles")
    producto = relationship("Producto", back_populates="detalles")  


from datetime import datetime

class Producto(Base):
    __tablename__ = 'productos'

    ProductoID = Column(Integer, primary_key=True, autoincrement=True)
    Nombre = Column(String(255), nullable=False, unique=True)
    Precio = Column(DECIMAL(10, 2), nullable=False)
    Categoria = Column(String(50), nullable=False)
    Ingredientes = Column(String(255), nullable=True)
    Ubicacion = Column(String(255), nullable=True)
    Stock = Column(Integer, nullable=False, default=0)
    ImagenURL = Column(String(255), nullable=True)
    Descripcion = Column(String(500), nullable=True)
    Descuento = Column(DECIMAL(10, 2), nullable=True, default=0.00)
    Disponible = Column(Boolean, default=True)
    

    detalles = relationship("PedidoDetalle", back_populates="producto", cascade="all, delete-orphan")
  

class Empleado(Base):
    __tablename__ = 'empleados'

    EmpleadoID = Column(Integer, primary_key=True, autoincrement=True)
    Nombre = Column(String(255), nullable=False)
    Apellido = Column(String(255), nullable=False)
    Email = Column(String(255), nullable=False, unique=True)
    Telefono = Column(String(50), nullable=True)
    Direccion = Column(String(255), nullable=True)
    Puesto = Column(String(100), nullable=False)  # Ej: Repartidor, Cajero, Administrador
    Salario = Column(DECIMAL(10, 2), nullable=False, default=0.00)