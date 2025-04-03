
import os
import re
import requests
import urllib.parse
from dotenv import load_dotenv
import logging

load_dotenv()

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constantes configurables
API_KEY =  "AIzaSyAwDIKTLh1gO4Z9jp_zf-B4bZUIgzEQxN4"
BASE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
LOCALITY = "Tarancón"
REGION = "Cuenca"
VALID_GENERAL_ADDRESSES = [
    f"{LOCALITY}, {REGION}, Spain",
    f"{REGION}, Spain"
]

def limpiar_direccion(direccion):
    """Limpia y normaliza la dirección."""
    direccion = re.sub(r"\bpaseo\s+de\s+la\s+estacion\b|\bpaseo\s+la\s+estacion\b", "paseo estación", direccion, flags=re.IGNORECASE)
    direccion = re.sub(r"\bportal\b", "", direccion, flags=re.IGNORECASE)
    logger.info("Dirección normalizada: %s", direccion)
    return direccion

def construir_url(direccion):
    """Construye la URL para la API de Google Maps."""
    direccion_codificada = urllib.parse.quote(direccion)
    return f"{BASE_URL}?address={direccion_codificada},+16400+{LOCALITY},+{REGION},+España&key={API_KEY}"

from shapely.geometry import Point, Polygon

# Define el polígono de Tarancón usando las coordenadas proporcionadas
TARANCON_POLYGON = Polygon([
    (-3.019209905495245, 40.01775348398729),
    (-3.008857569574019, 40.01933348021197),
    (-2.9983947104945514, 40.01594772921979),
    (-2.9985052336542424, 40.012138558560025),
    (-3.0010472663179826, 40.00993760749759),
    (-3.0011946305308754, 40.007256866114204),
    (-3.0001630810435245, 40.00412449808081),
    (-2.9960368830968775, 40.00237482454909),
    (-2.9979894589105527, 39.999609120097006),
    (-3.018694130751527, 40.00178218302548),
    (-3.0234834676546996, 40.00793411598124),
    (-3.0245150171406863, 40.017358479214664),
    (-3.0191362233887844, 40.01775348398729)
])

def validar_coordenadas(coordenadas):
    """Valida si las coordenadas están dentro de los límites de Tarancón."""
    punto = Point(coordenadas['lng'], coordenadas['lat'])
    return TARANCON_POLYGON.contains(punto)

TIPOS_VALIDOS = {"street_address", "premise", "subpremise"}

def validar_direccion(direccion):
    """
    Valida si una dirección existe, es válida y está en el pueblo especificado.
    """
    direccion_limpia = limpiar_direccion(direccion)
    url = construir_url(direccion_limpia)

    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        datos = response.json()

        if datos.get('status') != 'OK' or not datos.get('results'):
            logger.warning("Dirección no válida o no encontrada: %s", datos.get('status'))
            return False, None

        resultado = datos['results'][0]
        direccion_formateada = resultado['formatted_address']
        coordenadas = resultado['geometry']['location']  # Obtiene latitud y longitud

        # Validar si las coordenadas están dentro de Tarancón
        if not validar_coordenadas(coordenadas):
            logger.warning("Dirección fuera de los límites de Tarancón: %s", direccion_formateada)
            return False, direccion_formateada

        # Validar si la dirección es demasiado general
        if direccion_formateada in VALID_GENERAL_ADDRESSES:
            logger.warning("Dirección demasiado general: %s", direccion_formateada)
            return False, None

        # Validar si la dirección es específica
        if not any(tipo in resultado.get("types", []) for tipo in TIPOS_VALIDOS):
            logger.warning("La dirección no parece ser específica: %s", resultado.get("types"))
            return False, direccion_formateada

        logger.info("Dirección válida: %s", direccion_formateada)
        return True, direccion_formateada

    except requests.exceptions.RequestException as e:
        logger.error("Error al conectar con la API de Google Maps: %s", e)
        return False, None

