# claude/hooks/tests/test_validate.py
"""Tests unitarios para validate.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from validate import validate_artifact, ValidationResult, SCHEMA_MAP, SCHEMA_DIR


# ── Helpers de datos de test ──────────────────────────────────────────────────

def _valid_plan() -> dict:
    """Plan mínimo completamente válido según plan.json schema."""
    return {
        "task": "Agregar endpoint /health",
        "steps": [{"id": "s1", "title": "Crear handler", "owner": "backend"}],
        "risks": [],
        "done_criteria": ["GET /health retorna 200"],
        "context_inputs": {
            "selected_readers": ["api"],
            "maps_used": ["ROUTING_MAP.json"],
            "files_to_open": [],
            "files_to_review": [],
        },
        "rollback_plan": {"enabled": False, "steps": []},
    }



# ── Criterio 1: campo required faltante bloquea ──────────────────────────────

def test_plan_missing_done_criteria_is_critical():
    """Campo required faltante → ok=False, error menciona done_criteria."""
    data = _valid_plan()
    del data["done_criteria"]
    result = validate_artifact("plan.json", data)
    assert not result.ok
    assert any("done_criteria" in e for e in result.errors), f"errors: {result.errors}"


# ── Criterio 2: enum inválido bloquea ────────────────────────────────────────

def test_plan_invalid_owner_enum_is_critical():
    """Valor enum inválido en steps[0].owner → ok=False."""
    data = _valid_plan()
    data["steps"][0]["owner"] = "devops"
    result = validate_artifact("plan.json", data)
    assert not result.ok
    assert any("owner" in e or "devops" in e for e in result.errors), f"errors: {result.errors}"


# ── Criterio 3: campo opcional malformado → warning, no error ─────────────────

def test_plan_optional_field_wrong_type_is_warning():
    """Campo opcional con tipo incorrecto → ok=True, entry en warnings."""
    data = _valid_plan()
    data["context_inputs"]["notes"] = 99999  # notes es string opcional
    result = validate_artifact("plan.json", data)
    assert result.ok, f"errors: {result.errors}"
    assert len(result.warnings) > 0, "Se esperaba al menos un warning"


# ── Criterio 8: artifact desconocido lanza KeyError ──────────────────────────

def test_unknown_artifact_raises_key_error():
    """Artifact no registrado → KeyError con el nombre en el mensaje."""
    with pytest.raises(KeyError) as exc_info:
        validate_artifact("unknown-artifact.json", {})
    assert "unknown-artifact.json" in str(exc_info.value)



# ── result.json: sin required a nivel raíz ───────────────────────────────────

def test_result_empty_object_passes_schema():
    """result.json vacío es válido per schema (frontend/backend son opcionales)."""
    result = validate_artifact("result.json", {})
    assert result.ok


def test_result_with_invalid_frontend_status_is_critical():
    """result.json con frontend.status inválido → ok=False."""
    data = {
        "frontend": {
            "status": "unknown_status",
            "summary": "hecho",
            "artifacts": [],
            "next_steps": [],
        }
    }
    result = validate_artifact("result.json", data)
    assert not result.ok
    assert any("status" in e or "unknown_status" in e for e in result.errors), \
        f"errors: {result.errors}"


# ── operator-approval.json ────────────────────────────────────────────────────

def test_operator_approval_valid():
    result = validate_artifact("operator-approval.json", {"status": "approved", "approved_by": "alice"})
    assert result.ok


def test_operator_approval_invalid_status():
    result = validate_artifact("operator-approval.json", {"status": "maybe", "approved_by": "alice"})
    assert not result.ok


# ── Cobertura de SCHEMA_MAP ───────────────────────────────────────────────────

def test_schema_map_covers_all_registered_schemas():
    """SCHEMA_MAP debe cubrir exactamente los artifacts validados hoy."""
    assert len(SCHEMA_MAP) == 14, f"Esperado 14, encontrado {len(SCHEMA_MAP)}"


def test_all_schema_files_exist_on_disk():
    """Todos los schema files referenciados deben existir en claude/schemas/."""
    missing = [
        f"{name} → {schema_file}"
        for name, schema_file in SCHEMA_MAP.items()
        if not (SCHEMA_DIR / schema_file).exists()
    ]
    assert missing == [], f"Schema files faltantes: {missing}"


# ── ValidationResult formatting ──────────────────────────────────────────────

def test_format_includes_artifact_name_and_blocked():
    data = {"status": "bad", "approved_by": "x"}
    result = validate_artifact("operator-approval.json", data)
    formatted = result.format()
    assert "operator-approval.json" in formatted
    assert "BLOCKED" in formatted


def test_summary_is_single_line():
    result = validate_artifact("operator-approval.json", {"status": "approved", "approved_by": "a"})
    assert "\n" not in result.summary()
