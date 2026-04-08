import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch


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
