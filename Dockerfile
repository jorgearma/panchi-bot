# syntax=docker/dockerfile:1
# ─────────────────────────────────────────────────────────────
# panchi-bot · Flask + gunicorn + RQ workers (misma imagen)
# Multi-stage: pip, curl y gnupg SOLO viven en la etapa de build.
# Base fijada por versión + DIGEST (OWASP #9/#13); Dependabot la actualiza.
# Las DOS etapas usan la MISMA base: el venv depende de la versión exacta de Python.
# ─────────────────────────────────────────────────────────────

# ── ETAPA 1: build ───────────────────────────────────────────
FROM python:3.15-slim-bookworm@sha256:96599df822d0e1c6bb700014a05c7f3c8cabc6e0f7ff3c4f9f69cee033b4b5d9 AS build
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Clave del repo de Microsoft (para msodbcsql18). Se descarga AQUÍ y se comprueba
# su huella: si alguien la cambia en el camino, el build falla.
# hadolint ignore=DL3008
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl gnupg \
 && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc -o /microsoft-prod.asc \
 && gpg --show-keys --with-colons /microsoft-prod.asc | grep -q '^fpr:::::::::BC528686B50D79E339D3721CEB3E94ADBE1229CF:$' \
 && rm -rf /var/lib/apt/lists/*

# venv en ruta fija → se copia entero a la etapa final
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
# Primero solo requirements → la capa de dependencias se cachea
COPY requirements.txt .
RUN pip install -r requirements.txt \
 && python -m spacy download es_core_news_sm \
 && pip uninstall -y pip

# ── ETAPA 2: imagen final ────────────────────────────────────
FROM python:3.15-slim-bookworm@sha256:96599df822d0e1c6bb700014a05c7f3c8cabc6e0f7ff3c4f9f69cee033b4b5d9

LABEL org.opencontainers.image.title="panchi-bot" \
      org.opencontainers.image.source="https://github.com/jorgearma/panchi-bot"

# PYTHONDONTWRITEBYTECODE: no intenta escribir .pyc (el FS es read-only en el compose)
# PYTHONUNBUFFERED: logs al momento en docker logs
# HOME=/tmp: el usuario no tiene home; si alguna librería quiere caché, va al tmpfs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    HOME=/tmp \
    LOG_FILE=/app/logs/panchi-bot.log

# Driver ODBC 18 de SQL Server. Solo el runtime (unixodbc), sin cabeceras -dev,
# sin curl, sin recommends. apt habla HTTPS solo, no hace falta curl.
# Versión de msodbcsql18 sin fijar a propósito: Microsoft retira las antiguas del repo.
COPY --from=build /microsoft-prod.asc /usr/share/keyrings/microsoft-prod.asc
# hadolint ignore=DL3008
RUN echo "deb [signed-by=/usr/share/keyrings/microsoft-prod.asc] https://packages.microsoft.com/debian/12/prod bookworm main" \
      > /etc/apt/sources.list.d/mssql-release.list \
 && apt-get update \
 && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd -r -g 10001 appuser \
 && useradd -r -u 10001 -g appuser -s /usr/sbin/nologin -M appuser

# Todo lo copiado es de root → appuser NO puede modificar su código ni sus librerías.
COPY --from=build /opt/venv /opt/venv
WORKDIR /app
# COPY . . filtrado por .dockerignore (allowlist: solo entra lo que se lista allí con "!")
COPY . .

# Único sitio escribible de la imagen: los logs (en el compose, volumen/tmpfs)
RUN mkdir -p /app/logs && chown appuser:appuser /app/logs

USER 10001
EXPOSE 5000

# Sin curl en la imagen → healthcheck con Python. Los workers lo desactivan en el compose.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health', timeout=4)"]

CMD ["gunicorn", "--config", "gunicorn.conf.py", "main:app"]
