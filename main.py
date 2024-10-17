# main.py

from menu import mostrar_menu, procesar_pedido, mostrar_carrito
from openai_api import obtener_respuesta_openai


def mostrar_instrucciones():
    print("\n*Opciones disponibles:*")
    print("- Escribe el *nombre del producto* para agregarlo al carrito.")
    print("- Escribe *'ver carrito'* o *'revisar pedido'* para ver los productos.")
    print("- Escribe *'pagar'* para finalizar la compra.")

def camarero_bot():
    print("¡Bienvenido al restaurante! Soy su camarero virtual. A continuación te muestro nuestro menú:\n")
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
                    print(f"Camarero: ¡Perfecto! El total de tu pedido es ${total:.2f}. Gracias por tu compra.")
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
