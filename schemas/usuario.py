from typing import Optional
from pydantic import BaseModel, Field

class UsuarioDatos(BaseModel):
    id: int = Field(..., description="ID único del usuario")
    nombre: str = Field(..., min_length=1, max_length=255, description="Nombre del usuario")
    numero: str = Field(..., min_length=1, max_length=50, description="Número de cliente del usuario")
    direccion: str = Field(None, max_length=255, description="Dirección del usuario")
    token: Optional[str] = None
