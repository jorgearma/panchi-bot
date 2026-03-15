import logging
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from models import Usuario
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

logger = logging.getLogger(__name__)

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
            logger.error("Error al obtener el usuario: %s", e)
            return None

    def guardar_usuario(self, numero_cliente, nombre, direccion):
        """Guarda un nuevo usuario en la base de datos."""
        try:
            nuevo_usuario = Usuario(numero_cliente=numero_cliente, nombre=nombre, direccion=direccion)
            self.session.add(nuevo_usuario)
            self.session.commit()
            logger.info("Usuario %s guardado en la base de datos.", nombre)
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error("Error al guardar el usuario en la base de datos: %s", e)

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
            logger.error("Error de conexión al verificar el usuario: %s", op_err)
            raise
        except SQLAlchemyError as e:
            logger.error("Error al verificar el usuario: %s", e)
            raise
        
