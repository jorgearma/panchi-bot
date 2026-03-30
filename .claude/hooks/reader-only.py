#!/usr/bin/env python3
"""Reader standalone — lee MAPs, crea reader-context.json. Sin confirmaciones."""

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
READER_AGENT = PLUGIN_DIR / "agents" / "reader.md"
ALLOWLIST_FILE = RUNTIME / "reader-allowlist.json"
READS_LOG = RUNTIME / "reader-reads.log"
WRITES_LOG = RUNTIME / "reader-writes.log"
SESSION_DIR = Path.home() / ".claude" / "projects" / str(PROJECT_ROOT).replace("/", "-").replace("\\", "-")

# MAPs que el reader puede leer
ALLOWED_MAPS = [
    ".claude/maps/ROUTING_MAP.json",
    ".claude/maps/DOMAIN_INDEX_api.json",
    ".claude/maps/DOMAIN_INDEX_data.json",
    ".claude/maps/DOMAIN_INDEX_ui.json",
    ".claude/maps/DOMAIN_INDEX_services.json",
    ".claude/maps/DOMAIN_INDEX_jobs.json",
    ".claude/maps/CONTRACT_MAP.json",
    ".claude/maps/DATA_MODEL_MAP.json",
    ".claude/maps/DEPENDENCY_MAP.json",
    ".claude/maps/TEST_MAP.json",
]


def load_reader_prompt() -> str | None:
    """Lee reader.md y quita el frontmatter YAML (--- ... ---)."""
    try:
        content = READER_AGENT.read_text(encoding="utf-8")
    except OSError:
        return None
    # Quitar frontmatter YAML
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
    print(f"    Tokens nuevos:   {usage['input_tokens']:>10,}  ({fmt_tokens(usage['input_tokens'])})")
    print(f"    Cache leído:     {usage['cache_read']:>10,}  ({fmt_tokens(usage['cache_read'])})")
    print(f"    Cache escrito:   {usage['cache_write']:>10,}  ({fmt_tokens(usage['cache_write'])})")
    print(f"    {'─'*40}")
    print(f"    Total entrada:   {usage['total_in']:>10,}  ({fmt_tokens(usage['total_in'])})")

    print()
    print(f"  {BOLD}Salida:{RESET}")
    print(f"    Tokens output:   {usage['output_tokens']:>10,}  ({fmt_tokens(usage['output_tokens'])})")

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

    # Línea resumen estilo CLI (input+output sin cache = comparable con consola)
    useful = usage["input_tokens"] + usage["output_tokens"]
    time_str = fmt_time(elapsed) if elapsed else "?"
    print(f"\n  {GREEN}Done ({n_tools} tool uses · "
          f"{fmt_tokens(useful)} tokens · {time_str}){RESET}")

    print(f"\n{DIM}  Archivo: {usage['session_file']}{RESET}")
    print()


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Reader standalone — extrae contexto de MAPs.")
    parser.add_argument("petition", help="Petición del usuario en texto libre.")
    parser.add_argument("--model", choices=["haiku", "sonnet", "opus"], default="sonnet", help="Modelo a usar (default: sonnet)")
    args = parser.parse_args()

    model_id = {
        "haiku": "claude-haiku-4-5-20251001",
        "sonnet": "claude-sonnet-4-6",
        "opus": "claude-opus-4-6",
    }[args.model]
    prices = MODEL_PRICES[model_id]

    print(f"\n{CYAN}{'='*60}")
    print(f"  READER — extrayendo contexto de MAPs")
    print(f"{'='*60}{RESET}\n")
    print(f"{BOLD}Tarea:{RESET} {args.petition}\n")

    # Cargar reader.md (sin frontmatter) + petición
    reader_prompt = load_reader_prompt()
    if not reader_prompt:
        print(f"{RED}Error: no se encontró {READER_AGENT}{RESET}")
        return 1

    cmd = [
        "claude",
        "--model", model_id,
        "--system-prompt", reader_prompt,
        "--dangerously-skip-permissions",
        f"Petición del operador: {args.petition}",
    ]

    # Generar allowlist para guard-reader.py
    reader_ctx_rel = str(READER_CONTEXT.relative_to(PROJECT_ROOT))
    allowlist_data = {
        "allowed_reads": ALLOWED_MAPS,
        "allowed_write": reader_ctx_rel,
    }
    ALLOWLIST_FILE.write_text(json.dumps(allowlist_data, indent=2), encoding="utf-8")
    # Limpiar logs de sesiones anteriores
    for f in (READS_LOG, WRITES_LOG):
        if f.exists():
            f.unlink()
    print(f"{GREEN}✓ Guard activado: {len(ALLOWED_MAPS)} MAPs permitidos{RESET}")
    print(f"  {DIM}(hook: guard-reader.py → bloquea reads fuera de MAPs + duplicados + Edit){RESET}\n")

    before = snapshot_sessions(SESSION_DIR)
    start  = time.time()

    try:
        result = subprocess.run(cmd)
    finally:
        # Limpiar archivos del guard pase lo que pase
        for f in (ALLOWLIST_FILE, READS_LOG, WRITES_LOG):
            if f.exists():
                f.unlink()

    elapsed = time.time() - start

    if result.returncode != 0:
        print(f"\n{RED}Reader terminó con error (código {result.returncode}).{RESET}")
        return result.returncode

    print(f"\n{GREEN}Completado en {fmt_time(elapsed)}{RESET}")

    # Verificar que reader-context.json fue escrito
    if READER_CONTEXT.exists():
        try:
            ctx = json.loads(READER_CONTEXT.read_text(encoding="utf-8"))
            status = ctx.get("status", "ready")
            n_open = len(ctx.get("files_to_open", []))
            n_review = len(ctx.get("files_to_review", []))
            print(f"\n{GREEN}reader-context.json: status={status}, "
                  f"files_to_open={n_open}, files_to_review={n_review}{RESET}")
        except (json.JSONDecodeError, OSError) as e:
            print(f"\n{RED}reader-context.json existe pero no es JSON válido: {e}{RESET}")
    else:
        print(f"\n{RED}El agente no escribió reader-context.json — "
              f"el planner no tendrá contexto.{RESET}")

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
