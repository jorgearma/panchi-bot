# Fase 2: Particionado de workers por usuario

## Contexto

En Fase 1 hay una sola cola `whatsapp` y un único worker RQ. El ordering por usuario está garantizado porque es FIFO puro.

Con múltiples workers y cola única, dos workers pueden coger mensajes del mismo usuario simultáneamente. El segundo encontrará el `bloqueo:<phone>` activo en Redis y descartará el mensaje sin reintentarlo — el usuario no recibe respuesta.

**Trigger para implementar esta fase:** empezar a usar más de 2 workers de forma estable, o detectar en logs mensajes descartados por bloqueo durante procesamiento concurrente.

---

## Solución: N colas, una por worker

Cada usuario se asigna siempre a la misma cola mediante `hash(numero) % N`. El mismo worker procesa todos los mensajes de ese usuario → orden garantizado sin locks adicionales.

```
hash(numero) % 3

whatsapp_0  →  worker_0
whatsapp_1  →  worker_1
whatsapp_2  →  worker_2
```

---

## Cambios necesarios

### 1. `config.py`

```python
WORKER_COUNT: int = int(os.environ.get("WORKER_COUNT", "1"))
WORKER_INDEX: int = int(os.environ.get("WORKER_INDEX", "0"))
```

### 2. `message_queue.py`

```python
from redis import Redis
from rq import Queue
import config

_redis_conn = Redis(
    host=config.REDIS_HOST,
    port=config.REDIS_PORT,
    db=config.REDIS_DB,
    socket_timeout=3,
    socket_connect_timeout=3,
)

queues = [
    Queue(f"whatsapp_{i}", connection=_redis_conn)
    for i in range(config.WORKER_COUNT)
]
```

### 3. `services/inbound_whatsapp.py` — función `encolar_mensaje`

```python
def encolar_mensaje(numero: str, mensaje: str, wamid: str | None = None) -> None:
    if wamid and redismanager.ya_procesado_wamid(wamid):
        logger.info("wamid %s ya procesado — duplicado descartado", wamid)
        return
    from message_queue import queues
    idx = hash(numero) % len(queues)
    queues[idx].enqueue(_job_procesar_mensaje, numero, mensaje)
    logger.debug("Mensaje de %s encolado en whatsapp_%s (wamid=%s)", numero, idx, wamid)
```

### 4. `worker.py`

```python
from dotenv import load_dotenv
load_dotenv()

import config
from message_queue import queues
from rq import Worker

if __name__ == "__main__":
    queue = queues[config.WORKER_INDEX]
    worker = Worker([queue], connection=queue.connection)
    worker.work()
```

### 5. `docker-compose.yml`

Reemplazar el servicio `worker` único por un servicio por worker. Ejemplo con 3 workers:

```yaml
worker_0:
  build: .
  command: python worker.py
  depends_on:
    - redis
  env_file: .env
  environment:
    WORKER_INDEX: "0"
    WORKER_COUNT: "3"
  restart: unless-stopped

worker_1:
  build: .
  command: python worker.py
  depends_on:
    - redis
  env_file: .env
  environment:
    WORKER_INDEX: "1"
    WORKER_COUNT: "3"
  restart: unless-stopped

worker_2:
  build: .
  command: python worker.py
  depends_on:
    - redis
  env_file: .env
  environment:
    WORKER_INDEX: "2"
    WORKER_COUNT: "3"
  restart: unless-stopped
```

---

## Consideraciones al cambiar N

Al cambiar `WORKER_COUNT`, el hash de usuarios existentes cambia — un usuario que iba a `whatsapp_1` puede pasar a `whatsapp_0`. Esto no es un problema porque:

- Los mensajes encolados antes del cambio se procesan en las colas antiguas
- Los mensajes nuevos van a las colas nuevas
- No hay estado compartido entre colas del mismo usuario

El único riesgo es durante el despliegue si hay mensajes en vuelo. Despliega en horas de baja actividad.

---

## Cálculo de workers necesarios

```
workers = ceil((mensajes_por_minuto * segundos_por_mensaje) / 60)
```

Añade un 30% de margen. Mide `segundos_por_mensaje` en producción con logs antes de decidir cuántos workers desplegar.

---

## Estado actual (Fase 1)

- Cola: `whatsapp` (única)
- Workers: 1
- Ordering: garantizado
- Archivos relevantes: `message_queue.py`, `worker.py`, `services/inbound_whatsapp.py`
