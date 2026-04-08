# utils/rq_callbacks.py
import functools
import json
import logging

import sentry_sdk

logger = logging.getLogger(__name__)


def on_job_failure(job, connection, type, value, traceback_obj):
    """RQ callback: persiste en failed_jobs + alerta Sentry al agotar reintentos.

    Tiene try/except propio: si BD está caída, Sentry recibe la alerta de todos modos.
    Se registra en cada enqueue(..., on_failure=on_job_failure).
    """
    from database import SessionLocal
    from models import FailedJob

    # 1. Persistir en BD (best effort)
    s = SessionLocal()
    try:
        s.add(FailedJob(
            job_id=job.id,
            job_type=job.func_name,
            queue_name=job.origin,
            payload=json.dumps(list(job.args)),
            error=str(value),
            retries=getattr(job, 'retries_left', 0),
        ))
        s.commit()
        logger.error("Job fallido persistido en DLQ: %s (job_id=%s)", job.func_name, job.id)
    except Exception as db_err:
        logger.error("No se pudo guardar failed_job en BD: %s", db_err)
        s.rollback()
    finally:
        s.close()

    # 2. Alerta Sentry (siempre, independiente de BD)
    with sentry_sdk.push_scope() as scope:
        scope.set_tag("job_type", job.func_name)
        scope.set_tag("queue", job.origin)
        scope.set_extra("job_id", job.id)
        scope.set_extra("args", job.args)
        sentry_sdk.capture_exception(value)


def sentry_job(op_name: str = "rq.job"):
    """Decorator: wrappea un job RQ con una transacción Sentry Performance."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with sentry_sdk.start_transaction(op=op_name, name=func.__name__):
                return func(*args, **kwargs)
        return wrapper
    return decorator
