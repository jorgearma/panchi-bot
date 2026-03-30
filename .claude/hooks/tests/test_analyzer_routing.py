"""Tests para analyzers/routing.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analyzers import core
from analyzers.routing import run


def _make_project(tmp_path):
    (tmp_path / "requirements.txt").write_text("Flask==3.1.0\nSQLAlchemy==2.0.38\n")
    (tmp_path / "main.py").write_text('"""Entry point."""\ndef create_app(): pass\n')
    (tmp_path / "blueprints").mkdir()
    (tmp_path / "blueprints" / "pedidos.py").write_text(
        'from flask import Blueprint\n'
        'bp = Blueprint("pedidos", __name__, url_prefix="/api/pedidos")\n'
        '@bp.route("/", methods=["GET"])\n'
        'def listar():\n'
        '    pass\n'
    )
    maps_dir = tmp_path / ".claude" / "maps"
    maps_dir.mkdir(parents=True)
    return tmp_path, maps_dir


def test_run_writes_routing_map(tmp_path):
    root, maps_dir = _make_project(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)

    result = run(root, files, stack)

    assert (maps_dir / "ROUTING_MAP.json").exists()
    assert "project_summary" in result
    assert "domains" in result
    assert "default_constraints" in result


def test_routing_domains_match_current_reader_indexes(tmp_path):
    root, _ = _make_project(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)

    result = run(root, files, stack)

    domains = {domain["name"]: domain for domain in result["domains"]}
    assert set(domains) == {"api", "data", "services", "ui", "jobs"}
    assert domains["api"]["preferred_indexes"] == ["DOMAIN_INDEX_api.json"]
    assert domains["data"]["preferred_indexes"] == [
        "DOMAIN_INDEX_data.json",
        "DATA_MODEL_MAP.json",
    ]


def test_routing_includes_entry_points_and_stack(tmp_path):
    root, _ = _make_project(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)

    result = run(root, files, stack)

    assert "main.py" in result["entry_points"]
    assert "Flask" in result["project_summary"]["stack"]
