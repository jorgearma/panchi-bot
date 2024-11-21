from utils.mensajes import enviar_mensaje_whatsapp

class Carrito:
    def __init__(self):
        self.carrito = {}

    def inicializar_carrito(self, numero_cliente):
        self.carrito[numero_cliente] = []

    def obtener_carrito_cliente(self, numero_cliente):
        return self.carrito.get(numero_cliente, None)
        
    def agregar_productos(self, numero_whatsapp, productos):
        if numero_whatsapp in self.carrito:
            self.carrito[numero_whatsapp].extend(productos)
        else:
            self.carrito[numero_whatsapp] = productos    

    def calcular_total(self, carrito_cliente):
        return sum(item[1] for item in carrito_cliente)

    def mostrar_carrito_sin_mensaje(self, carrito):
        if not carrito:
            return "Tu carrito está vacío.\n", 0
        
        total = self.calcular_total(carrito)
        resultado = "\n _⬇️ *Este es tu pedido* ⬇️_ \n\n"
        for item, precio in carrito:
            resultado += f" ▪️ {item}: *€{precio:.2f}*\n"
        resultado += f"\nTotal a pagar: *€{total:.2f}*\n"
        resultado += f"➖➖➖➖➖➖➖➖➖➖\n"
        
        return resultado, total

    def mostrar_carrito(self, carrito):
        resultado, total = self.mostrar_carrito_sin_mensaje(carrito)
        resultado += "\n ❗¿Algo más?❗Escribe📝\n👉 el *NUMERO* o su *NOMBRE*\n\n❗¿ya estás list@?❗Escribe📝\n👉 *PAGAR* 👈 para continuar "
        return resultado, total

    def verificar_palabras_clave(self, mensaje_cliente, palabras_clave):
        mensaje_cliente = mensaje_cliente.lower()
        return any(palabra in mensaje_cliente for palabra in palabras_clave)

    def verificar_carrito(self, numero_cliente):
        return numero_cliente in self.carrito

    def obtener_contenido_carrito(self, numero_cliente):
        if self.verificar_carrito(numero_cliente):
            return self.mostrar_carrito(self.carrito[numero_cliente])
        else:
            return "Tu carrito está vacío."

    def enviar_respuesta_carrito(self, contenido, numero_cliente):
        enviar_mensaje_whatsapp(contenido, numero_cliente)

    def es_consulta_carrito(self, mensaje_cliente):
        palabras_clave = ["revisar pedido", "ver carrito", "revisar", "carrito"]
        return self.verificar_palabras_clave(mensaje_cliente, palabras_clave)

    def procesar_consulta_carrito(self, numero_cliente):
        contenido_carrito = self.obtener_contenido_carrito(numero_cliente)
        self.enviar_respuesta_carrito(contenido_carrito, numero_cliente)

    def eliminar_carrito(self, numero_cliente):
        if numero_cliente in self.carrito:
            del self.carrito[numero_cliente]    

    def manejar_consulta_carrito(self, mensaje_cliente, numero_cliente):
        if self.es_consulta_carrito(mensaje_cliente):
            self.procesar_consulta_carrito(numero_cliente)
            return True
        return False

# Instancia global de Carrito
carrito_instancia = Carrito()

# Funciones globales para compatibilidad
def inicializar_carrito(numero_cliente):
    carrito_instancia.inicializar_carrito(numero_cliente)

def calcular_total(carrito_cliente):
    return carrito_instancia.calcular_total(carrito_cliente)

def mostrar_carrito_sin_mensaje(carrito):
    return carrito_instancia.mostrar_carrito_sin_mensaje(carrito)

def mostrar_carrito(carrito):
    return carrito_instancia.mostrar_carrito(carrito)

def verificar_palabras_clave(mensaje_cliente, palabras_clave):
    return carrito_instancia.verificar_palabras_clave(mensaje_cliente, palabras_clave)

def verificar_carrito(numero_cliente, carrito):
    return carrito_instancia.verificar_carrito(numero_cliente)

def obtener_contenido_carrito(numero_cliente, carrito):
    return carrito_instancia.obtener_contenido_carrito(numero_cliente)

def enviar_respuesta_carrito(contenido, numero_cliente):
    carrito_instancia.enviar_respuesta_carrito(contenido, numero_cliente)

def es_consulta_carrito(mensaje_cliente):
    return carrito_instancia.es_consulta_carrito(mensaje_cliente)

def procesar_consulta_carrito(numero_cliente, carrito):
    carrito_instancia.procesar_consulta_carrito(numero_cliente)

def manejar_consulta_carrito(mensaje_cliente, numero_cliente, carrito):
    return carrito_instancia.manejar_consulta_carrito(mensaje_cliente, numero_cliente)