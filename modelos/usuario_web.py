class UsuarioWeb:
    """DTO de usuario para las vistas de menú y confirmación de pago."""

    def __init__(self, datos: dict):
        self.id = datos.get("id", "")
        self.nombre = datos.get("nombre", "")
        self.numero = datos.get("numero", "")
        self.direccion = datos.get("direccion", "")
        self.token = datos.get("token", "")

    def __repr__(self):
        return f"<UsuarioWeb: {self.nombre}>"

    def to_dict(self) -> dict:
        return {
            "nombre": self.nombre,
            "numero": self.numero,
            "direccion": self.direccion,
        }
