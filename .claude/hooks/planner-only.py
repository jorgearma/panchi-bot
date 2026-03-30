#!/usr/bin/env python3
"""Planner standalone — lee reader-context.json, crea plan.json. Sin confirmaciones."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PLUGIN_DIR.parent
RUNTIME = PLUGIN_DIR / "runtime"
READER_CONTEXT = RUNTIME / "reader-context.json"
PLAN_JSON = RUNTIME / "plan.json"
ALLOWLIST_FILE = RUNTIME / "planner-allowlist.json"
READS_LOG = RUNTIME / "planner-reads.log"
PLANNER_AGENT = PLUGIN_DIR / "agents" / "planner.md"
SESSION_DIR = Path.home() / ".claude" / "projects" / str(PROJECT_ROOT).replace("/", "-").replace("\\", "-")


def load_planner_prompt() -> str | None:
	"""Lee planner.md y quita el frontmatter YAML (--- ... ---)."""
	try:
		content = PLANNER_AGENT.read_text(encoding="utf-8")
	except OSError:
		return None
	# Quitar frontmatter YAML
	if content.startswith("---"):
		end = content.find("---", 3)
		if end != -1:
			content = content[end + 3:].lstrip("\n")
	return content


def build_dynamic_prompt(base_prompt: str, ctx: dict) -> str:
	"""Genera system prompt dinámico: planner.md base + sección de archivos autorizados.

	Inyecta en el system prompt (no en el mensaje del usuario) la lista exacta
	de archivos que el planner puede leer, con hints y tamaño en líneas.
	Esto es la fuente de verdad que Claude más respeta.
	"""
	seen: set[str] = set()
	open_lines: list[str] = []
	review_lines: list[str] = []
	size_map: dict[str, int | str] = {}

	for f in ctx.get("files_to_open", []):
		p = f["path"]
		if p in seen:
			continue
		seen.add(p)
		hint = f.get("hint", "")
		symbols = f.get("key_symbols", [])
		# Calcular tamaño
		full = PROJECT_ROOT / p
		if full.exists():
			try:
				n = len(full.read_text(encoding="utf-8").splitlines())
				size_map[p] = n
			except OSError:
				size_map[p] = "error"
		else:
			size_map[p] = "NO EXISTE"
		line = f"- `{p}` ({size_map[p]} líneas)"
		if hint:
			line += f" — {hint}"
		if symbols:
			line += f"\n  - key_symbols: `{'`, `'.join(symbols)}`"
		open_lines.append(line)

	for f in ctx.get("files_to_review", []):
		p = f["path"]
		if p in seen:
			continue
		seen.add(p)
		hint = f.get("hint", "")
		symbols = f.get("key_symbols", [])
		full = PROJECT_ROOT / p
		if full.exists():
			try:
				n = len(full.read_text(encoding="utf-8").splitlines())
				size_map[p] = n
			except OSError:
				size_map[p] = "error"
		else:
			size_map[p] = "NO EXISTE"
		line = f"- `{p}` ({size_map[p]} líneas)"
		if hint:
			line += f" — {hint}"
		if symbols:
			line += f"\n  - key_symbols: `{'`, `'.join(symbols)}`"
		review_lines.append(line)

	# Construir sección dinámica
	section = "\n\n## Archivos autorizados — generado por reader\n\n"
	section += "**RESTRICCIÓN ABSOLUTA:** Solo puedes leer (Read/Grep) los archivos listados abajo. "
	section += "NO abras, leas ni busques en ningún otro archivo del proyecto. "
	section += "Si necesitas información de un archivo no listado, registralo en `risks` como dependencia no revisada.\n"

	if open_lines:
		section += "\n### files_to_open (archivos donde ocurre el cambio):\n"
		section += "\n".join(open_lines) + "\n"

	if review_lines:
		section += "\n### files_to_review (archivos de referencia):\n"
		section += "\n".join(review_lines) + "\n"

	section += "\n### Salida permitida:\n"
	section += "- Solo puedes escribir: `.claude/runtime/plan.json`\n"

	return base_prompt + section, list(seen), size_map


def write_allowlist(allowed_paths: list[str]) -> None:
	"""Genera planner-allowlist.json para el hook guard-planner.py."""
	plan_rel = str(PLAN_JSON.relative_to(PROJECT_ROOT))
	data = {
		"allowed_paths": allowed_paths,
		"plan_output": plan_rel,
	}
	ALLOWLIST_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
	# Limpiar log de lecturas previas
	if READS_LOG.exists():
		READS_LOG.unlink()


def cleanup_guard_files() -> None:
	"""Limpia archivos temporales del guard al terminar."""
	for f in (ALLOWLIST_FILE, READS_LOG):
		if f.exists():
			f.unlink()


def validate_reader_context() -> dict | None:
	"""Valida que reader-context.json exista y sea válido."""
	if not READER_CONTEXT.exists():
		return None
	try:
		ctx = json.loads(READER_CONTEXT.read_text(encoding="utf-8"))
		return ctx
	except (json.JSONDecodeError, OSError):
		return None


# Precios por modelo (USD por millón de tokens)
MODEL_PRICES = {
	"claude-haiku-4-5-20251001": {
		"label": "HAIKU",
		"input": 0.80, "cache_w": 1.00, "cache_r": 0.08, "output": 4.00,
	},
	"claude-sonnet-4-6": {
		"label": "SONNET",
		"input": 3.00, "cache_w": 3.75, "cache_r": 0.30, "output": 15.00,
	},
	"claude-opus-4-6": {
		"label": "OPUS",
		"input": 15.00, "cache_w": 18.75, "cache_r": 1.50, "output": 75.00,
	},
}

# ── Colores ────────────────────────────────────────────────────────────────────

CYAN   = "\033[36m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
DIM    = "\033[2m"
BOLD   = "\033[1m"
RED    = "\033[31m"
RESET  = "\033[0m"


# ── Sesiones / tokens ──────────────────────────────────────────────────────────

def snapshot_sessions(session_dir: Path) -> set[Path]:
	"""Captura qué archivos .jsonl existen ANTES de lanzar el agente."""
	if not session_dir.exists():
		return set()
	return set(session_dir.glob("*.jsonl"))


def find_new_session(before: set[Path], session_dir: Path) -> Path | None:
	"""Encuentra el .jsonl que NO existía antes — ese es el del agente que acabamos de lanzar."""
	if not session_dir.exists():
		return None
	after = set(session_dir.glob("*.jsonl"))
	new_files = after - before
	if not new_files:
		return None
	# Si hay más de uno (raro), tomar el más reciente
	return max(new_files, key=lambda p: p.stat().st_mtime)


def parse_session_tokens(path: Path, prices: dict) -> dict | None:
	"""Lee el .jsonl y suma tokens de llamadas API únicas.

	Claude Code a veces divide una misma request en varios eventos assistant
	con el mismo requestId (por ejemplo texto preliminar + tool_use).
	Aquí se agrupan por requestId para no duplicar tokens ni inflar turnos.

	Los campos de usage son POR REQUEST (no acumulativos):
	  - input_tokens: tokens nuevos enviados (sin cache)
	  - cache_read_input_tokens: tokens leídos de cache
	  - cache_creation_input_tokens: tokens escritos a cache
	  - output_tokens: tokens generados por el modelo

	NOTA: El campo anidado "cache_creation" (con ephemeral_5m/1h) es solo
	el DESGLOSE del cache_creation_input_tokens — NO se suma por separado.
	"""
	try:
		lines = path.read_text(encoding="utf-8").splitlines()
	except OSError:
		return None
	if not lines:
		return None

	input_tokens = 0
	output_tokens = 0
	cache_read = 0
	cache_write = 0
	n_turns = 0
	tools_used: list[str] = []
	turns_detail: list[dict] = []
	seen_requests: dict[str, int] = {}

	for raw in lines:
		try:
			entry = json.loads(raw)
		except json.JSONDecodeError:
			continue

		if entry.get("type") != "assistant":
			continue

		msg = entry.get("message", {})
		usage = msg.get("usage", {})
		if not usage:
			continue

		turn_tools: list[str] = []
		for block in msg.get("content", []):
			if isinstance(block, dict) and block.get("type") == "tool_use":
				name = block.get("name", "")
				fp = block.get("input", {}).get("file_path", "")
				if fp:
					short = "/".join(Path(fp).parts[-3:])  # últimos 3 segmentos
					label = f"{name}({short})"
				elif name:
					label = name
				else:
					continue
				turn_tools.append(label)

		request_key = entry.get("requestId") or msg.get("id")
		if request_key and request_key in seen_requests:
			idx = seen_requests[request_key]
			existing_tools = turns_detail[idx]["tools"]
			for label in turn_tools:
				if label not in existing_tools:
					existing_tools.append(label)
				if label not in tools_used:
					tools_used.append(label)
			continue

		n_turns += 1
		t_in  = usage.get("input_tokens", 0)
		t_out = usage.get("output_tokens", 0)
		t_cr  = usage.get("cache_read_input_tokens", 0)
		t_cw  = usage.get("cache_creation_input_tokens", 0)

		input_tokens  += t_in
		output_tokens += t_out
		cache_read    += t_cr
		cache_write   += t_cw

		for label in turn_tools:
			if label not in tools_used:
				tools_used.append(label)

		turns_detail.append({
			"turn":        n_turns,
			"input":       t_in,
			"cache_read":  t_cr,
			"cache_write": t_cw,
			"output":      t_out,
			"tools":       turn_tools,
		})
		if request_key:
			seen_requests[request_key] = len(turns_detail) - 1

	if n_turns == 0:
		return None

	total_in = input_tokens + cache_read + cache_write
	cost = (
		input_tokens  / 1_000_000 * prices["input"]
		+ cache_write / 1_000_000 * prices["cache_w"]
		+ cache_read  / 1_000_000 * prices["cache_r"]
		+ output_tokens / 1_000_000 * prices["output"]
	)

	return {
		"session_id":    path.stem,
		"session_file":  str(path),
		"turns":         n_turns,
		"turns_detail":  turns_detail,
		"input_tokens":  input_tokens,
		"cache_read":    cache_read,
		"cache_write":   cache_write,
		"output_tokens": output_tokens,
		"total_in":      total_in,
		"total_tokens":  total_in + output_tokens,
		"cost_usd":      cost,
		"tools_used":    tools_used,
	}


def fmt_tokens(n: int) -> str:
	if n >= 1_000_000:
		return f"{n / 1_000_000:.1f}M"
	if n >= 1_000:
		return f"{n / 1_000:.1f}k"
	return str(n)


def fmt_time(s: float) -> str:
	if s < 60:
		return f"{s:.1f}s"
	return f"{int(s // 60)}m {s % 60:.0f}s"


def print_usage(usage: dict, prices: dict, elapsed: float | None = None) -> None:
	"""Muestra el consumo de tokens de forma clara."""
	sid = usage["session_id"][:8]
	n_tools = len(usage["tools_used"])
	label = prices["label"]

	print(f"\n{CYAN}{'─'*60}")
	print(f"  CONSUMO DE TOKENS ({label}) — sesión {sid}")
	print(f"{'─'*60}{RESET}")

	print(f"\n  {BOLD}Turnos API:{RESET}       {usage['turns']}")
	print()
	print(f"  {BOLD}Entrada:{RESET}")
	print(f"    Tokens nuevos:   {usage['input_tokens']:>10,}  ({fmt_tokens(usage['input_tokens'])})  ${prices['input']:.2f}/M")
	print(f"    Cache leído:     {usage['cache_read']:>10,}  ({fmt_tokens(usage['cache_read'])})     ${prices['cache_r']:.2f}/M")
	print(f"    Cache escrito:   {usage['cache_write']:>10,}  ({fmt_tokens(usage['cache_write'])})  ${prices['cache_w']:.2f}/M")
	print(f"    {'─'*40}")
	print(f"    Total entrada:   {usage['total_in']:>10,}  ({fmt_tokens(usage['total_in'])})")

	print()
	print(f"  {BOLD}Salida:{RESET}")
	print(f"    Tokens output:   {usage['output_tokens']:>10,}  ({fmt_tokens(usage['output_tokens'])})  ${prices['output']:.2f}/M")

	print()
	print(f"  {BOLD}Total tokens:{RESET}     {usage['total_tokens']:>10,}  ({fmt_tokens(usage['total_tokens'])})")
	print(f"  {BOLD}Costo estimado:{RESET}   ${usage['cost_usd']:.4f} USD")

	# Detalle por turno
	if usage.get("turns_detail"):
		print(f"\n  {BOLD}Detalle por turno:{RESET}")
		for t in usage["turns_detail"]:
			parts = []
			if t["input"]:
				parts.append(f"in={fmt_tokens(t['input'])}")
			if t["cache_read"]:
				parts.append(f"cache_r={fmt_tokens(t['cache_read'])}")
			if t["cache_write"]:
				parts.append(f"cache_w={fmt_tokens(t['cache_write'])}")
			if t["output"]:
				parts.append(f"out={fmt_tokens(t['output'])}")
			summary = "  ".join(parts)
			print(f"    Turno {t['turn']}:  {summary}")
			for tool in t["tools"]:
				print(f"      → {tool}")

	if usage["tools_used"]:
		print(f"\n  {BOLD}Operaciones:{RESET}")
		for tool in usage["tools_used"]:
			print(f"    → {tool}")

	# Línea resumen estilo CLI
	useful = usage["input_tokens"] + usage["output_tokens"]
	time_str = fmt_time(elapsed) if elapsed else "?"
	print(f"\n  {GREEN}Done ({n_tools} tool uses · "
		  f"{fmt_tokens(useful)} tokens · {time_str}){RESET}")

	print(f"\n{DIM}  Archivo: {usage['session_file']}{RESET}")
	print()


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
	parser = argparse.ArgumentParser(description="Planner standalone — genera plan.json desde reader-context.json.")
	parser.add_argument("--skip-validation", action="store_true", help="Saltarse validación de reader-context.json")
	parser.add_argument("--model", choices=["haiku", "sonnet", "opus"], default="opus", help="Modelo a usar (default: opus)")
	args = parser.parse_args()

	model_id = {
		"haiku": "claude-haiku-4-5-20251001",
		"sonnet": "claude-sonnet-4-6",
		"opus": "claude-opus-4-6",
	}[args.model]
	prices = MODEL_PRICES[model_id]

	print(f"\n{CYAN}{'='*60}")
	print(f"  PLANNER — generando plan.json")
	print(f"{'='*60}{RESET}\n")

	# Validar que reader-context.json existe y es válido
	if not args.skip_validation:
		ctx = validate_reader_context()
		if not ctx:
			print(f"{RED}Error: {READER_CONTEXT} no existe o no es válido JSON.{RESET}")
			print(f"{DIM}(Ejecuta reader-only.py primero o usa --skip-validation){RESET}")
			return 1
		print(f"{GREEN}✓ reader-context.json validado{RESET}")
		print(f"  - Tarea: {ctx.get('improved_prompt', '?')[:60]}...")
		print(f"  - Archivos a abrir: {len(ctx.get('files_to_open', []))}")
		print(f"  - Archivos a revisar: {len(ctx.get('files_to_review', []))}\n")
	else:
		print(f"{YELLOW}⚠  Validación saltada (--skip-validation){RESET}\n")

	# Cargar planner.md base (sin frontmatter)
	base_prompt = load_planner_prompt()
	if not base_prompt:
		print(f"{RED}Error: no se encontró {PLANNER_AGENT}{RESET}")
		return 1

	# Construir system prompt dinámico + mensaje del usuario
	allowed_paths: list[str] = []
	if not args.skip_validation:
		# Generar system prompt con sección dinámica de archivos autorizados
		planner_prompt, allowed_paths, size_map = build_dynamic_prompt(base_prompt, ctx)

		# Construir user_message limpio — sin redundancia con system prompt
		# (tamaños, hints y key_symbols ya están en la sección "Archivos autorizados" del system prompt)
		open_paths = [f["path"] for f in ctx.get("files_to_open", [])]
		review_paths = [f["path"] for f in ctx.get("files_to_review", [])]
		# Marcar archivos que no existen
		missing = [p for p, n in size_map.items() if n == "NO EXISTE"]

		parts = [f"## Tarea\n{ctx.get('improved_prompt', '')}"]

		constraints = ctx.get("constraints", [])
		if constraints:
			parts.append("## Restricciones\n" + "\n".join(f"- {c}" for c in constraints))

		key_facts = ctx.get("key_facts", [])
		if key_facts:
			parts.append("## Datos clave\n" + "\n".join(f"- {f}" for f in key_facts))

		if open_paths:
			parts.append("## files_to_open\n" + "\n".join(f"- {p}" for p in open_paths))

		if review_paths:
			parts.append("## files_to_review\n" + "\n".join(f"- {p}" for p in review_paths))

		dep_graph = ctx.get("dependency_graph")
		if dep_graph:
			dep_lines = [f"- {k} → [{', '.join(v)}]" for k, v in dep_graph.items()]
			parts.append("## Dependencias\n" + "\n".join(dep_lines))

		if missing:
			parts.append("## ⚠️ Archivos que NO existen\n" + "\n".join(f"- {p} → registrar en risks" for p in missing))

		parts.append("Genera plan.json.")

		user_message = "\n\n".join(parts)

		print(f"{GREEN}✓ System prompt dinámico: {len(allowed_paths)} archivos inyectados{RESET}")
	else:
		planner_prompt = base_prompt
		user_message = "Genera plan.json según tus instrucciones."

	# Generar allowlist para el hook guard-planner.py (enforcement real)
	if allowed_paths:
		write_allowlist(allowed_paths)
		print(f"{GREEN}✓ Guard activado: {len(allowed_paths)} archivos permitidos{RESET}")
		print(f"  {DIM}(hook: guard-planner.py → bloquea reads fuera de lista + duplicados){RESET}\n")

	# Lanzar claude con el system prompt dinámico
	cmd = [
		"claude",
		"--model", model_id,
		"--system-prompt", planner_prompt,
		"--dangerously-skip-permissions",
	]

	print(f"{BOLD}Ejecutando planner ({prices['label']})...{RESET}\n")

	before = snapshot_sessions(SESSION_DIR)
	start  = time.time()

	try:
		result = subprocess.run(cmd, input=user_message, text=True)
	finally:
		# Limpiar archivos del guard pase lo que pase
		cleanup_guard_files()

	elapsed = time.time() - start

	if result.returncode != 0:
		print(f"\n{RED}Planner terminó con error (código {result.returncode}).{RESET}")
		return result.returncode

	print(f"\n{GREEN}Completado en {fmt_time(elapsed)}{RESET}")

	# Verificar que plan.json fue escrito
	if PLAN_JSON.exists():
		try:
			plan = json.loads(PLAN_JSON.read_text(encoding="utf-8"))
			n_steps = len(plan.get("steps", []))
			print(f"\n{GREEN}plan.json: {n_steps} pasos identificados{RESET}")
		except (json.JSONDecodeError, OSError) as e:
			print(f"\n{RED}plan.json existe pero no es JSON válido: {e}{RESET}")
	else:
		print(f"\n{RED}El planner no escribió plan.json.{RESET}")

	# Buscar la sesión NUEVA (no la modificada, la que no existía antes)
	session_path = find_new_session(before, SESSION_DIR)
	if session_path:
		usage = parse_session_tokens(session_path, prices)
		if usage:
			print_usage(usage, prices, elapsed)
		else:
			print(f"\n{YELLOW}Sesión encontrada pero sin datos de tokens.{RESET}")
	else:
		print(f"\n{YELLOW}No se detectó sesión nueva en {SESSION_DIR}{RESET}")
		print(f"{DIM}(Sesiones existentes: {len(before)}){RESET}")

	return 0


if __name__ == "__main__":
	sys.exit(main())
