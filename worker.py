"""Entry point del worker RQ.

Arranca un worker que consume 3 colas en orden de prioridad:
1. whatsapp (CRÍTICA - mensajes al cliente)
2. pedidos (IMPORTANTE - operacional)
3. dashboard (BACKGROUND - métricas/observabilidad)

Los workers se balancean automáticamente: si una cola está vacía,
van a la siguiente. Si están todos ocupados, todos ayudan.

Uso:
    python worker.py                    # worker único (dev)
    docker-compose up --scale worker=2  # 2 workers (producción)
"""
import logging
from dotenv import load_dotenv
load_dotenv()

from message_queue import QUEUES_PRIORITY
from rq import Worker

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    # Todos los workers escuchan las mismas colas en orden de prioridad
    worker = Worker(QUEUES_PRIORITY, connection=QUEUES_PRIORITY[0].connection)
    logger.info(f"Worker iniciado. Colas: {[q.name for q in QUEUES_PRIORITY]}")
    worker.work()
