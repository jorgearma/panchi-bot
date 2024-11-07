import urllib.parse

def generar_enlace_google_maps(direccion):
    direccion1 = re.sub(r"\bportal\b", "", direccion, flags=re.IGNORECASE)
    direccion_codificada = urllib.parse.quote(direccion1)
    url = f"https://www.google.com/maps/place/{direccion_codificada},+16400+Taranc%C3%B3n,+Cuenca,+Espa%C3%B1a/"
    print(url)
    return url##


import requests

def validar_direccion(direccion):
    api_key = 'AIzaSyBkKYaPKMICRDfY95r9kp0NSmeXXRMb458'  # Reemplaza con tu clave de API de Google Maps
    direccion = re.sub(r"\bpaseo\s+de\s+la\s+estacion\b|\bpaseo\s+la\s+estacion\b", "paseo estación", direccion, flags=re.IGNORECASE)
    print("Dirección después de reemplazo de 'paseo de la estación' =", direccion)
    direccion_para_verificar = re.sub(r"\bportal\b", "", direccion, flags=re.IGNORECASE)
    direccion_codificada = urllib.parse.quote(direccion_para_verificar)

    print("Dirección limpia =", direccion_para_verificar)
    url = f'https://maps.googleapis.com/maps/api/geocode/json?address={direccion_codificada},+16400+Taranc%C3%B3n,+Cuenca,+Espa%C3%B1a/&key={api_key}'
    print("url ",url)
    response = requests.get(url)
    if response.status_code == 200:
        datos = response.json()
        if datos['status'] == 'OK' and len(datos['results']) > 0:
            resultado = datos['results'][0]['formatted_address']
            if resultado == "16400 Tarancón, Cuenca, Spain" or resultado =="Tarancón, 16400, Cuenca, Spain":
                print("La dirección es demasiado general y se considera inválida.")
                return False, None  # Retorna False y None cuando la dirección es demasiado general
                
            if "Tarancón" in resultado and "Cuenca" in resultado:
                print("La dirección es válida:", resultado)
                return True, resultado  # Retorna True y la dirección cuando es válida
            else:
                print("La dirección no está en Tarancón, Cuenca.")
                return False, resultado  # Retorna False y la dirección cuando no es válida
        elif datos['status'] == 'ZERO_RESULTS':
            print("La dirección no es válida.")
            return False, None  # Retorna False y None si no hay resultados
        else:
            print("Error en la solicitud:", datos['status'])
            return False, None  # Retorna False y None en caso de error en la solicitud
    else:
        print("Error en la conexión a la API.")
        return False, None  # Retorna False y None si hay un problema con la conexión


import re 
