"""Cola de mensajes WhatsApp.

Instancia RQ compartida por blueprints (enqueue) y worker.py (consume).
Patrón idéntico a database.py — infraestructura, sin lógica de negocio.
"""
import logging

from redis import Redis
from rq import Queue

import config

logger = logging.getLogger(__name__)

_redis_conn = Redis(
    host=config.REDIS_HOST,
    port=config.REDIS_PORT,
    db=config.REDIS_DB,
    socket_timeout=3,
    socket_connect_timeout=3,
)

message_queue = Queue("whatsapp", connection=_redis_conn)
