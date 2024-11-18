carrito = {}
from data.usuarios import  obtener_usuario_bd
import pyodbc
from database import conectar_bd
from utils.mensajes import enviar_mensaje_whatsapp




def guardar_pedido(numero_cliente, carrito, id_pedido):
    """Guarda el pedido y sus detalles en la base de datos utilizando el número de WhatsApp."""
    nombre = obtener_usuario_bd(numero_cliente)
    nombre_usuario = nombre["nombre"]
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
                    INSERT INTO detalle_pedido (id_pedido, producto_nombre, precio, cantidad,nombre_usuario)
                    VALUES (?, ?, ?, ?,?)
                """, (id_pedido, producto_nombre, precio, 1, nombre_usuario))  # Asumimos cantidad 1
            
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

## funcion para mostrar el carrito

# Función para mostrar el carrito y calcular el total
def mostrar_carrito_sin_mensaje(carrito):
    if not carrito:
        return "Tu carrito está vacío.\n" , 0
    
    total = sum(precio for _, precio in carrito)
    resultado = "\n _⬇️ *Este es tu pedido* ⬇️_ \n\n"
    for item, precio in carrito:
        resultado += f" ▪️ {item}: *€{precio:.2f}*\n"
    resultado += f"\nTotal a pagar: *€{total:.2f}*\n"
    resultado += f"➖➖➖➖➖➖➖➖➖➖\n"
    
    
    return resultado, total

def mostrar_carrito(carrito):
    resultado, total = mostrar_carrito_sin_mensaje(carrito)
    resultado += "\n ❗¿Algo más?❗Escribe📝\n👉 el *NUMERO* o su *NOMBRE*\n\n❗¿ya estás list@?❗Escribe📝\n👉 *PAGAR* 👈 para continuar "
    return resultado, total

def manejar_consulta_carrito(mensaje_cliente, numero_cliente):
    mensaje_cliente = mensaje_cliente.lower()
    
    palabras_clave = ["revisar pedido", "ver carrito", "revisar", "carrito"]
    
    if mensaje_cliente in palabras_clave:
        if numero_cliente in carrito:
            contenido_carrito = mostrar_carrito(carrito[numero_cliente])
            enviar_mensaje_whatsapp(contenido_carrito, numero_cliente)
        else:
            enviar_mensaje_whatsapp("Tu carrito está vacío.", numero_cliente)
        return True
    
    return False