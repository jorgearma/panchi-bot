import json
from database import conectar_bd
from utils.mensajes import enviar_mensaje_whatsapp
from data.usuarios import obtener_usuario_bd , obtener_nombre_usuario , GestorUsuarios

class Pedido:
    def __init__(self):
        pass

    def enviar_comanda_a_cocina(self, id_pedido, contenido_pedido):
        contenido_serializado = json.dumps(contenido_pedido)
        with conectar_bd() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute("""
                        INSERT INTO comandas (id_pedido, contenido)
                        VALUES (?, ?);
                    """, (id_pedido, contenido_serializado))
                    conn.commit()
                    print(f"Comanda #{id_pedido} enviada a la cocina: {contenido_pedido}")
                except Exception as e:
                    print("Error al enviar la comanda a la cocina:", e)

    def verificar_pedido_activo(self, numero_cliente, mensaje_cliente, pedidos_activos):
        if mensaje_cliente.isdigit() and len(mensaje_cliente) == 4:
            id_pedido_cliente = int(mensaje_cliente)
            pedido_cliente = pedidos_activos.get(numero_cliente)
            if pedido_cliente and pedido_cliente["id_pedido"] == id_pedido_cliente:
                enviar_mensaje_whatsapp(f"Su pedido #{id_pedido_cliente} está en preparación.", numero_cliente)
            else:
                enviar_mensaje_whatsapp("No se encontró ningún pedido con ese identificador.", numero_cliente)
            return "Mensaje enviado", 200
        return None

    

class GestorPedidoDB:
    def insertar_pedido(self, cursor, id_pedido, numero_cliente, total):
        cursor.execute("""
            INSERT INTO pedidos (id_pedido, numero_cliente, total)
            VALUES (?, ?, ?)
        """, (id_pedido, numero_cliente, total))

    def insertar_detalle_pedido(self, cursor, id_pedido, carrito_cliente, nombre_usuario):
        for producto_nombre, precio in carrito_cliente:
            cursor.execute("""
                INSERT INTO detalle_pedido (id_pedido, producto_nombre, precio, cantidad, nombre_usuario)
                VALUES (?, ?, ?, ?, ?)
            """, (id_pedido, producto_nombre, precio, 1, nombre_usuario))

    def guardar_pedido(self, numero_cliente, carrito, id_pedido):
        if not numero_cliente:
            print("El número de WhatsApp no está registrado en la tabla de usuarios.")
            return
        nombre_usuario = obtener_nombre_usuario(numero_cliente)
        total = sum(item[1] for item in carrito)
        connection = conectar_bd()
        cursor = None
        try:
            if connection:
                cursor = connection.cursor()
                self.insertar_pedido(cursor, id_pedido, numero_cliente, total)
                self.insertar_detalle_pedido(cursor, id_pedido, carrito, nombre_usuario)
                connection.commit()
                print("Pedido y detalles guardados exitosamente.")
        except Exception as e:
            if connection:
                connection.rollback()
            print("Error al guardar el pedido en la base de datos:", e)
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

# Instancia de la clase Pedido
estancia_pedido = Pedido()
gestor_pedido_db = GestorPedidoDB()

# Funciones globales que llaman a los métodos de las clases Pedido y GestorPedidoDB
def enviar_comanda_a_cocina(id_pedido, contenido_pedido):
    estancia_pedido.enviar_comanda_a_cocina(id_pedido, contenido_pedido)

def verificar_pedido_activo(numero_cliente, mensaje_cliente, pedidos_activos):
    return estancia_pedido.verificar_pedido_activo(numero_cliente, mensaje_cliente, pedidos_activos)

def obtener_nombre_usuario(numero_cliente):
    return GestorUsuarios.obtener_nombre_usuario(numero_cliente)

def insertar_pedido(cursor, id_pedido, numero_cliente, total):
    gestor_pedido_db.insertar_pedido(cursor, id_pedido, numero_cliente, total)

def insertar_detalle_pedido(cursor, id_pedido, carrito_cliente, nombre_usuario):
    gestor_pedido_db.insertar_detalle_pedido(cursor, id_pedido, carrito_cliente, nombre_usuario)

def guardar_pedido(numero_cliente, carrito, id_pedido):
    gestor_pedido_db.guardar_pedido(numero_cliente, carrito, id_pedido)