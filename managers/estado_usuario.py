import json
import logging
from tenacity import retry, wait_fixed, stop_after_attempt
from states import EstadoRegistro, transicion_valida_registro

logger = logging.getLogger(__name__)


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
        return {"estado": EstadoRegistro.SALUDO_INICIAL}

    @retry(wait=wait_fixed(2), stop=stop_after_attempt(3))
    def actualizar_estado(self, nuevo_estado, datos_adicionales=None):
        try:
            estado_actual = self.obtener_estado()
        except Exception as e:
            raise Exception("Error al obtener el estado actual del usuario") from e

        estado_origen = estado_actual["estado"]
        if not transicion_valida_registro(estado_origen, nuevo_estado):
            logger.error(
                "Transición de registro inválida: %s → %s (usuario %s)",
                estado_origen, nuevo_estado, self.numero_cliente,
            )
            raise ValueError(
                f"Transición de registro inválida: {estado_origen} → {nuevo_estado}"
            )

        estado_actual["estado"] = nuevo_estado
        if datos_adicionales:
            estado_actual.update(datos_adicionales)
        try:
            self.redismanager.set(self.numero_cliente, json.dumps(estado_actual))
        except Exception as e:
            raise Exception("Error al actualizar el estado del usuario en Redis") from e
