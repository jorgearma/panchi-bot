import json
import logging
import re
import unicodedata
from pathlib import Path

from rapidfuzz import process, fuzz

logger = logging.getLogger(__name__)

_CALLES_PATH = Path(__file__).parent / "calles_tarancon.json"
_calles_cache: list[str] = []

_SCORE_THRESHOLD = 72  # por debajo no sugerimos nada


def _load_calles() -> list[str]:
    if not _calles_cache:
        with open(_CALLES_PATH, encoding="utf-8") as f:
            _calles_cache.extend(json.load(f))
    return _calles_cache


def _normalizar(texto: str) -> str:
    """Minúsculas, sin tildes, sin números, sin puntuación extra."""
    texto = texto.lower().strip()
    texto = re.sub(r"\d+", "", texto)           # quitar números (nº portal)
    texto = re.sub(r"[,./\\]+", " ", texto)     # quitar puntuación
    texto = re.sub(r"\s+", " ", texto).strip()
    # quitar tildes para comparación
    texto = "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )
    return texto


def sugerir_calle(input_usuario: str) -> str | None:
    """
    Busca la calle más parecida al input del usuario en calles_tarancon.json.
    Devuelve el nombre oficial de la calle (con tildes) o None si no hay
    coincidencia suficientemente buena.
    """
    calles = _load_calles()
    query = _normalizar(input_usuario)

    if not query:
        return None

    # Normalizamos también las calles del catálogo para comparar sin tildes
    calles_norm = [_normalizar(c) for c in calles]

    resultado = process.extractOne(
        query,
        calles_norm,
        scorer=fuzz.token_set_ratio,  # robusto ante orden de palabras y prefijos
    )

    if resultado is None:
        return None

    _match_norm, score, idx = resultado
    logger.debug("sugerir_calle: query=%r best=%r score=%s", query, calles[idx], score)

    if score >= _SCORE_THRESHOLD:
        return calles[idx]  # devolvemos el nombre oficial con tildes

    return None
