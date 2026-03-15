import os
import redis
import logging
from tenacity import retry, wait_fixed, stop_after_attempt
import json

logger = logging.getLogger(__name__)

class RedisManager:
    def __init__(self, host='localhost', port=6379, db=0):

        try:
            self.client = redis.Redis(
                host=host,
                port=port,
                db=db,
                socket_timeout=3,            # ⏱ Tiempo máx esperando respuesta
                socket_connect_timeout=3,    # ⏱ Tiempo máx conectando
                retry_on_timeout=True        # 🔁 Intenta de nuevo si hay timeout
            )
            self.client.ping()
            logger.info("✅ Conexión exitosa a Redis")
        except redis.RedisError as e:
            logger.error("❌ Error al conectar a Redis: %s", e)
            raise Exception("Error al conectar a Redis") from e
        
    def get(self, key):
        try:
            return self.client.get(key)
        except redis.RedisError as e:
            logger.error("Error al obtener la clave %s: %s", key, e)
            return None

    @retry(wait=wait_fixed(2), stop=stop_after_attempt(3))
    def set(self, key, value, ex=None):
        """
        Intenta establecer la clave en Redis. Si falla de forma transitoria, reintenta la operación.
        Si después de 3 intentos la operación sigue fallando, lanza Exception.
        """
        try:
            result = self.client.set(key, value, ex=ex)
            if not result:
                raise Exception(f"No se pudo establecer la clave {key}")
            return result
        except redis.RedisError as e:
            logger.error("Error al establecer la clave %s: %s", key, e)
            raise Exception("Error en operación SET") from e

    @retry(wait=wait_fixed(2), stop=stop_after_attempt(3))
    def delete(self, key):
        """
        Intenta eliminar la clave en Redis. Se reintenta en caso de error.
        Si la clave no existe, se registra una advertencia.
        """
        try:
            result = self.client.delete(key)
            if result == 0:
                logger.warning("No se encontró la clave %s para eliminar", key)
            return result
        except redis.RedisError as e:
            logger.error("Error al eliminar la clave %s: %s", key, e)
            raise Exception("Error en operación DELETE") from e

    def esta_bloqueado(self, numero):
        key = f"bloqueo:{numero}"
        bloqueado = self.get(key)
        return bloqueado is not None

    def bloquear_usuario(self, numero, duracion=None):
        """
        Bloquea un usuario. Opcionalmente se puede definir una duración (en segundos)
        para que el bloqueo expire automáticamente.
        """
        key = f"bloqueo:{numero}"
        print(f"Bloqueando usuario {numero} por {duracion} segundos")
        return self.set(key, "1", ex=duracion)

    def desbloquear_usuario(self, numero):
        key = f"bloqueo:{numero}"
        print(f"Desbloqueando usuario {numero}")
        return self.delete(key) 





class EstadoUsuario:
    """Clase para gestionar el estado del usuario usando Redis."""
    def __init__(self, numero_cliente, redismanager):
        """
        Constructor de EstadoUsuario.
        :param numero_cliente: Identificador único del cliente.
        :param redismanager: Instancia de RedisManager para interactuar con Redis.
        """
        self.numero_cliente = numero_cliente
        self.redismanager = redismanager

    @retry(wait=wait_fixed(2), stop=stop_after_attempt(3))
    def obtener_estado(self):
        try:
            estado = self.redismanager.get(self.numero_cliente)
        except Exception as e:
            raise Exception("Error al obtener el estado del usuario desde Redis") from e

        if estado:
            try:
                return json.loads(estado)
            except json.JSONDecodeError as e:
                raise Exception("Error al decodificar el estado del usuario") from e
        # Si no hay estado, se retorna un estado por defecto.
        return {"estado": "saludo_inicial"}

    @retry(wait=wait_fixed(2), stop=stop_after_attempt(3))
    def actualizar_estado(self, nuevo_estado, datos_adicionales=None):
        try:
            estado_actual = self.obtener_estado()
        except Exception as e:
            raise Exception("Error al obtener el estado actual del usuario") from e

        estado_actual["estado"] = nuevo_estado
        if datos_adicionales:
            estado_actual.update(datos_adicionales)
        try:
            self.redismanager.set(self.numero_cliente, json.dumps(estado_actual))
        except Exception as e:
            raise Exception("Error al actualizar el estado del usuario en Redis") from e


redismanager = RedisManager(
    host=os.environ.get('REDIS_HOST', 'localhost'),
    port=int(os.environ.get('REDIS_PORT', 6379)),
    db=int(os.environ.get('REDIS_DB', 0)),
)
  


