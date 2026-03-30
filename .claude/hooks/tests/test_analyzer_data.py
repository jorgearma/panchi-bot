"""Tests para analyzers/data.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analyzers import core
from analyzers.data import run


def _make_project(tmp_path):
    (tmp_path / "requirements.txt").write_text("Flask==3.1.0\nSQLAlchemy==2.0.38\n")
    (tmp_path / "models.py").write_text(
        "from sqlalchemy import Column, Integer, String\n"
        "from sqlalchemy.orm import declarative_base\n"
        "Base = declarative_base()\n"
        "class Pedido(Base):\n"
        "    __tablename__ = 'pedidos'\n"
        "    id = Column(Integer, primary_key=True)\n"
        "    estado = Column(String)\n"
    )
    (tmp_path / "managers").mkdir()
    (tmp_path / "managers" / "pedido_manager.py").write_text(
        "from models import Pedido\n"
        "def get_pedido(session, pedido_id):\n"
        "    return session.query(Pedido).filter_by(id=pedido_id).first()\n"
    )
    maps_dir = tmp_path / ".claude" / "maps"
    maps_dir.mkdir(parents=True)
    return tmp_path, maps_dir


def test_run_writes_domain_index_data(tmp_path):
    root, maps_dir = _make_project(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)

    result = run(root, files, stack)

    assert (maps_dir / "DOMAIN_INDEX_data.json").exists()
    assert result["domain"] == "data"
    assert isinstance(result["candidates"], list)


def test_data_access_files_are_seed_candidates(tmp_path):
    root, _ = _make_project(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)

    result = run(root, files, stack)

    manager = next(
        candidate
        for candidate in result["candidates"]
        if candidate["path"] == "managers/pedido_manager.py"
    )
    assert manager["open_priority"] == "seed"


def test_model_files_are_review_candidates(tmp_path):
    root, _ = _make_project(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)

    result = run(root, files, stack)

    model = next(
        candidate
        for candidate in result["candidates"]
        if candidate["path"] == "models.py"
    )
    assert model["open_priority"] == "review"
    assert "model:Pedido" in model["contracts"]


def test_empty_project_returns_empty_candidates(tmp_path):
    (tmp_path / "main.py").write_text("print('hello')\n")
    (tmp_path / ".claude" / "maps").mkdir(parents=True)
    files = core.walk_repo(tmp_path)
    stack = core.detect_stack(tmp_path)

    result = run(tmp_path, files, stack)

    assert result == {"domain": "data", "candidates": []}
