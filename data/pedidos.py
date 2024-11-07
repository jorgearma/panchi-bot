# data/pedidos.py
from database import conectar_bd
import json

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
