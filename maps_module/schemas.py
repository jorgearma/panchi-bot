from pydantic import BaseModel
from typing import Optional


class ValidateAddressRequest(BaseModel):
    address: str
    territory: str = "tarancon"


class Coords(BaseModel):
    lat: float
    lng: float


class ValidateAddressResponse(BaseModel):
    valid: bool
    formatted_address: Optional[str] = None
    coords: Optional[Coords] = None
    types: list = []


class GeocodeRequest(BaseModel):
    address: str
    territory: str = "tarancon"


class GeocodeResponse(BaseModel):
    lat: float
    lng: float


class ValidateCoordsRequest(BaseModel):
    lat: float
    lng: float
    territory: str = "tarancon"


class ValidateCoordsResponse(BaseModel):
    valid: bool
