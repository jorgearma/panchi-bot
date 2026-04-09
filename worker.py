"""Entry point del worker RQ.

Colas disponibles (en orden de prioridad):
1. whatsapp (CRÍTICA - mensajes al cliente)
2. pedidos (IMPORTANTE - operacional)
3. dashboard (BACKGROUND - métricas/observabilidad)

Uso:
    python worker.py                          # todas las colas (dev)
    python worker.py whatsapp                 # worker dedicado crítico
    python worker.py pedidos dashboard        # worker background
    docker-compose up --scale worker=2        # N workers (producción)
"""
import logging
import sys
from dotenv import load_dotenv
load_dotenv()

from message_queue import QUEUES_PRIORITY, queue_whatsapp, queue_pedidos, queue_dashboard
from rq import Worker

logger = logging.getLogger(__name__)

_COLA_MAP = {
    "whatsapp": queue_whatsapp,
    "pedidos": queue_pedidos,
    "dashboard": queue_dashboard,
}

if __name__ == "__main__":
    nombres = sys.argv[1:]
    if nombres:
        colas = [_COLA_MAP[n] for n in nombres if n in _COLA_MAP]
        if not colas:
            print(f"Colas válidas: {list(_COLA_MAP)}", file=sys.stderr)
            sys.exit(1)
    else:
        colas = QUEUES_PRIORITY

    worker = Worker(colas, connection=colas[0].connection)
    logger.info("Worker iniciado. Colas: %s", [q.name for q in colas])
    worker.work()
