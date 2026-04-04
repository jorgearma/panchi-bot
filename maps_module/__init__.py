"""
maps_module — módulo de validación geográfica.

API pública:
    validar_direccion(address, territory="tarancon") -> (bool, str | None)
    geocodificar_direccion(address, territory="tarancon") -> (float, float) | None
    validar_coordenadas(coords, territory="tarancon") -> bool
    limpiar_direccion(address, territory="tarancon") -> str

Diseñado para ser extraíble como microservicio independiente:
    - El blueprint Flask en maps_module.blueprint ya expone los endpoints REST.
    - Los controllers del monolito importan directamente (sin HTTP overhead).
    - Para extraer: reemplazar los imports por maps_client.MapsClient().
"""
from maps_module.service import (
    validar_direccion,
    geocodificar_direccion,
    validar_coordenadas,
    limpiar_direccion,
)

__all__ = [
    "validar_direccion",
    "geocodificar_direccion",
    "validar_coordenadas",
    "limpiar_direccion",
]
