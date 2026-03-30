#!/usr/bin/env python3
"""Writer standalone — convierte plan.json en execution-brief. Sin confirmaciones."""

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
PLAN_JSON = RUNTIME / "plan.json"
BRIEF_JSON = RUNTIME / "execution-brief.json"
BRIEF_MD = RUNTIME / "execution-brief.md"
WRITER_AGENT = PLUGIN_DIR / "agents" / "writer.md"
BRIEF_SCHEMA = PLUGIN_DIR / "schemas" / "execution-brief.json"
ALLOWLIST_FILE = RUNTIME / "writer-allowlist.json"
READS_LOG = RUNTIME / "writer-reads.log"
WRITES_LOG = RUNTIME / "writer-writes.log"
SESSION_DIR = Path.home() / ".claude" / "projects" / str(PROJECT_ROOT).replace("/", "-").replace("\\", "-")

# Archivos que el writer puede leer
ALLOWED_READS = [
	".claude/runtime/plan.json",
	".claude/schemas/execution-brief.json",
]

# Archivos que el writer puede escribir
ALLOWED_WRITES = [
	".claude/runtime/execution-brief.json",
	".claude/runtime/execution-brief.md",
]


def load_writer_prompt() -> str | None:
	"""Lee writer.md y quita el frontmatter YAML (--- ... ---)."""
	try:
		content = WRITER_AGENT.read_text(encoding="utf-8")
	except OSError:
		return None
	if content.startswith("---"):
		end = content.find("---", 3)
		if end != -1:
			content = content[end + 3:].lstrip("\n")
	return content


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
	return max(new_files, key=lambda p: p.stat().st_mtime)


def parse_session_tokens(path: Path, prices: dict) -> dict | None:
	"""Lee el .jsonl y suma tokens de llamadas API únicas.

	Claude Code a veces divide una misma request en varios eventos assistant
	con el mismo requestId (por ejemplo texto preliminar + tool_use).
	Aquí se agrupan por requestId para no duplicar tokens ni inflar turnos.
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
					short = "/".join(Path(fp).parts[-3:])
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

	useful = usage["input_tokens"] + usage["output_tokens"]
	time_str = fmt_time(elapsed) if elapsed else "?"
	print(f"\n  {GREEN}Done ({n_tools} tool uses · "
		  f"{fmt_tokens(useful)} tokens · {time_str}){RESET}")

	print(f"\n{DIM}  Archivo: {usage['session_file']}{RESET}")
	print()


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
	parser = argparse.ArgumentParser(description="Writer standalone — convierte plan.json en execution-brief.")
	parser.add_argument("--model", choices=["haiku", "sonnet", "opus"], default="sonnet", help="Modelo a usar (default: sonnet)")
	args = parser.parse_args()

	model_id = {
		"haiku": "claude-haiku-4-5-20251001",
		"sonnet": "claude-sonnet-4-6",
		"opus": "claude-opus-4-6",
	}[args.model]
	prices = MODEL_PRICES[model_id]

	print(f"\n{CYAN}{'='*60}")
	print(f"  WRITER — generando execution-brief")
	print(f"{'='*60}{RESET}\n")

	# Validar que plan.json existe y tiene steps
	if not PLAN_JSON.exists():
		print(f"{RED}Error: {PLAN_JSON} no existe.{RESET}")
		print(f"{DIM}(Ejecuta planner-only.py primero){RESET}")
		return 1

	try:
		plan = json.loads(PLAN_JSON.read_text(encoding="utf-8"))
	except (json.JSONDecodeError, OSError) as e:
		print(f"{RED}Error: plan.json no es válido: {e}{RESET}")
		return 1

	n_steps = len(plan.get("steps", []))
	if n_steps == 0:
		print(f"{RED}Error: plan.json no tiene pasos.{RESET}")
		return 1

	task = plan.get("task", "?")
	print(f"{GREEN}✓ plan.json validado{RESET}")
	print(f"  - Tarea: {task[:70]}...")
	print(f"  - Pasos: {n_steps}\n")

	# Cargar writer.md
	writer_prompt = load_writer_prompt()
	if not writer_prompt:
		print(f"{RED}Error: no se encontró {WRITER_AGENT}{RESET}")
		return 1

	# Generar allowlist para guard-writer.py
	allowlist_data = {
		"allowed_reads": ALLOWED_READS,
		"allowed_writes": ALLOWED_WRITES,
	}
	ALLOWLIST_FILE.write_text(json.dumps(allowlist_data, indent=2), encoding="utf-8")
	for f in (READS_LOG, WRITES_LOG):
		if f.exists():
			f.unlink()
	print(f"{GREEN}✓ Guard activado: {len(ALLOWED_READS)} reads, {len(ALLOWED_WRITES)} writes permitidos{RESET}")
	print(f"  {DIM}(hook: guard-writer.py → bloquea reads/writes fuera de lista + duplicados + Bash/Grep/Glob){RESET}\n")

	# Lanzar claude con el system prompt
	cmd = [
		"claude",
		"--model", model_id,
		"--system-prompt", writer_prompt,
		"--dangerously-skip-permissions",
	]
	user_message = "Convierte plan.json en execution-brief.json y execution-brief.md según tus instrucciones."

	print(f"{BOLD}Ejecutando writer ({prices['label']})...{RESET}\n")

	before = snapshot_sessions(SESSION_DIR)
	start  = time.time()

	try:
		result = subprocess.run(cmd, input=user_message, text=True)
	finally:
		for f in (ALLOWLIST_FILE, READS_LOG, WRITES_LOG):
			if f.exists():
				f.unlink()

	elapsed = time.time() - start

	if result.returncode != 0:
		print(f"\n{RED}Writer terminó con error (código {result.returncode}).{RESET}")
		return result.returncode

	print(f"\n{GREEN}Completado en {fmt_time(elapsed)}{RESET}")

	# Verificar salidas
	for path, label in [(BRIEF_JSON, "execution-brief.json"), (BRIEF_MD, "execution-brief.md")]:
		if path.exists():
			if label.endswith(".json"):
				try:
					brief = json.loads(path.read_text(encoding="utf-8"))
					n_impl = len(brief.get("implementation_steps", []))
					status = brief.get("approval_status", "?")
					print(f"\n{GREEN}{label}: {n_impl} pasos, status={status}{RESET}")
				except (json.JSONDecodeError, OSError) as e:
					print(f"\n{RED}{label} existe pero no es JSON válido: {e}{RESET}")
			else:
				size = path.stat().st_size
				print(f"{GREEN}{label}: {size} bytes{RESET}")
		else:
			print(f"\n{RED}El writer no escribió {label}.{RESET}")

	# Tokens
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
