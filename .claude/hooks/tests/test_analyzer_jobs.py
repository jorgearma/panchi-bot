"""Tests para analyzers/jobs.py."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analyzers import core
from analyzers.jobs import run


def _make_project_with_celery(tmp_path):
    (tmp_path / "requirements.txt").write_text("celery==5.3.0\nredis==5.2.1\n")
    (tmp_path / "tasks.py").write_text(
        'from celery import Celery\n'
        'app = Celery("tasks")\n\n'
        '@app.task\n'
        'def enviar_notificacion(user_id):\n'
        '    """Envía notificación por email al usuario."""\n'
        '    pass\n\n'
        '@app.task(bind=True)\n'
        'def procesar_pago(self, pedido_id):\n'
        '    pass\n'
    )
    maps_dir = tmp_path / ".claude" / "maps"
    maps_dir.mkdir(parents=True)
    return tmp_path, maps_dir


def test_run_returns_required_keys(tmp_path):
    root, _ = _make_project_with_celery(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    assert result["domain"] == "jobs"
    assert "candidates" in result


def test_writes_domain_index_jobs(tmp_path):
    root, _ = _make_project_with_celery(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    assert result["domain"] == "jobs"
    assert (root / ".claude" / "maps" / "DOMAIN_INDEX_jobs.json").exists()


def test_task_file_is_seed_candidate_with_job_contracts(tmp_path):
    root, _ = _make_project_with_celery(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    candidate = next(
        candidate
        for candidate in result["candidates"]
        if candidate["path"] == "tasks.py"
    )
    assert candidate["open_priority"] == "seed"
    assert "job:enviar_notificacion" in candidate["contracts"]
    assert "job:procesar_pago" in candidate["contracts"]
    assert "trigger:manual" in candidate["contracts"]


def test_manual_job_files_are_review_candidates(tmp_path):
    (tmp_path / "requirements.txt").write_text("celery==5.3.0\n")
    (tmp_path / "cleanup_job.py").write_text(
        "def run():\n"
        "    return True\n"
    )
    (tmp_path / ".claude" / "maps").mkdir(parents=True)
    files = core.walk_repo(tmp_path)
    stack = core.detect_stack(tmp_path)

    result = run(tmp_path, files, stack)

    candidate = next(
        candidate
        for candidate in result["candidates"]
        if candidate["path"] == "cleanup_job.py"
    )
    assert candidate["open_priority"] == "review"
    assert "trigger:manual" in candidate["contracts"]


def test_empty_project_returns_empty_candidates(tmp_path):
    (tmp_path / "main.py").write_text("print('hello')")
    maps_dir = tmp_path / ".claude" / "maps"
    maps_dir.mkdir(parents=True)
    files = core.walk_repo(tmp_path)
    stack = core.detect_stack(tmp_path)
    result = run(tmp_path, files, stack)
    assert result == {"domain": "jobs", "candidates": []}


def test_jobs_map_jobs_have_test_file(tmp_path):
    from analyzers.core import walk_repo, detect_stack
    from analyzers.jobs import run

    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "email_tasks.py").write_text(
        "from celery import shared_task\n@shared_task\ndef send_welcome_email(user_id): pass\n"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_email_tasks.py").write_text("def test_send_welcome_email(): pass\n")
    (tmp_path / ".git").mkdir()
    (tmp_path / "requirements.txt").write_text("celery==5.3.0\n")

    files = walk_repo(tmp_path)
    stack = detect_stack(tmp_path)
    result = run(tmp_path, files, stack)

    for candidate in result["candidates"]:
        assert "test_files" in candidate, f"job {candidate['path']} no tiene test_files"
