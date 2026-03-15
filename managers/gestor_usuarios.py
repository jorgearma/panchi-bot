from sqlalchemy.exc import SQLAlchemyError, OperationalError
from models import Usuario
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

class GestorUsuarios:

    @property
    def session(self):
        from database import get_db
        return get_db()
       

    def obtener_usuario(self, numero_cliente):
        """Recupera un usuario dando su número de cliente."""
        try:
            usuario = self.session.query(Usuario).filter_by(numero_cliente=numero_cliente).first()
            if usuario:
                return {
                    "nombre": usuario.nombre,
                    "numero": usuario.numero_cliente,
                    "direccion": usuario.direccion
                }
            return None
        except SQLAlchemyError as e:
            print("Error al obtener el usuario:", e)
            return None

    def guardar_usuario(self, numero_cliente, nombre, direccion):
        """Guarda un nuevo usuario en la base de datos."""
        try:
            nuevo_usuario = Usuario(numero_cliente=numero_cliente, nombre=nombre, direccion=direccion)  # Crear una instancia del modelo
            self.session.add(nuevo_usuario)
            self.session.commit()
            print(f"Usuario {nombre} guardado en la base de datos.")
        except SQLAlchemyError as e:
            self.session.rollback()
            print("Error al guardar el usuario en la base de datos:", e)

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1), retry=retry_if_exception_type(SQLAlchemyError))
    def obtener_usuario_completo(self, numero_cliente):
        """Recupera un usuario completo, incluyendo su id, dado su número de cliente."""
        usuario = self.session.query(Usuario).filter_by(numero_cliente=numero_cliente).first()
        if usuario:
            return {
                "id": usuario.id,
                "nombre": usuario.nombre,
                "numero": usuario.numero_cliente,
                "direccion": usuario.direccion
            }
        return None
    
    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1), retry=retry_if_exception_type(SQLAlchemyError))
    def verificar_usuario(self, numero_cliente):

        try:
            usuario = self.session.query(Usuario).filter_by(numero_cliente=numero_cliente).scalar()
            # Si no se encontró usuario, se retorna None
            return usuario  
        except OperationalError as op_err:
            # Error de conexión (o similar)
            print("Error de conexión al verificar el usuario:", op_err)
            # Se relanza la excepción para que el decorador realice los reintentos
            raise
        except SQLAlchemyError as e:
            print("Error al verificar el usuario:", e)
            raise
        
