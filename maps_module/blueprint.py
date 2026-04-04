"""
Blueprint REST para maps_module.

Endpoints: /api/v1/maps/validate-address, /geocode, /validate-coords, /territories
Listo para ser extraído como microservicio independiente sin cambios de contrato.
"""
import json
import logging
from pathlib import Path

from flask import Blueprint, request, jsonify
from pydantic import ValidationError

from maps_module.schemas import (
    ValidateAddressRequest,
    GeocodeRequest,
    ValidateCoordsRequest,
)
from maps_module.service import (
    validar_direccion,
    geocodificar_direccion,
    validar_coordenadas,
)

logger = logging.getLogger(__name__)

blueprint_maps = Blueprint("maps", __name__, url_prefix="/api/v1/maps")

_TERRITORIES_PATH = Path(__file__).parent / "territories.json"


@blueprint_maps.route("/validate-address", methods=["POST"])
def validate_address():
    try:
        req = ValidateAddressRequest(**request.get_json(force=True))
    except (ValidationError, TypeError) as e:
        return jsonify({"error": str(e)}), 400

    valid, formatted = validar_direccion(req.address, req.territory)
    return jsonify({
        "valid": valid,
        "formatted_address": formatted,
    }), 200


@blueprint_maps.route("/geocode", methods=["POST"])
def geocode():
    try:
        req = GeocodeRequest(**request.get_json(force=True))
    except (ValidationError, TypeError) as e:
        return jsonify({"error": str(e)}), 400

    result = geocodificar_direccion(req.address, req.territory)
    if result is None:
        return jsonify({"error": "Could not geocode address"}), 400

    lat, lng = result
    return jsonify({"lat": lat, "lng": lng}), 200


@blueprint_maps.route("/validate-coords", methods=["POST"])
def validate_coords():
    try:
        req = ValidateCoordsRequest(**request.get_json(force=True))
    except (ValidationError, TypeError) as e:
        return jsonify({"error": str(e)}), 400

    valid = validar_coordenadas({"lat": req.lat, "lng": req.lng}, req.territory)
    return jsonify({"valid": valid}), 200


@blueprint_maps.route("/territories", methods=["GET"])
def territories():
    with open(_TERRITORIES_PATH) as f:
        data = json.load(f)
    # No exponer el polygon completo en producción si no es necesario
    summary = [
        {
            "name": t["name"],
            "locality": t["locality"],
            "region": t["region"],
        }
        for t in data["territories"]
    ]
    return jsonify({"territories": summary}), 200
