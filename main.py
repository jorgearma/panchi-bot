from menu import mostrar_menu, procesar_pedido, mostrar_carrito
from openai_api import obtener_respuesta_openai

# Simulamos una "base de datos" de usuarios registrados. 
# Nos aseguramos de que los números estén almacenados como cadenas de texto (str).
usuarios_registrados = {
    "123": {"nombre": "Juan", "numero": "123", "direccion": "Calle Falsa 123"},
    # Puedes agregar más usuarios registrados aquí.
}

# Función para registrar un nuevo usuario
def registrar_usuario(numero):
    print("\nNo estás registrado, por favor proporciona tus datos para continuar.")
    nombre = input("Por favor, ingresa tu nombre: ")
    direccion = input("Ingresa tu dirección: ")
    
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

def mostrar_instrucciones():
    print("\n*Opciones disponibles:*")
    print("- Escribe el *nombre del producto* para agregarlo al carrito.")
    print("- Escribe *'ver carrito'* o *'revisar pedido'* para ver los productos.")
    print("- Escribe *'pagar'* para finalizar la compra.")

def camarero_bot():
    print("¡Bienvenido al restaurante! Soy su camarero virtual.")
    
    # Comprobamos si el usuario ya está registrado
    usuario = comprobar_usuario()
    
    print("\nAquí tienes nuestro menú:\n")
    mostrar_menu()
    
    carrito = []
    
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
            respuesta_openai = obtener_respuesta_openai(cliente_input)
            print(f"Camarero: {respuesta_openai}")
            
        else:
            print(f"Camarero: {respuesta_camarero}")
            if "Has agregado" in respuesta_camarero:
                mostrar_carrito(carrito)

# Ejecuta el bot
if __name__ == "__main__":
    camarero_bot()
