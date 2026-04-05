import json
import logging
import re
import urllib.parse
from pathlib import Path

import requests
from shapely.geometry import Point, Polygon
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

import config

logger = logging.getLogger(__name__)

BASE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

_TERRITORIES_PATH = Path(__file__).parent / "territories.json"
_territories_cache: dict = {}
_polygon_cache: dict = {}


def _load_territory(name: str) -> dict:
    if name not in _territories_cache:
        with open(_TERRITORIES_PATH) as f:
            data = json.load(f)
        for t in data["territories"]:
            _territories_cache[t["name"]] = t
    if name not in _territories_cache:
        raise ValueError(f"Territory '{name}' not found in configuration")
    return _territories_cache[name]


def _get_polygon(territory: str) -> Polygon:
    if territory not in _polygon_cache:
        t = _load_territory(territory)
        _polygon_cache[territory] = Polygon(t["polygon"])
    return _polygon_cache[territory]


def _apply_normalizations(address: str, normalizations: list) -> str:
    for rule in normalizations:
        flags = 0
        if "IGNORECASE" in rule.get("flags", ""):
            flags |= re.IGNORECASE
        address = re.sub(rule["pattern"], rule["replacement"], address, flags=flags)
    return address


def limpiar_direccion(address: str, territory: str = "tarancon") -> str:
    t = _load_territory(territory)
    cleaned = _apply_normalizations(address, t.get("normalizations", []))
    logger.info("Dirección normalizada: %s", cleaned)
    return cleaned


def _build_url(address: str, territory: str) -> str:
    t = _load_territory(territory)
    encoded = urllib.parse.quote(address)
    postal = t.get("postal_code", "")
    locality = t["locality"]
    region = t["region"]
    return f"{BASE_URL}?address={encoded},+{postal}+{locality},+{region},+España&key={config.GOOGLE_MAPS_API_KEY}"


def validar_coordenadas(coords: dict, territory: str = "tarancon") -> bool:
    polygon = _get_polygon(territory)
    point = Point(coords["lng"], coords["lat"])
    return polygon.contains(point)


@retry(
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
    reraise=False,
)
def _google_geocode(url: str) -> dict | None:
    """Llama a la API de Google Maps con retry automático ante fallos de red."""
    response = requests.get(url, timeout=5)
    response.raise_for_status()
    return response.json()


def _es_resultado_generico(types: list, territory: str) -> bool:
    """Devuelve True si el tipo de resultado de Google indica zona/país, no dirección concreta."""
    t = _load_territory(territory)
    excluded_types = set(t.get("excluded_result_types", []))
    return bool(excluded_types.intersection(types))


def geocodificar_direccion(address: str, territory: str = "tarancon") -> tuple[float, float] | None:
    clean = limpiar_direccion(address, territory)
    url = _build_url(clean, territory)
    try:
        data = _google_geocode(url)
        if data is None or data.get("status") != "OK" or not data.get("results"):
            logger.warning("geocodificar_direccion: no results for '%s'", address)
            return None
        location = data["results"][0]["geometry"]["location"]
        return location["lat"], location["lng"]
    except Exception as e:
        logger.error("geocodificar_direccion: error for '%s': %s", address, e)
        return None


def validar_direccion(address: str, territory: str = "tarancon") -> tuple[bool, str | None, str | None]:
    """
    Valida una dirección y devuelve (valida, direccion_formateada, motivo_rechazo).

    Motivos de rechazo:
      "no_encontrada"      — Google no devuelve resultados
      "fuera_de_zona"      — coordenadas fuera del polígono
      "demasiado_generica" — Google devuelve zona/país en vez de dirección concreta
      "sin_numero"         — dentro del polígono pero tipo no entregable
      "error_api"          — fallo de conexión con Google Maps tras reintentos
    """
    t = _load_territory(territory)
    clean = limpiar_direccion(address, territory)
    url = _build_url(clean, territory)

    logger.debug("Dirección original: %r", address)
    logger.debug("Dirección limpia: %r", clean)

    try:
        data = _google_geocode(url)

        if data is None or data.get("status") != "OK" or not data.get("results"):
            logger.warning("Dirección no válida o no encontrada: %s", data.get("status") if data else "None")
            return False, None, "no_encontrada"

        result = data["results"][0]
        formatted = result["formatted_address"]
        coords = result["geometry"]["location"]
        types = result.get("types", [])

        logger.debug("Dirección formateada: %s", formatted)
        logger.debug("Coordenadas: %s", coords)
        logger.debug("Types: %s", types)

        # Rechazar por tipo genérico antes de comprobar polígono
        if _es_resultado_generico(types, territory):
            logger.warning("Resultado demasiado genérico (tipos: %s): %s", types, formatted)
            return False, None, "demasiado_generica"

        if not validar_coordenadas(coords, territory):
            logger.warning("Dirección fuera de los límites de %s: %s", territory, formatted)
            return False, formatted, "fuera_de_zona"

        # Fallback de exclusión por string exacto (por si acaso)
        if formatted in t.get("excluded_addresses", []):
            logger.warning("Dirección demasiado general: %s", formatted)
            return False, None, "demasiado_generica"

        valid_types = set(t.get("valid_address_types", []))
        if not any(tp in types for tp in valid_types):
            logger.warning("La dirección no parece ser específica: %s", types)
            return False, formatted, "sin_numero"

        logger.info("Dirección válida: %s", formatted)
        return True, formatted, None

    except Exception as e:
        logger.error("Error al conectar con la API de Google Maps: %s", e)
        return False, None, "error_api"
