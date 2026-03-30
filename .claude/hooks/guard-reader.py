#!/usr/bin/env python3
"""PreToolUse hook — restringe al reader a los MAPs autorizados.

Lee runtime/reader-allowlist.json (generado por reader-only.py) y:
  1. Bloquea Read a paths fuera de los MAPs autorizados
  2. Bloquea Read duplicados (mismo archivo leído dos veces)
  3. Solo permite Write a reader-context.json (una sola vez)
  4. Bloquea Edit sobre reader-context.json (debe usar Write)
  5. Bloquea Bash, Glob, Grep — el reader no los necesita

Protocolo de hooks PreToolUse (Claude Code):
  - Recibe JSON por stdin con {tool_name, tool_input, ...}
  - Responde JSON por stdout con hookSpecificOutput.permissionDecision
  - "allow" → deja pasar, "deny" → bloquea con razón
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PLUGIN_DIR.parent
RUNTIME = PLUGIN_DIR / "runtime"
ALLOWLIST_FILE = RUNTIME / "reader-allowlist.json"
READS_LOG = RUNTIME / "reader-reads.log"
WRITES_LOG = RUNTIME / "reader-writes.log"


def allow():
	"""Permite la tool call."""
	print(json.dumps({"hookSpecificOutput": {
		"hookEventName": "PreToolUse",
		"permissionDecision": "allow",
	}}))
	sys.exit(0)


def deny(reason: str):
	"""Bloquea la tool call con razón visible para Claude."""
	print(json.dumps({"hookSpecificOutput": {
		"hookEventName": "PreToolUse",
		"permissionDecision": "deny",
		"permissionDecisionReason": reason,
	}}))
	sys.exit(0)


# Solo se activa si existe el allowlist (reader-only.py lo crea antes de lanzar claude)
if not ALLOWLIST_FILE.exists():
	allow()

try:
	hook_input = json.loads(sys.stdin.read())
except (json.JSONDecodeError, EOFError):
	allow()

tool_name = hook_input.get("tool_name", "")
tool_input = hook_input.get("tool_input", {})

# ── Bloquear herramientas prohibidas ──────────────────────────────────────────

if tool_name in ("Bash", "Glob", "Grep"):
	deny(
		f"{tool_name} no permitido. El reader solo puede usar Read (MAPs) "
		"y Write (reader-context.json). Ya sabes qué archivos leer — úsalos directamente."
	)

# Solo nos interesan Read, Write y Edit
if tool_name not in ("Read", "Write", "Edit"):
	allow()

# Cargar allowlist
try:
	allowlist = json.loads(ALLOWLIST_FILE.read_text(encoding="utf-8"))
except (json.JSONDecodeError, OSError):
	allow()

allowed_reads: set[str] = set(allowlist.get("allowed_reads", []))
allowed_write: str = allowlist.get("allowed_write", "")


# ── Resolver el path que Claude quiere usar ──────────────────────────────────

def resolve_target(inp: dict) -> str | None:
	"""Extrae y normaliza el path objetivo de la tool call."""
	raw = inp.get("file_path", "")
	if not raw:
		return None
	try:
		p = Path(raw).resolve()
		return str(p.relative_to(PROJECT_ROOT))
	except (ValueError, OSError):
		return raw


target = resolve_target(tool_input)

if not target:
	allow()

# ── Edit: nunca permitido para el reader ──────────────────────────────────────

if tool_name == "Edit":
	deny(
		f"Edit no permitido. Usa Write para crear reader-context.json de una sola vez. "
		"No edites ni corrijas — genera el JSON completo y correcto en un solo Write."
	)

# ── Write: solo reader-context.json, una sola vez ────────────────────────────

if tool_name == "Write":
	if target != allowed_write:
		deny(f"Write a '{target}' no permitido. Solo puedes escribir '{allowed_write}'.")

	# Verificar si ya escribió
	already_written = False
	if WRITES_LOG.exists():
		try:
			already_written = bool(WRITES_LOG.read_text(encoding="utf-8").strip())
		except OSError:
			pass

	if already_written:
		deny(
			"Ya escribiste reader-context.json. No lo reescribas ni corrijas. "
			"Si el JSON tenía un error, el validador lo detectará después."
		)

	# Registrar escritura
	try:
		WRITES_LOG.write_text(target + "\n", encoding="utf-8")
	except OSError:
		pass

	allow()

# ── Read: verificar contra allowlist ──────────────────────────────────────────

if target not in allowed_reads:
	deny(
		f"'{target}' no está en la lista de MAPs autorizados. "
		f"Solo puedes leer: {', '.join(sorted(allowed_reads))}"
	)

# ── Read: permitir relecturas acotadas (más margen para MAPs grandes) ───────────

MAX_READS_DEFAULT = 3
MAX_READS_BY_TARGET = {
	# ROUTING_MAP es pequeño — límite estándar
	# DOMAIN_INDEX_data puede tener muchos candidatos si el proyecto tiene >20 modelos
	".claude/maps/DOMAIN_INDEX_data.json":     10,
	"claude/maps/DOMAIN_INDEX_data.json":      10,
	# DEPENDENCY_MAP puede ser muy grande en proyectos con muchos archivos
	".claude/maps/DEPENDENCY_MAP.json":        10,
	"claude/maps/DEPENDENCY_MAP.json":         10,
}
read_count: dict[str, int] = {}

if READS_LOG.exists():
	try:
		lines = READS_LOG.read_text(encoding="utf-8").splitlines()
		for line in lines:
			read_count[line] = read_count.get(line, 0) + 1
	except OSError:
		pass

max_reads = MAX_READS_BY_TARGET.get(target, MAX_READS_DEFAULT)

if target in read_count and read_count[target] >= max_reads:
	deny(
		f"'{target}' ya fue leído {max_reads} veces. "
		"Usa la información que obtuviste en las lecturas anteriores o registra en risks si necesitas más contexto."
	)

# Registrar lectura
try:
	with READS_LOG.open("a", encoding="utf-8") as f:
		f.write(target + "\n")
except OSError:
	pass

# Todo ok
allow()
