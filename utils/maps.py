import urllib.parse

def generar_enlace_google_maps(direccion):
    direccion_codificada = urllib.parse.quote(direccion)
    url = f"https://www.google.com/maps/place/{direccion_codificada},+16400+Taranc%C3%B3n,+Cuenca,+Espa%C3%B1a/"
    return url
