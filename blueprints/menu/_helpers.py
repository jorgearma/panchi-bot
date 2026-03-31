def _extraer_calle(direccion: str) -> str:
    """Returns street + number from an address string.

    Handles two common formats:
      "Calle Mayor 12, 16400 Tarancón"  → "Calle Mayor 12"
      "Calle Mayor, 12, 16400 Tarancón" → "Calle Mayor 12"
    """
    parts = [p.strip() for p in direccion.split(',')]
    if len(parts) >= 2 and parts[1].isdigit():
        return f"{parts[0]} {parts[1]}"
    return parts[0]
