"""Colas RQ con prioridades.

Instancias RQ compartidas por blueprints (enqueue) y worker.py (consume).
Patrón idéntico a database.py — infraestructura, sin lógica de negocio.

Colas:
- queue_whatsapp: CRÍTICO (mensajes al cliente, tiempo real)
- queue_pedidos: IMPORTANTE (cambios operacionales de pedidos/asignaciones)
- queue_dashboard: BACKGROUND (métricas, estado operativo, reportes)

Los workers escuchan todas las colas en orden de prioridad.
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

# CRÍTICA: Mensajes al cliente (respuesta tiempo real)
queue_whatsapp = Queue("whatsapp", connection=_redis_conn, default_timeout='5m')

# IMPORTANTE: Cambios operacionales (pedidos, asignaciones, pickings, repartos)
queue_pedidos = Queue("pedidos", connection=_redis_conn, default_timeout='5m')

# BACKGROUND: Observabilidad (métricas, estado operativo, reportes)
queue_dashboard = Queue("dashboard", connection=_redis_conn, default_timeout='10m')

# Orden de prioridad para los workers (procesar en este orden)
QUEUES_PRIORITY = [queue_whatsapp, queue_pedidos, queue_dashboard]

# Alias para compatibilidad hacia atrás (código antiguo usa message_queue)
message_queue = queue_whatsapp
