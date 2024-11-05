import urllib.parse

def generar_enlace_google_maps(direccion):
    direccion_codificada = urllib.parse.quote(direccion)
    url = f"https://www.google.com/maps/place/{direccion_codificada},+16400+Taranc%C3%B3n,+Cuenca,+Espa%C3%B1a/"
    return url


import requests

def validar_direccion(direccion):
    api_key = 'AIzaSyBkKYaPKMICRDfY95r9kp0NSmeXXRMb458'  # Reemplaza con tu clave de API de Google Maps
    direccion_codificada = urllib.parse.quote(direccion)
    url = f'https://maps.googleapis.com/maps/api/geocode/json?address={direccion_codificada}&key={api_key}'
    
    response = requests.get(url)
    if response.status_code == 200:
        datos = response.json()
        if datos['status'] == 'OK' and len(datos['results']) > 0:
            # La dirección es válida si la API devuelve resultados
            print("La dirección es válida:", datos['results'][0]['formatted_address'])
            return True
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

