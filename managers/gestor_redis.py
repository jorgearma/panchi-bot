import redis
import logging
import config
from tenacity import retry, wait_fixed, stop_after_attempt

logger = logging.getLogger(__name__)

class RedisManager:
    def __init__(self, host='localhost', port=6379, db=0):
        """Inicializa la conexión con Redis y valida disponibilidad."""

        try:
            self.client = redis.Redis(
                host=host,
                port=port,
                db=db,
                password=config.REDIS_PASSWORD or None,
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
        """Recupera una clave de Redis de forma segura."""
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
                logger.debug("Clave %s no existía al eliminar (operación idempotente)", key)
            return result
        except redis.RedisError as e:
            logger.error("Error al eliminar la clave %s: %s", key, e)
            raise Exception("Error en operación DELETE") from e

    def esta_bloqueado(self, numero):
        """Comprueba si el usuario tiene un bloqueo temporal."""
        key = f"bloqueo:{numero}"
        bloqueado = self.get(key)
        return bloqueado is not None

    def bloquear_usuario(self, numero, duracion=None):
        """
        Bloquea un usuario. Opcionalmente se puede definir una duración (en segundos)
        para que el bloqueo expire automáticamente.
        """
        key = f"bloqueo:{numero}"
        logger.debug("Bloqueando usuario %s por %s segundos", numero, duracion)
        return self.set(key, "1", ex=duracion)

    def desbloquear_usuario(self, numero):
        """Elimina el bloqueo temporal de un usuario."""
        key = f"bloqueo:{numero}"
        logger.debug("Desbloqueando usuario %s", numero)
        return self.delete(key)

    def ya_procesado_wamid(self, wamid: str, ttl: int = 300) -> bool:
        """Registra el wamid atómicamente (SET NX). Devuelve True si es duplicado.

        Usa SET NX para que la comprobación y el registro sean una sola operación
        Redis — dos requests concurrentes con el mismo wamid no pueden pasar ambas.
        En caso de error Redis devuelve False: mejor procesar un duplicado que
        perder un mensaje.
        """
        key = f"wamid:{wamid}"
        try:
            resultado = self.client.set(key, "1", ex=ttl, nx=True)
            return resultado is None  # None = clave ya existía = duplicado
        except redis.RedisError as e:
            logger.error("Error al verificar wamid %s: %s", wamid, e)
            return False

    def adquirir_lock(self, key: str, ttl: int = 10) -> bool:
        """Intenta adquirir un lock atómico con SET NX. Devuelve True si se adquirió.

        Usa SET NX para que la comprobación y el registro sean una sola operación
        Redis — dos requests concurrentes con la misma clave no pueden adquirir ambas.
        En caso de error Redis devuelve False: mejor ignorar el lock que bloquear indefinidamente.
        """
        try:
            resultado = self.client.set(key, "1", ex=ttl, nx=True)
            return resultado is not None  # None = clave ya existía = lock no adquirido
        except redis.RedisError as e:
            logger.error("Error al adquirir lock %s: %s", key, e)
            return True  # fail-open: ante error Redis, dejar pasar para no bloquear al usuario


redismanager = RedisManager(
    host=config.REDIS_HOST,
    port=config.REDIS_PORT,
    db=config.REDIS_DB,
)
  

