# Guía de despliegue — Panchi-Bot (todo en VPS)

Stack completo en un solo VPS: App + Redis + SQL Server + Nginx con HTTPS.

---

## Resumen de lo que tienes y lo que falta

| Componente | Estado |
|---|---|
| `docker-compose.yml` | ✅ Actualizado (incluye SQL Server) |
| `nginx.local.conf` | ✅ Listo para pruebas locales por HTTP |
| `.prod.conf` | ⚠️ Hay que personalizarlo para HTTPS |nginx
| `gunicorn.conf.py` | ✅ Listo |
| `.env.example` | ✅ Listo |
| `Dockerfile` | ❌ **Falta — paso 1** |

---

## Requisitos del VPS

- **RAM mínima: 4 GB** (SQL Server Express necesita ~2 GB solo él)
- Ubuntu 22.04+
- Docker + Docker Compose v2 instalados
- Un dominio apuntando al VPS (registro A → IP pública del VPS)
- Puertos 80 y 443 abiertos en el firewall

### Instalar Docker en Ubuntu (si no está)
```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
```

---

## Paso 1 — Crear el Dockerfile

Crea el archivo `Dockerfile` en la raíz del proyecto:

```dockerfile
FROM python:3.12-slim

# ODBC Driver 18 para SQL Server — obligatorio para pyodbc
RUN apt-get update && apt-get install -y \
    curl \
    gnupg2 \
    unixodbc-dev \
    && curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - \
    && curl https://packages.microsoft.com/config/debian/11/prod.list \
       > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y msodbcsql18 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Modelo spaCy en español — necesario para validación de nombres
RUN python -m spacy download es_core_news_sm

COPY . .

EXPOSE 5000

CMD ["gunicorn", "main:create_app()", "-c", "gunicorn.conf.py"]
```

---

## Paso 2 — Preparar el .env

```bash
cp .env.example .env
```

Edita `.env`. Estos son los valores exactos para el stack todo-en-VPS:

```bash
# Flask
SECRET_KEY=          # genera con: python3 -c "import secrets; print(secrets.token_hex(32))"

# SQL Server — el nombre 'sqlserver' es el nombre del servicio en docker-compose
SQL_SERVER=sqlserver,1433
SQL_DATABASE=panchibot
SQL_UID=sa
SQL_PWD=             # ⚠️ mínimo 8 chars, 1 mayúscula, 1 número, 1 símbolo. Ej: Panchi2024!

# Redis — el nombre 'redis' es el nombre del servicio en docker-compose
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

# URL pública con https
PUBLIC_URL=https://tudominio.com

# Nginx que montará docker compose en el contenedor
NGINX_CONF=nginx.prod.conf

# WhatsApp — elige uno
WHATSAPP_PROVIDER=meta   # o twilio

# Si usas Meta
META_ACCESS_TOKEN=
META_PHONE_NUMBER_ID=
META_APP_SECRET=
META_VERIFY_TOKEN=   # un string que tú eliges, p.ej: panchi-webhook-2024

# Si usas Twilio
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886

# Monei
MONEI_API_KEY=
MONEI_WEBHOOK_SECRET=

# Google Maps
GOOGLE_MAPS_API_KEY=

# Token interno
INTERNAL_API_TOKEN=  # genera con: python3 -c "import secrets; print(secrets.token_hex(32))"

# Sentry (opcional)
SENTRY_DSN=

# Info del negocio
STORE_PHONE=969123456
STORE_ADDRESS=C/ Mayor 1, Tarancón
```

> **Importante**: `SQL_SERVER=sqlserver,1433` y `REDIS_HOST=redis` usan los nombres
> de los servicios de Docker Compose. Si pones `localhost` fallará.

---

## Paso 3 — HTTPS con Certbot (antes de levantar Docker)

Los webhooks de WhatsApp y Monei **requieren HTTPS**. El certificado se genera
en el host y se monta en el contenedor de Nginx.

```bash
# 1. Instala certbot en el VPS
sudo apt install -y certbot

# 2. Genera el certificado (el puerto 80 debe estar libre — no corras docker-compose todavía)
sudo certbot certonly --standalone -d tudominio.com

# Los certificados quedan en:
# /etc/letsencrypt/live/tudominio.com/fullchain.pem
# /etc/letsencrypt/live/tudominio.com/privkey.pem
```

---

## Paso 4 — Preparar nginx para producción

El proyecto ahora usa dos configuraciones separadas:

- `nginx.local.conf`: para pruebas locales por HTTP
- `nginx.prod.conf`: para el VPS con dominio y HTTPS

Para producción, edita `nginx.prod.conf` y deja este contenido:

```nginx
server {
    listen 80;
    server_name tudominio.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name tudominio.com;

    ssl_certificate     /etc/letsencrypt/live/tudominio.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/tudominio.com/privkey.pem;

    location /health {
        proxy_pass http://app:5000/health;
        access_log off;
    }

    location / {
        proxy_pass http://app:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 30s;
    }
}
```

> Sustituye `tudominio.com` por tu dominio real en los 4 sitios donde aparece.
> En `.env`, deja `NGINX_CONF=nginx.prod.conf` cuando despliegues en el VPS.

---

## Paso 5 — Subir el código al VPS

```bash
# En el VPS, clona el repo
git clone https://github.com/tu-usuario/panchi-bot.git
cd panchi-bot

# O si ya está clonado
git pull origin master

# Crea la carpeta donde pondrás el backup .bak
mkdir -p backups
```

---

## Paso 6 — Arrancar primero solo SQL Server

```bash
# Levanta solo SQL Server
docker-compose up -d sqlserver
# Sigue los logs hasta que quede sano
docker compose logs -f sqlserver
```

SQL Server tarda en iniciar. Espera a que el healthcheck pase antes de seguir.

---

## Paso 7 — Restaurar el backup o crear la base

El contenedor monta automáticamente:

- `./backups` en `/var/opt/mssql/backup`
- `./migrations` en `/migrations`

### Opción A — Tienes un backup `.bak`

Sube tu backup al VPS dentro de `backups/`, por ejemplo:

```bash
scp mi_backup.bak usuario@tu-vps:/home/ubuntu/panchi-bot/backups/
```

Bloque recomendado de variables para no repetir valores a mano:

```bash
export DB_NAME=panchibot
export BACKUP_FILE=mi_backup.bak
export SA_PASSWORD='TuPassword!'
```

Comprueba que el backup existe dentro del contenedor:

```bash
docker compose exec sqlserver ls -lh /var/opt/mssql/backup
```

Valida que SQL Server puede leer el backup:

```bash
docker compose exec sqlserver /opt/mssql-tools18/bin/sqlcmd \
  -S localhost -U sa -P "$SA_PASSWORD" -C \
  -Q "RESTORE VERIFYONLY FROM DISK = N'/var/opt/mssql/backup/${BACKUP_FILE}'"
```

Consulta primero los nombres lógicos del backup:

```bash
docker-compose exec sqlserver /opt/mssql-tools18/bin/sqlcmd \
  -S localhost -U sa -P "$Jorgejorge1!" -C \
  -Q "RESTORE FILELISTONLY FROM DISK = N'/var/opt/mssql/backup/${BACKUP_FILE}'"
```

Luego restaura la BD. Sustituye `LogicalDataName` y `LogicalLogName` por los nombres
que te haya devuelto el comando anterior:


```bash
docker-compose exec sqlserver /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P 'Jorgejorge1!' -C -Q "RESTORE 
  DATABASE pruebabot FROM DISK = N'/var/opt/mssql/backup/panchibot.bak' WITH MOVE 'pruebabot' TO                  
  '/var/opt/mssql/data/pruebabot.mdf', MOVE 'pruebabot_log' TO '/var/opt/mssql/data/pruebabot_log.ldf', REPLACE"
  ```

```bash
export LOGICAL_DATA_NAME='LogicalDataName'
export LOGICAL_LOG_NAME='LogicalLogName'

docker compose exec sqlserver /opt/mssql-tools18/bin/sqlcmd \
  -S localhost -U sa -P "$SA_PASSWORD" -C \
  -Q "RESTORE DATABASE ${DB_NAME}
      FROM DISK = N'/var/opt/mssql/backup/${BACKUP_FILE}'
      WITH MOVE '${LOGICAL_DATA_NAME}' TO '/var/opt/mssql/data/${DB_NAME}.mdf',
           MOVE '${LOGICAL_LOG_NAME}' TO '/var/opt/mssql/data/${DB_NAME}_log.ldf',
           REPLACE, RECOVERY"
```

Comprueba que la base quedó restaurada y accesible:

```bash
docker compose exec sqlserver /opt/mssql-tools18/bin/sqlcmd \
  -S localhost -U sa -P "$SA_PASSWORD" -C \
  -Q "SELECT name, state_desc FROM sys.databases WHERE name = '${DB_NAME}'"
```

Prueba una consulta simple ya dentro de la base restaurada:

```bash
docker compose exec sqlserver /opt/mssql-tools18/bin/sqlcmd \
  -S localhost -U sa -P "$SA_PASSWORD" -d "$DB_NAME" -C \
  -Q "SELECT TOP 1 name FROM sys.tables ORDER BY name"
```

### Opción B — No tienes backup

SQL Server Express arranca vacío. Crea la BD manualmente:

```bash
docker compose exec sqlserver /opt/mssql-tools18/bin/sqlcmd \
  -S localhost -U sa -P "TuPassword!" -C \
  -Q "CREATE DATABASE panchibot"
```

> Recomendación: si tienes backup, restáuralo antes de arrancar la app.
> Así evitas una BD a medias o diferencias de esquema.

---

## Paso 8 — Arrancar el resto del stack

Cuando la base ya exista y esté restaurada, levanta el resto:

```bash
# Construye la imagen de la app y levanta todo lo demás
docker compose up --build -d redis app nginx

# Sigue los logs de la app
docker compose logs -f app
```

El orden de arranque será:
1. `redis` arranca y pasa el healthcheck (~5s)
2. `sqlserver` ya está levantado y sano
3. `app` arranca una vez Redis y SQL Server están sanos
4. `nginx` arranca

---

## Paso 9 — Ejecutar migraciones SQL adicionales (si aplican)

Si has restaurado un backup reciente, puede que no necesites esto.
Si arrancas con una base nueva o tu backup está desactualizado, aplica los SQL de
`migrations/` manualmente desde el contenedor de SQL Server:

```bash
# Ejemplo: ejecutar una migración concreta
docker compose exec sqlserver /opt/mssql-tools18/bin/sqlcmd \
  -S localhost -U sa -P "TuPassword!" -d panchibot -C \
  -i /migrations/002_turno_campos_dashboard.sql
```

---

## Paso 10 — Verificar que todo funciona

```bash
# Health check — debe devolver {"status":"ok","redis":"ok","database":"ok"}
curl https://tudominio.com/health

# Dashboard accesible
curl -I https://tudominio.com/dashboard/

# Logs de la app sin errores
docker compose logs app --tail=50
```

---

## Paso 11 — Configurar webhooks externos

### Meta / WhatsApp Cloud API

En [developers.facebook.com](https://developers.facebook.com):
1. Tu app → WhatsApp → Configuration → Webhook
2. **Callback URL**: `https://tudominio.com/webhook/meta`
3. **Verify Token**: el valor de `META_VERIFY_TOKEN` en tu `.env`
4. Suscríbete al campo: `messages`

Verificación manual:
```bash
curl "https://tudominio.com/webhook/meta?hub.mode=subscribe&hub.verify_token=TU_TOKEN&hub.challenge=test"
# Debe responder: test
```

### Twilio

En [console.twilio.com](https://console.twilio.com):
1. Messaging → Sandbox Settings (o tu número)
2. **Webhook URL**: `https://tudominio.com/webhook`
3. Método: POST

### Monei

En [dashboard.monei.com](https://dashboard.monei.com):
1. Settings → Webhooks → Add endpoint
2. **URL**: `https://tudominio.com/webhook/monei`
3. Eventos: `payment.succeeded`, `payment.failed`, `payment.canceled`

---

## Renovación automática de certificados

```bash
# Añade al crontab del VPS (renueva cada 60 días automáticamente)
sudo crontab -e

# Añade esta línea (ajusta la ruta al proyecto):
0 3 1 * * certbot renew --quiet && docker compose -f /home/ubuntu/panchi-bot/docker-compose.yml restart nginx
```

---

## Comandos del día a día

```bash
# Estado de los servicios
docker compose ps

# Logs en tiempo real
docker compose logs -f app

# Redesplegar tras cambios de código (sin reconstruir imagen)
git pull && docker compose restart app

# Reconstruir imagen tras cambios en requirements.txt o Dockerfile
git pull && docker compose up --build -d app

# Acceder a la shell de la app
docker compose exec app bash

# Acceder a SQL Server
docker compose exec sqlserver /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "TuPassword!" -No

# Reiniciar solo nginx (tras cambiar nginx.local.conf o nginx.prod.conf)
docker compose restart nginx

# Parar todo (Redis y SQL Server siguen con sus datos en volúmenes)
docker compose down

# ⚠️ Borrar TODO incluyendo datos de SQL Server y Redis
docker compose down -v
```

---

## Checklist final antes de dar por desplegado

- [ ] `curl https://tudominio.com/health` → `{"status":"ok","redis":"ok","database":"ok"}`
- [ ] Dashboard accesible en `https://tudominio.com/dashboard/`
- [ ] Webhook de WhatsApp verificado en el panel de Meta/Twilio
- [ ] Webhook de Monei configurado
- [ ] Enviar un WhatsApp de prueba y ver en los logs que llega
- [ ] Crear un usuario administrador en la BD
- [ ] `docker compose logs app` sin errores en rojo
