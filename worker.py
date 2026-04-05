"""Entry point del worker RQ.

Arranca un worker que consume la cola 'whatsapp' y ejecuta
_job_procesar_mensaje() para cada mensaje entrante.

Uso:
    python worker.py
    rq worker whatsapp          # alternativa directa con rq CLI
"""
from dotenv import load_dotenv
load_dotenv()

from message_queue import message_queue
from rq import Worker

if __name__ == "__main__":
    worker = Worker([message_queue], connection=message_queue.connection)
    worker.work()
