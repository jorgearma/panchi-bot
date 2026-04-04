import json
import logging
import re
import urllib.parse
from pathlib import Path

import requests
from shapely.geometry import Point, Polygon

import config

logger = logging.getLogger(__name__)

BASE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

_TERRITORIES_PATH = Path(__file__).parent / "territories.json"
_territories_cache: dict = {}


def _load_territory(name: str) -> dict:
    if name not in _territories_cache:
        with open(_TERRITORIES_PATH) as f:
            data = json.load(f)
        for t in data["territories"]:
            _territories_cache[t["name"]] = t
    if name not in _territories_cache:
        raise ValueError(f"Territory '{name}' not found in configuration")
    return _territories_cache[name]


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


def _build_polygon(territory: str) -> Polygon:
    t = _load_territory(territory)
    return Polygon(t["polygon"])


def validar_coordenadas(coords: dict, territory: str = "tarancon") -> bool:
    polygon = _build_polygon(territory)
    point = Point(coords["lng"], coords["lat"])
    return polygon.contains(point)


def geocodificar_direccion(address: str, territory: str = "tarancon") -> tuple[float, float] | None:
    clean = limpiar_direccion(address, territory)
    url = _build_url(clean, territory)
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        if data.get("status") != "OK" or not data.get("results"):
            logger.warning("geocodificar_direccion: no results for '%s'", address)
            return None
        location = data["results"][0]["geometry"]["location"]
        return location["lat"], location["lng"]
    except requests.exceptions.RequestException as e:
        logger.error("geocodificar_direccion: request error for '%s': %s", address, e)
        return None


def validar_direccion(address: str, territory: str = "tarancon") -> tuple[bool, str | None]:
    t = _load_territory(territory)
    clean = limpiar_direccion(address, territory)
    url = _build_url(clean, territory)

    logger.debug("Dirección original: %r", address)
    logger.debug("Dirección limpia: %r", clean)

    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()

        logger.debug("Status API: %s", data.get("status"))

        if data.get("status") != "OK" or not data.get("results"):
            logger.warning("Dirección no válida o no encontrada: %s", data.get("status"))
            return False, None

        result = data["results"][0]
        formatted = result["formatted_address"]
        coords = result["geometry"]["location"]
        types = result.get("types", [])

        logger.debug("Dirección formateada: %s", formatted)
        logger.debug("Coordenadas: %s", coords)
        logger.debug("Types: %s", types)

        if not validar_coordenadas(coords, territory):
            logger.warning("Dirección fuera de los límites de %s: %s", territory, formatted)
            return False, formatted

        if formatted in t.get("excluded_addresses", []):
            logger.warning("Dirección demasiado general: %s", formatted)
            return False, None

        valid_types = set(t.get("valid_address_types", []))
        if not any(tp in types for tp in valid_types):
            logger.warning("La dirección no parece ser específica: %s", types)
            return False, formatted

        logger.info("Dirección válida: %s", formatted)
        return True, formatted

    except requests.exceptions.RequestException as e:
        logger.error("Error al conectar con la API de Google Maps: %s", e)
        return False, None
