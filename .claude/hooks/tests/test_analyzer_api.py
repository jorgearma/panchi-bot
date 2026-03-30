"""Tests para analyzers/api.py."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analyzers import core
from analyzers.api import run


def _make_flask_api(tmp_path):
    (tmp_path / "requirements.txt").write_text("Flask==3.1.0\n")
    bp_dir = tmp_path / "blueprints"
    bp_dir.mkdir()
    (bp_dir / "pedidos.py").write_text(
        'from flask import Blueprint\n'
        'from utils.auth import login_required\n'
        'bp = Blueprint("pedidos", __name__, url_prefix="/api/pedidos")\n\n'
        '@bp.route("/", methods=["GET"])\n'
        '@login_required\n'
        'def listar_pedidos():\n'
        '    pass\n\n'
        '@bp.route("/<int:pid>", methods=["PUT"])\n'
        'def actualizar_pedido(pid):\n'
        '    pass\n\n'
        '@bp.route("/webhook", methods=["POST"])\n'
        'def twilio_webhook():\n'
        '    pass\n'
    )
    (tmp_path / "utils").mkdir()
    (tmp_path / "utils" / "auth.py").write_text("def login_required(f): return f")
    maps_dir = tmp_path / ".claude" / "maps"
    maps_dir.mkdir(parents=True)
    return tmp_path, maps_dir


def test_run_returns_required_keys(tmp_path):
    root, _ = _make_flask_api(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    assert result["domain"] == "api"
    assert "candidates" in result


def test_writes_domain_index_file(tmp_path):
    root, _ = _make_flask_api(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    assert result["domain"] == "api"
    assert (root / ".claude" / "maps" / "DOMAIN_INDEX_api.json").exists()


def test_route_file_is_seed_candidate_with_contracts(tmp_path):
    root, _ = _make_flask_api(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    candidate = next(
        candidate
        for candidate in result["candidates"]
        if candidate["path"] == "blueprints/pedidos.py"
    )
    assert candidate["open_priority"] == "seed"
    assert "GET /api/pedidos" in candidate["contracts"]
    assert "PUT /api/pedidos/<int:pid>" in candidate["contracts"]


def test_webhook_routes_are_exposed_as_contracts(tmp_path):
    root, _ = _make_flask_api(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    candidate = next(
        candidate
        for candidate in result["candidates"]
        if candidate["path"] == "blueprints/pedidos.py"
    )
    assert "POST /api/pedidos/webhook" in candidate["contracts"]
    assert "has_webhook_route" in candidate["confidence_signals"]


def test_auth_file_becomes_review_candidate(tmp_path):
    root, _ = _make_flask_api(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    candidate = next(
        candidate
        for candidate in result["candidates"]
        if candidate["path"] == "utils/auth.py"
    )
    assert candidate["open_priority"] == "review"
    assert "is_middleware" in candidate["confidence_signals"]


def test_empty_project_returns_empty_structure(tmp_path):
    (tmp_path / "main.py").write_text("print('hello')")
    maps_dir = tmp_path / ".claude" / "maps"
    maps_dir.mkdir(parents=True)
    files = core.walk_repo(tmp_path)
    stack = core.detect_stack(tmp_path)
    result = run(tmp_path, files, stack)
    assert result == {"domain": "api", "candidates": []}


def test_schema_files_become_review_candidates(tmp_path):
    root, _ = _make_flask_api(tmp_path)
    (root / "schemas").mkdir()
    (root / "schemas" / "auth.py").write_text(
        "from pydantic import BaseModel\n"
        "class LoginRequest(BaseModel):\n"
        "    email: str\n"
    )
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    candidate = next(
        candidate
        for candidate in result["candidates"]
        if candidate["path"] == "schemas/auth.py"
    )
    assert candidate["open_priority"] == "review"
    assert "is_schema_file" in candidate["confidence_signals"]

def test_api_blueprint_has_test_file(tmp_path):
    from analyzers.core import walk_repo, detect_stack
    from analyzers.api import run

    (tmp_path / "blueprints").mkdir()
    (tmp_path / "blueprints" / "auth.py").write_text(
        "from flask import Blueprint\nauth = Blueprint('auth', __name__)\n@auth.route('/login', methods=['POST'])\ndef login(): pass\n"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_auth.py").write_text("def test_login(): pass\n")
    (tmp_path / ".git").mkdir()

    files = walk_repo(tmp_path)
    stack = detect_stack(tmp_path)
    result = run(tmp_path, files, stack)

    assert result["candidates"], "debe haber al menos un candidato"
    candidate = result["candidates"][0]
    assert candidate["test_files"] == ["tests/test_auth.py"]
