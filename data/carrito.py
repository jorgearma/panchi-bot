carrito = {}

import pyodbc
from database import conectar_bd


import pyodbc
from database import conectar_bd

def guardar_pedido(numero_cliente, carrito, id_pedido):
    """Guarda el pedido y sus detalles en la base de datos utilizando el número de WhatsApp."""
    
    if not numero_cliente:
        print("El número de WhatsApp no está registrado en la tabla de usuarios.")
        return
    
    connection = conectar_bd()
    cursor = None
    total = sum(item[1] for item in carrito[numero_cliente])  # Calcula el total sumando los precios
    
    try:
        if connection:
            cursor = connection.cursor()
            print(f"Inserting into pedidos: numero_cliente={numero_cliente}, total={total}")
            
            # Asegúrate de que id_pedido es un entero y numero_cliente es un string
            cursor.execute("""
                INSERT INTO pedidos (id_pedido, numero_cliente, total)
                VALUES (?, ?, ?)
            """, (id_pedido, numero_cliente, total))  # Inserción correcta
            
            connection.commit()  # Confirma el pedido
            
            # Inserta cada producto del carrito en la tabla DetallePedido
            for producto_nombre, precio in carrito[numero_cliente]:
                print(f"Inserting into detalle_pedido: id_pedido={id_pedido}, producto_nombre={producto_nombre}, precio={precio}, cantidad=1")
                cursor.execute("""
                    INSERT INTO detalle_pedido (id_pedido, producto_nombre, precio, cantidad)
                    VALUES (?, ?, ?, ?)
                """, (id_pedido, producto_nombre, precio, 1))  # Asumimos cantidad 1
            
            connection.commit()  # Confirma todos los cambios
            print("Pedido y detalles guardados exitosamente.")
    
    except Exception as e:
        if connection:
            connection.rollback()  # Revertir cambios en caso de error
        print("Error al guardar el pedido en la base de datos:", e)
    
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()
