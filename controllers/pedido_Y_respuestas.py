from openai_api import obtener_respuesta_openai
from menu import mostrar_menu, procesar_pedido
from utils.mensajes import enviar_mensaje_whatsapp
from data.carrito import  mostrar_carrito , carrito_instancia

#aqui proceso los posibles problemas que puedan surgir  en al elecion del menu  como malos comandos 
def procesar_mensaje_como_pedido(mensaje_cliente, numero_cliente):
    menu_comando_no_reconocido = mostrar_menu()
    respuesta_camarero = procesar_pedido(mensaje_cliente , numero_cliente )
    
    if "no reconocí ningún ítem" in respuesta_camarero:
        respuesta_openai = "❌Comando no reconosido❌ \n   ▪️Elija un restaurante▪️"  #obtener_respuesta_openai(mensaje_cliente, carrito_cliente)
        enviar_mensaje_whatsapp(f"{respuesta_openai} {menu_comando_no_reconocido} \nEscribe el *numero* para elegir ", numero_cliente)
    else:
        enviar_mensaje_whatsapp(f"{respuesta_camarero}", numero_cliente)
        if "Has agregado" in respuesta_camarero:
            
            print("flujo cortado revisar")
            
    return "Mensaje recibido", 200   