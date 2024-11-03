carrito = {}

import pyodbc


def guardar_carrito_en_bd(carrito, numero_cliente):
    connection = conectar_bd()
    cursor = None

    try:
        if connection:
            cursor = connection.cursor()

            for item, precio in carrito:
                # Suponiendo que tienes una tabla para almacenar los pedidos
                cursor.execute("""
                    INSERT INTO pedido_items (nombre, precio, cliente_id)  -- Asegúrate de que la columna cliente_id exista
                    VALUES (?, ?, ?)
                """, (item, precio, numero_cliente))
            
            connection.commit()  # Confirmar los cambios en la base de datos
    except Exception as e:
        if connection:
            connection.rollback()  # Revertir cambios en caso de error
        print("Error al guardar el carrito en la base de datos:", e)
    finally:
        if cursor:
            cursor.close()  # Cerrar el cursor
        if connection:
            connection.close()  # Cerrar la conexión
