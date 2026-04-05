import json
import logging
import re
import unicodedata
from pathlib import Path

from rapidfuzz import process, fuzz

logger = logging.getLogger(__name__)

_CALLES_PATH = Path(__file__).parent / "calles_tarancon.json"

# Cache: lista original con tildes y lista normalizada para comparar
_calles_raw: list[str] = []
_calles_norm: list[str] = []

# Umbral mínimo para sugerir algo
_SCORE_MIN = 72
# Umbral para considerar la sugerencia "segura" (tono más directo en el mensaje)
_SCORE_ALTA_CONFIANZA = 86


def _load_calles() -> tuple[list[str], list[str]]:
    if not _calles_raw:
        with open(_CALLES_PATH, encoding="utf-8") as f:
            _calles_raw.extend(json.load(f))
        _calles_norm.extend(_normalizar(c) for c in _calles_raw)
    return _calles_raw, _calles_norm


_ABREVS = [
    (r"\bc/\s*",          "calle "),
    (r"\bavda\.?\s+",     "avenida "),
    (r"\bavd\.?\s+",      "avenida "),
    (r"\bpza\.?\s+",      "plaza "),
    (r"\bpso\.?\s+",      "paseo "),
    (r"\bcno\.?\s+",      "camino "),
    (r"\bglta\.?\s+",     "glorieta "),
    (r"\brda\.?\s+",      "ronda "),
    (r"\btrav\.?\s+",     "travesia "),
]


def _normalizar(texto: str) -> str:
    """Minúsculas, sin tildes, sin números, expande abreviaciones, sin puntuación extra."""
    texto = texto.lower().strip()
    for patron, expansion in _ABREVS:
        texto = re.sub(patron, expansion, texto, flags=re.IGNORECASE)
    texto = re.sub(r"\d+", "", texto)
    texto = re.sub(r"[,./\\]+", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


def sugerir_calle(input_usuario: str) -> tuple[str, bool] | tuple[None, None]:
    """
    Busca la calle más parecida al input del usuario en el catálogo.

    Devuelve (nombre_oficial, alta_confianza) si hay coincidencia suficiente,
    o (None, None) si no hay nada fiable.

    alta_confianza=True  → el bot puede decir "¿Quisiste decir X?"
    alta_confianza=False → el bot dice "¿Te refieres a X?" con más cautela
    """
    calles_raw, calles_norm = _load_calles()
    query = _normalizar(input_usuario)

    if not query:
        return None, None

    # WRatio combina varios scorers y elige el mejor para cada par.
    # Más preciso que token_set_ratio solo para distinguir calles con nombres similares.
    resultado = process.extractOne(
        query,
        calles_norm,
        scorer=fuzz.WRatio,
    )

    if resultado is None:
        return None, None

    _match_norm, score, idx = resultado
    logger.debug("sugerir_calle: query=%r best=%r score=%s", query, calles_raw[idx], score)

    if score >= _SCORE_MIN:
        return calles_raw[idx], score >= _SCORE_ALTA_CONFIANZA

    return None, None
