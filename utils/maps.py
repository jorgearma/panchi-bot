import urllib.parse

def generar_enlace_google_maps(direccion):
    direccion1 = re.sub(r"\bportal\b", "", direccion, flags=re.IGNORECASE)
    direccion_codificada = urllib.parse.quote(direccion1)
    url = f"https://www.google.com/maps/place/{direccion_codificada},+16400+Taranc%C3%B3n,+Cuenca,+Espa%C3%B1a/"
    print(url)
    return url


import requests

def validar_direccion(direccion):
    api_key = 'AIzaSyBkKYaPKMICRDfY95r9kp0NSmeXXRMb458'  # Reemplaza con tu clave de API de Google Maps
    direccion_con_localidad = direccion
    direccion_para_verificar = limpiar_direccion(direccion_con_localidad)
    direccion_codificada = urllib.parse.quote(direccion_para_verificar)

    print("Dirección limpia =", direccion_para_verificar)
    url = f'https://maps.googleapis.com/maps/api/geocode/json?address={direccion_codificada},+16400+Taranc%C3%B3n,+Cuenca,+Espa%C3%B1a/&key={api_key}'

    
    response = requests.get(url)
    if response.status_code == 200:
        datos = response.json()
        if datos['status'] == 'OK' and len(datos['results']) > 0:
            # La dirección es válida si la API devuelve resultados y está en Tarancón
            resultado = datos['results'][0]['formatted_address']
            if resultado == "16400 Tarancón, Cuenca, Spain":
                print("La dirección es demasiado general y se considera inválida.")
                return False
                
            if "Tarancón" in resultado and "Cuenca" in resultado:
                print("La dirección es válida:", resultado)
                return True
            else:
                print("La dirección no está en Tarancón, Cuenca.")
                return False
        elif datos['status'] == 'ZERO_RESULTS':
            # La dirección no es válida
            print("La dirección no es válida.")
            return False
        else:
            print("Error en la solicitud:", datos['status'])
            return False
    else:
        print("Error en la conexión a la API.")
        return False

import re

def limpiar_direccion(direccion):
    # Removemos la palabra "portal" si aparece en la dirección
    direccion = re.sub(r"\bportal\b", "", direccion, flags=re.IGNORECASE)
    
    # Utilizamos una expresión regular para capturar el nombre de la calle y el número del portal
    match = re.match(r"(.+?)\s+(\d+)", direccion)
    
    if match:
        # El primer grupo es el nombre de la calle y el segundo es el número del portal
        calle = match.group(1)
        numero_portal = match.group(2)
        # Combinamos calle y número para obtener la dirección limpia
        direccion_limpia = f"{calle.strip()} {numero_portal}"
        return direccion_limpia
    else:
        # Si no hay coincidencias, devolvemos la dirección original (o un mensaje de error)
        return direccion.strip()