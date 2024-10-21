from menu import mostrar_menu, procesar_pedido, mostrar_carrito
from openai_api import obtener_respuesta_openai

import urllib.parse  # Para codificar la dirección en una URL

# Simulamos una "base de datos" de usuarios registrados.
usuarios_registrados = {
    "123": {"nombre": "Juan", "numero": "123", "direccion": "Calle Falsa 123"},
    # Puedes agregar más usuarios registrados aquí.
}

# Base de datos de calles válidas

# Función para generar el enlace de Google Maps a partir de una dirección
def generar_enlace_google_maps(direccion):
    direccion_codificada = urllib.parse.quote(direccion)
    url = f"https://www.google.com/maps/place/{direccion_codificada},+16400+Taranc%C3%B3n,+Cuenca,+Espa%C3%B1a/"
    return url

# Función para registrar un nuevo usuario
def registrar_usuario(numero):
    print("\nNo estás registrado, por favor proporciona tus datos para continuar.")
    nombre = input("Por favor, ingresa tu nombre: ")
    
    # Comprobación de dirección válida
    direccion = ingresar_direccion()
    
    # Guardamos los datos del nuevo usuario en nuestra "base de datos"
    usuarios_registrados[numero] = {
        "nombre": nombre,
        "numero": numero,
        "direccion": direccion
    }
    
    print(f"\n¡Gracias {nombre}! Ahora estás registrado.\n")
    return usuarios_registrados[numero]

# Función para comprobar si el usuario ya está registrado
def comprobar_usuario():
    numero = input("Por favor, ingresa tu número de teléfono: ").strip()  # Limpiamos espacios extra
    
    if numero in usuarios_registrados:
        usuario = usuarios_registrados[numero]
        print(f"\n¡Bienvenido de nuevo, {usuario['nombre']}!")
        return usuario
    else:
        return registrar_usuario(numero)

# Función para ingresar y validar la dirección
def ingresar_direccion():
    while True:
        calle = input("Ingresa el nombre de tu calle: ").strip()

        # Generamos el enlace de Google Maps
        enlace_maps = generar_enlace_google_maps(calle)
        print(f"\nAquí tienes un enlace de Google Maps con la ubicación de tu calle: {enlace_maps}")

        # Preguntamos si la dirección es correcta
        confirmacion = input("¿Es esta tu dirección? Escribe 'si' para confirmar o 'no' para volver a ingresarla: ").strip().lower()

        if confirmacion == 'si':
            print(f"\nDirección válida: {calle}")
            return calle  # Si es correcta, la retornamos
        else:
            print("\nVamos a intentar de nuevo.\n")

carrito = []

def camarero_bot():
    print("¡Bienvenido al restaurante! Soy su camarero virtual.")
    
    # Comprobamos si el usuario ya está registrado
    usuario = comprobar_usuario()
    
    print("\nAquí tienes nuestro menú:\n")
    mostrar_menu()
    
    
    
    while True:
        cliente_input = input("Cliente: ")
        
        if cliente_input.lower() in ["revisar pedido", "ver carrito", "revisar", "carrito"]:
            mostrar_carrito(carrito)
            continue
        
        if cliente_input.lower() in ["salir", "nada más", "eso es todo", "pagar"]:
            if not carrito:
                print("Camarero: No tienes ningún pedido. ¡Gracias y que tenga un buen día!")
            else:
                total = mostrar_carrito(carrito)
                confirmar = input("\n¿Te gustaría proceder al pago? (sí/no): ").lower()
                if confirmar == "sí":
                    print(f"Camarero: ¡Perfecto! El total de tu pedido es ${total:.2f}. Gracias por tu compra, {usuario['nombre']}.\nTu pedido será enviado a {usuario['direccion']}.")
                else:
                    print("Camarero: Pedido cancelado. ¡Que tenga un buen día!")
            break
        
        # Procesa el pedido
        respuesta_camarero = procesar_pedido(cliente_input, carrito)
        
        if "no reconocí ningún ítem" in respuesta_camarero:
            # Si no se reconoció un ítem, se asume que el cliente hizo una pregunta
            respuesta_openai = obtener_respuesta_openai(cliente_input,carrito)
            print(f"Camarero: {respuesta_openai}")
            
        else:
            print(f"Camarero: {respuesta_camarero}")
            if "Has agregado" in respuesta_camarero:
                mostrar_carrito(carrito)

# Ejecuta el bot
if __name__ == "__main__":
    camarero_bot()
