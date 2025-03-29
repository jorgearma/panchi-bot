from pydantic import BaseModel, ValidationError, validator
import re

class WebhookRequest(BaseModel):
    From: str
    Body: str

    @validator('From')
    def validate_phone_number(cls, v):
        # Validar que el número tenga el formato "whatsapp:+<código_pais><número>"
        pattern = r'^whatsapp:\+\d{10,15}$'
        if not re.match(pattern, v):
            raise ValueError("Número de teléfono inválido. Debe tener el formato 'whatsapp:+<código_pais><número>'")
        return v

    @validator('Body')
    def validate_body(cls, v):
        if not v or not v.strip():
            raise ValueError("El mensaje no puede estar vacío")
        return v.strip()
    

from pydantic import BaseModel, Field

class PedidoInput(BaseModel):
    pedido: str = Field(..., min_length=1, description="El mensaje enviado por el cliente.")
    numero_cliente: str = Field(..., min_length=1, description="El número de teléfono o identificador único del cliente.")
    id_pedido_actual: int = Field(..., ge=1, description="El ID del pedido actual, debe ser un número entero positivo.")