#!/usr/bin/env python3
"""Validación central de artifacts JSON contra sus schemas.

Uso desde hooks:
    from validate import validate_artifact

    result = validate_artifact("plan.json", data)
    if not result.ok:
        print(result.format())
        return 1
    if result.warnings:
        print(result.format_warnings())
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

try:
    import jsonschema
    from jsonschema import ValidationError
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "jsonschema no está instalado. Ejecuta: pip install jsonschema"
    ) from exc


# claude/hooks/ -> parents[0]; claude/ -> parents[1]; claude/schemas/ -> parents[1]/schemas
SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"

# Mapeo: nombre del artifact en runtime → nombre del archivo schema en SCHEMA_DIR
SCHEMA_MAP: dict[str, str] = {
    # Runtime artifacts
    "reader-context.json":     "reader-context.json",
    "plan.json":               "plan.json",
    "execution-brief.json":    "execution-brief.json",
    "execution-dispatch.json": "execution-dispatch.json",
    "operator-approval.json":  "operator-approval.json",
    "result.json":             "result.json",
    # Maps (artifact name → schema filename en schemas/)
    "ROUTING_MAP.json":            "routing-map.json",
    "DOMAIN_INDEX_api.json":       "domain-index.json",
    "DOMAIN_INDEX_data.json":      "domain-index.json",
    "DOMAIN_INDEX_ui.json":        "domain-index.json",
    "DOMAIN_INDEX_services.json":  "domain-index.json",
    "DOMAIN_INDEX_jobs.json":      "domain-index.json",
    "CONTRACT_MAP.json":           "contract-map.json",
    "DEPENDENCY_MAP.json":         "dependency-map.json",
}

# Validators que son críticos en campos requeridos
_CRITICAL_VALIDATORS = {"required", "enum"}


@dataclass
class ValidationResult:
    name: str
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def format(self) -> str:
        """Texto multilínea para consola. Incluye nombre del artifact, errores y warnings."""
        n_e = len(self.errors)
        n_w = len(self.warnings)
        header = f"[BLOCKED] {self.name} — {n_e} error(s), {n_w} warning(s)"
        lines = [header]
        for e in self.errors:
            lines.append(f"  ERROR   {e}")
        for w in self.warnings:
            lines.append(f"  WARN    {w}")
        return "\n".join(lines)

    def format_warnings(self) -> str:
        """Solo los warnings, sin header de blocked."""
        lines = [f"[WARN] {self.name} — {len(self.warnings)} warning(s)"]
        for w in self.warnings:
            lines.append(f"  WARN    {w}")
        return "\n".join(lines)

    def summary(self) -> str:
        """Una línea para incluir como campo 'reason' en dispatch JSON."""
        if self.errors:
            return f"{self.name} inválido: {self.errors[0]}"
        if self.warnings:
            return f"{self.name} con {len(self.warnings)} advertencia(s)"
        return f"{self.name} válido"


def _load_schema(schema_filename: str) -> dict:
    schema_path = SCHEMA_DIR / schema_filename
    try:
        with schema_path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Schema file '{schema_filename}' no encontrado en {SCHEMA_DIR}. "
            f"Verifica que claude/schemas/{schema_filename} existe."
        )


def _is_critical(error: ValidationError) -> bool:
    """Determina si un error de jsonschema es bloqueante."""
    if error.validator in _CRITICAL_VALIDATORS:
        return True
    if error.validator == "type":
        # Crítico solo si el campo (string) está en `required` del schema padre.
        # Si path[-1] es un int (índice de array), no es un campo requerido → warning.
        field_name = error.path[-1] if error.path else None
        if isinstance(field_name, str) and error.parent is not None:
            parent_required = error.parent.schema.get("required", [])
            return field_name in parent_required
    return False


def _error_message(error: ValidationError) -> str:
    """Formatea un error de jsonschema como mensaje legible."""
    path = ".".join(str(p) for p in error.absolute_path) if error.absolute_path else "root"
    return f"{path}: {error.message}"


def validate_artifact(name: str, data: dict) -> ValidationResult:
    """Valida `data` contra el schema correspondiente a `name`.

    Args:
        name: Nombre del artifact (ej: "plan.json", "ROUTING_MAP.json").
        data: Contenido ya parseado del artifact.

    Returns:
        ValidationResult. ok=True si no hay errores críticos.
        Warnings presentes no afectan ok.

    Raises:
        KeyError: Si `name` no está en SCHEMA_MAP — indica bug en el hook caller.
        ImportError: Si jsonschema no está instalado.
    """
    if name not in SCHEMA_MAP:
        raise KeyError(
            f"Artifact desconocido: '{name}'. "
            f"Artifacts válidos: {sorted(SCHEMA_MAP)}"
        )

    if not isinstance(data, dict):
        raise TypeError(
            f"validate_artifact espera un dict, recibió {type(data).__name__}"
        )

    schema = _load_schema(SCHEMA_MAP[name])
    validator = jsonschema.Draft202012Validator(schema)

    errors: list[str] = []
    warnings: list[str] = []

    for error in validator.iter_errors(data):
        msg = _error_message(error)
        if _is_critical(error):
            errors.append(msg)
        else:
            warnings.append(msg)

    return ValidationResult(
        name=name,
        ok=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )
