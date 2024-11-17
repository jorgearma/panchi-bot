# data/pedidos.py
from database import conectar_bd
import json
from utils.mensajes import enviar_mensaje_whatsapp

def enviar_comanda_a_cocina(id_pedido, contenido_pedido):
    # Serializa el contenido a JSON
    contenido_serializado = json.dumps(contenido_pedido)

    with conectar_bd() as conn:
        with conn.cursor() as cur:
            try:
                # Inserta la comanda en la base de datos

                cur.execute("""
                    INSERT INTO comandas (id_pedido, contenido)
                    VALUES (?, ?);
                """, (id_pedido, contenido_serializado))
                conn.commit()
                print(f"Comanda #{id_pedido} enviada a la cocina: {contenido_pedido}")

            except Exception as e:
                print("Error al enviar la comanda a la cocina:", e)





def verificar_pedido_activo(numero_cliente, mensaje_cliente, pedidos_activos):
    """
    Verifica si un cliente tiene un pedido activo con el identificador proporcionado.

    Args:
        numero_cliente (str): Número de teléfono del cliente.
        mensaje_cliente (str): Mensaje recibido del cliente (posible ID del pedido).
        pedidos_activos (dict): Diccionario con los pedidos activos de los clientes.

    Returns:
        tuple: Mensaje de respuesta y código HTTP.
    """
    if mensaje_cliente.isdigit() and len(mensaje_cliente) == 4:
        id_pedido_cliente = int(mensaje_cliente)
        pedido_cliente = pedidos_activos.get(numero_cliente)

        # Verificar si el identificador corresponde a un pedido activo del cliente
        if pedido_cliente and pedido_cliente["id_pedido"] == id_pedido_cliente:
            enviar_mensaje_whatsapp(f"Su pedido #{id_pedido_cliente} está en preparación.", numero_cliente)
        else:
            enviar_mensaje_whatsapp("No se encontró ningún pedido con ese identificador.", numero_cliente)
        return "Mensaje enviado", 200

    return None  # No se trata de un ID de pedido válido

