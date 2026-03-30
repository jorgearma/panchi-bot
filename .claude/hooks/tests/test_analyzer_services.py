"""Tests para analyzers/services.py."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analyzers import core
from analyzers.services import run


def _make_project_with_services(tmp_path):
    (tmp_path / "requirements.txt").write_text(
        "Flask==3.1.0\ntwilio==9.4.6\nredis==5.2.1\nsentry-sdk==2.54.0\n"
    )
    svc_dir = tmp_path / "services"
    svc_dir.mkdir()
    (svc_dir / "twilio_service.py").write_text(
        'import twilio\nTWILIO_ACCOUNT_SID = os.environ["TWILIO_ACCOUNT_SID"]\n'
        'def enviar_mensaje(to, body): pass\n'
        'def procesar_respuesta(data): pass\n'
    )
    (svc_dir / "cache_service.py").write_text(
        'import redis\nREDIS_URL = os.environ.get("REDIS_URL")\n'
        'def get_cache(key): pass\n'
        'def set_cache(key, value): pass\n'
    )
    maps_dir = tmp_path / ".claude" / "maps"
    maps_dir.mkdir(parents=True)
    return tmp_path, maps_dir


def test_run_returns_required_keys(tmp_path):
    root, _ = _make_project_with_services(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    assert result["domain"] == "services"
    assert "candidates" in result


def test_sdk_imports_become_seed_candidates(tmp_path):
    root, _ = _make_project_with_services(tmp_path)
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    twilio = next(
        candidate
        for candidate in result["candidates"]
        if candidate["path"] == "services/twilio_service.py"
    )
    assert twilio["open_priority"] == "seed"
    assert "integration:Twilio" in twilio["contracts"]
    assert "env:TWILIO_ACCOUNT_SID" in twilio["contracts"]


def test_env_only_service_file_becomes_review_candidate(tmp_path):
    root, _ = _make_project_with_services(tmp_path)
    (root / "services" / "mail_adapter.py").write_text(
        "MAIL_API_KEY = os.environ.get('MAIL_API_KEY')\n"
        "def send_mail():\n"
        "    pass\n"
    )
    files = core.walk_repo(root)
    stack = core.detect_stack(root)
    result = run(root, files, stack)
    mail_adapter = next(
        candidate
        for candidate in result["candidates"]
        if candidate["path"] == "services/mail_adapter.py"
    )
    assert mail_adapter["open_priority"] == "review"
    assert "env:MAIL_API_KEY" in mail_adapter["contracts"]


def test_empty_project_returns_empty_integrations(tmp_path):
    (tmp_path / "main.py").write_text("print('hello')")
    maps_dir = tmp_path / ".claude" / "maps"
    maps_dir.mkdir(parents=True)
    files = core.walk_repo(tmp_path)
    stack = core.detect_stack(tmp_path)
    result = run(tmp_path, files, stack)
    assert result == {"domain": "services", "candidates": []}


def test_services_map_integrations_have_test_file(tmp_path):
    from analyzers.core import walk_repo, detect_stack
    from analyzers.services import run

    (tmp_path / "services").mkdir()
    (tmp_path / "services" / "stripe_service.py").write_text(
        "import stripe\nSTRIPE_KEY = os.getenv('STRIPE_SECRET_KEY')\ndef charge(amount): pass\n"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_stripe_service.py").write_text("def test_charge(): pass\n")
    (tmp_path / ".git").mkdir()

    files = walk_repo(tmp_path)
    stack = detect_stack(tmp_path)
    result = run(tmp_path, files, stack)

    for candidate in result["candidates"]:
        assert "test_files" in candidate, f"candidato {candidate['path']} no tiene test_files"
