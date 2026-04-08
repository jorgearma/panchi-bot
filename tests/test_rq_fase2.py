import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch, call


# ── Task 1: Models ────────────────────────────────────────────────────────────

def test_failed_job_model_campos():
    """FailedJob tiene todos los campos requeridos."""
    from models import FailedJob
    fj = FailedJob(
        job_id="abc123",
        job_type="descontar_stock_picking_job",
        queue_name="dashboard",
        payload='["picking_id_42"]',
        error="Connection refused",
        retries=3,
    )
    assert fj.job_id == "abc123"
    assert fj.job_type == "descontar_stock_picking_job"
    assert fj.queue_name == "dashboard"
    assert fj.retries == 3
    assert fj.resolved_at is None


def test_picking_pedido_tiene_stock_descontado():
    """PickingPedido tiene columna stock_descontado NOT NULL DEFAULT False."""
    from models import PickingPedido
    from sqlalchemy import inspect as sa_inspect

    mapper = sa_inspect(PickingPedido)
    col = mapper.columns['stock_descontado']
    assert col is not None, "stock_descontado no definido en PickingPedido"
    assert col.nullable is False
    # default aplicado en SQL INSERT, no en construcción Python
    assert col.default.arg is False


# ── Task 2: rq_callbacks ──────────────────────────────────────────────────────

def test_on_job_failure_persiste_en_bd(app):
    """on_job_failure crea FailedJob en BD."""
    from utils.rq_callbacks import on_job_failure
    from models import FailedJob

    job = MagicMock()
    job.id = "job-123"
    job.func_name = "descontar_stock_picking_job"
    job.origin = "dashboard"
    job.args = (42,)
    job.retries_left = 0

    error = Exception("Connection refused")

    with app.app_context():
        with patch('database.SessionLocal') as mock_sl, \
             patch('utils.rq_callbacks.sentry_sdk') as mock_sentry:
            mock_s = MagicMock()
            mock_sl.return_value = mock_s

            on_job_failure(job, None, type(error), error, None)

            mock_s.add.assert_called_once()
            added = mock_s.add.call_args[0][0]
            assert isinstance(added, FailedJob)
            assert added.job_id == "job-123"
            assert added.job_type == "descontar_stock_picking_job"
            assert added.queue_name == "dashboard"
            mock_s.commit.assert_called_once()
            mock_sentry.capture_exception.assert_called_once_with(error)


def test_on_job_failure_sentry_si_bd_cae(app):
    """Si BD falla en on_job_failure, Sentry recibe alerta igualmente."""
    from utils.rq_callbacks import on_job_failure

    job = MagicMock()
    job.id = "job-456"
    job.func_name = "notificar_picker_job"
    job.origin = "whatsapp"
    job.args = ("+34600000001", 99)
    job.retries_left = 0
    error = Exception("timeout")

    with app.app_context():
        with patch('database.SessionLocal') as mock_sl, \
             patch('utils.rq_callbacks.sentry_sdk') as mock_sentry:
            mock_s = MagicMock()
            mock_s.commit.side_effect = Exception("BD caída")
            mock_sl.return_value = mock_s

            on_job_failure(job, None, type(error), error, None)

            mock_sentry.capture_exception.assert_called_once_with(error)


def test_sentry_job_decorator_propaga_excepcion():
    """@sentry_job propaga excepciones del job."""
    from utils.rq_callbacks import sentry_job

    @sentry_job(op_name="rq.test")
    def job_que_falla():
        raise ValueError("algo salió mal")

    with patch('utils.rq_callbacks.sentry_sdk'):
        with pytest.raises(ValueError, match="algo salió mal"):
            job_que_falla()


def test_sentry_job_decorator_devuelve_resultado():
    """@sentry_job devuelve el resultado del job correctamente."""
    from utils.rq_callbacks import sentry_job

    @sentry_job(op_name="rq.test")
    def job_exitoso(x):
        return x * 2

    with patch('utils.rq_callbacks.sentry_sdk') as mock_sentry:
        mock_tx = MagicMock()
        mock_sentry.start_transaction.return_value.__enter__ = MagicMock(return_value=mock_tx)
        mock_sentry.start_transaction.return_value.__exit__ = MagicMock(return_value=False)

        result = job_exitoso(5)
        assert result == 10
