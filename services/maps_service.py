"""
Shim de compatibilidad — la lógica vive en maps_module.
Este archivo existe para no romper mocks de tests existentes.
No añadir lógica aquí.
"""
from maps_module.service import (  # noqa: F401
    validar_direccion,
    geocodificar_direccion,
    validar_coordenadas,
    limpiar_direccion,
)
