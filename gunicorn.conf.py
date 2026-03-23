import logging

bind = "0.0.0.0:5000"
workers = 2
timeout = 30
accesslog = "-"
errorlog = "-"
loglevel = "info"


# ---------------------------------------------------------------------------
# Rutas que siempre se loguean (independientemente del status code)
# ---------------------------------------------------------------------------
_RUTAS_CRITICAS = (
    "/webhook",          # mensajes WhatsApp (Twilio y Meta)
    "/webhoo/monei",     # typo legacy de Monei — mantener hasta eliminar la ruta
    "/auth/login",
    "/auth/logout",
)

# ---------------------------------------------------------------------------
# Prefijos de rutas que se suprimen si el status code es 2xx o 3xx
# ---------------------------------------------------------------------------
_RUTAS_POLLING = (
    "/dashboard/metricas",
    "/dashboard/pedidos-activos",
    "/dashboard/picking",
    "/dashboard/repartidores",
    "/dashboard/alertas",
    "/dashboard/eventos",
    "/dashboard/mapa",
    "/dashboard/empleados",
    "/empleado/carga-operativa",
    "/empleado/metricas",
    "/empleado/estado",
    "/empleado/turno-hoy",
    "/empleado/fichaje/hoy",
    "/empleado/perfil",
    "/empleado/capacidades",
    "/picker/mis-pedidos",
    "/picker/cola",
    "/repartidor/mis-pedidos",
    "/repartidor/cola",
    "/repartidor/cierre/datos",
    "/api/seguimiento/",
    "/metricas/operacion/",
    "/metricas/analitica/",
    "/health",
)


class _FiltroAcceso(logging.Filter):
    """
    Suprime líneas de acceso ruidosas y deja pasar solo lo relevante:
    - Siempre: errores 4xx y 5xx
    - Siempre: rutas críticas (webhooks, login, pagos)
    - Suprimidas: polling y recargas de templates con 2xx/3xx
    """

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()

        # Extraer status code y path del formato de log de gunicorn:
        # '127.0.0.1 - - [date] "GET /path HTTP/1.1" 200 123'
        try:
            parts = msg.split('"')
            if len(parts) < 3:
                return True
            request_line = parts[1]          # "GET /path HTTP/1.1"
            after_request = parts[2].strip() # "200 123"
            method = request_line.split(" ")[0]
            path = request_line.split(" ")[1] if " " in request_line else ""
            status = int(after_request.split(" ")[0])
        except (IndexError, ValueError):
            return True  # si no se puede parsear, dejar pasar

        # Siempre loguear errores
        if status >= 400:
            return True

        # Siempre loguear POST, PUT, DELETE (acciones reales)
        if method in ("POST", "PUT", "DELETE", "PATCH"):
            return True

        # Siempre loguear rutas críticas (GET de webhooks, login)
        if any(path.startswith(r) for r in _RUTAS_CRITICAS):
            return True

        # Suprimir GET de polling y recargas de templates con 2xx/3xx
        if any(path.startswith(r) for r in _RUTAS_POLLING):
            return False

        return True


def on_starting(server):
    logging.getLogger("gunicorn.access").addFilter(_FiltroAcceso())
