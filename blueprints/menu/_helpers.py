def _extraer_calle(direccion: str) -> str:
    """Extrae calle y número para mostrar direcciones de forma compacta."""
    parts = [p.strip() for p in direccion.split(',')]
    if len(parts) >= 2 and parts[1].isdigit():
        return f"{parts[0]} {parts[1]}"
    return parts[0]
