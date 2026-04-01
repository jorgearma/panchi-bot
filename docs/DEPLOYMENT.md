# 🚀 Guía de Despliegue en Servidor con Docker

Esta guía documenta los pasos correctos para desplegar **Panchi-Bot** en un servidor usando Docker Compose.

## 📋 Requisitos Previos

- Docker instalado
- Docker Compose v2.27+ (importante: NO v1.29)
- Git
- Acceso SSH al servidor
- Backup de la BD SQL Server (archivo `.bak`)

---

## 1️⃣ Instalación de Docker y Docker Compose

```bash
# Actualizar repositorios
sudo apt-get update
sudo apt-get install -y docker.io

# Desinstalar versión vieja de docker-compose (si existe)
sudo apt-get remove -y docker-compose

# Instalar Docker Compose v2.27
sudo curl -L "https://github.com/docker/compose/releases/download/v2.27.0/docker-compose-$(uname -s)-$(uname -m)" \
  -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Crear enlace simbólico
sudo ln -sf /usr/local/bin/docker-compose /usr/bin/docker-compose

# Verificar
docker-compose --version
```

---

## 2️⃣ Clonar el Repositorio

```bash
cd /ruta/donde/quieras/deploy
git clone <tu-repo-url> panchi-bot
cd panchi-bot
```

---

## 3️⃣ Configurar Variables de Entorno

```bash
cp .env.example .env
nano .env
```

**Variables críticas que DEBEN estar correctas:**

```bash
# Flask
SECRET_KEY=tu-clave-secreta-fuerte

# SQL Server (IMPORTANTE: usar nombres de servicio Docker)
SQL_SERVER=sqlserver,1433
SQL_DATABASE=pruebabot
SQL_UID=sa
SQL_PWD=tu_contraseña_fuerte

# Redis (IMPORTANTE: usar nombre del servicio)
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0
REDIS_URL=redis://redis:6379/0

# WhatsApp
WHATSAPP_PROVIDER=twilio  # o 'meta'
TWILIO_ACCOUNT_SID=ACxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxx
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886

# Monei
MONEI_API_KEY=sk_live_xxxxxxxx
MONEI_WEBHOOK_SECRET=xxxxxxxx

# Google Maps
GOOGLE_MAPS_API_KEY=xxxxxxxx

# URL Pública (usa la IP del servidor si no tienes dominio)
PUBLIC_URL=http://161.97.186.255

# Nginx
NGINX_CONF=nginx.conf

# Sentry (opcional)
SENTRY_DSN=

# CORS
ALLOWED_ORIGIN=http://161.97.186.255

# Token interno
INTERNAL_API_TOKEN=tu-token-aqui

# Almacén
STORE_PHONE=612345678
STORE_ADDRESS=C/ Ejemplo 12, Madrid
```

**⚠️ ERRORES COMUNES:**
- ❌ `SQL_SERVER=localhost` → ✅ `SQL_SERVER=sqlserver`
- ❌ `REDIS_HOST=localhost` → ✅ `REDIS_HOST=redis`
- ❌ `REDIS_URL=redis://localhost` → ✅ `REDIS_URL=redis://redis`

---

## 4️⃣ Preparar Archivo de Configuración de Nginx

Si tienes dominio con SSL, edita `nginx.prod.conf`:

```bash
sed -i 's/tudominio.com/tu-dominio-real.com/g' nginx.prod.conf
```

Luego en `.env`:
```bash
NGINX_CONF=nginx.prod.conf
```

Si usas IP (sin SSL), mantén:
```bash
NGINX_CONF=nginx.conf
```

---

## 5️⃣ Levantar SQL Server y Restaurar Backup

```bash
# Levanta solo SQL Server
docker-compose up -d sqlserver

# Espera a que esté listo (15-30 segundos)
docker-compose logs -f sqlserver
# Cuando veas "Recovery is complete", está listo. Presiona Ctrl+C

# Elimina BD antigua si existe
docker-compose exec sqlserver /opt/mssql-tools18/bin/sqlcmd \
  -S localhost -U sa -P "$(grep SQL_PWD .env | cut -d= -f2)" \
  -C \
  -Q "DROP DATABASE panchibot"  # si existe de un deploy anterior

# Restaura el backup
docker-compose exec sqlserver /opt/mssql-tools18/bin/sqlcmd \
  -S localhost -U sa -P "$(grep SQL_PWD .env | cut -d= -f2)" \
  -C \
  -Q "RESTORE DATABASE pruebabot FROM DISK = '/var/opt/mssql/backup/panchi.bak'"

# Verifica que se restauró
docker-compose exec sqlserver /opt/mssql-tools18/bin/sqlcmd \
  -S localhost -U sa -P "$(grep SQL_PWD .env | cut -d= -f2)" \
  -C \
  -Q "SELECT name FROM sys.databases WHERE name='pruebabot'"
```

---

## 6️⃣ Copiar Backup a la Carpeta Correcta

Si el backup está en otra ruta:

```bash
# Copiar backup a la carpeta montada
cp /ruta/del/backup/panchi.bak ./backups/

# Verificar
ls -lah ./backups/
```

---

## 7️⃣ Levantar Todos los Servicios

```bash
# Reconstruye la imagen (importante en primer despliegue)
docker-compose up -d --build

# Verifica que todos están corriendo
docker-compose ps

# Debería ver:
# - panchi-bot-app-1 (Up)
# - panchi-bot-redis-1 (Up, healthy)
# - panchi-bot-sqlserver-1 (Up, healthy)
# - panchi-bot-nginx-1 (Up)
```

---

## 8️⃣ Verificar que Funciona

```bash
# Health check
curl http://161.97.186.255/health

# Respuesta esperada:
# {"status": "ok", "redis": "ok", "database": "ok"}
```

Si ves `"status": "degraded"`, revisa los logs:

```bash
docker-compose logs app
```

---

## 📝 Comandos Útiles para Administración

### Ver logs
```bash
# Todos los logs
docker-compose logs -f

# Solo app
docker-compose logs -f app

# Solo SQL Server
docker-compose logs -f sqlserver
```

### Reiniciar servicios
```bash
# Reiniciar solo la app (si cambias .env)
docker-compose restart app

# Reiniciar todo
docker-compose restart
```

### Reconstruir (si cambias código o requirements.txt)
```bash
docker-compose up -d --build
```

### Parar todo
```bash
docker-compose down
```

### Ver estado
```bash
docker-compose ps
```

---

## 🔄 Cambios Después del Despliegue

| Cambio | Comando |
|--------|---------|
| `.env` (variables) | `docker-compose restart app` |
| `requirements.txt` | `docker-compose up -d --build` |
| Código Python | `docker-compose up -d --build` |
| `docker-compose.yml` | `docker-compose up -d` |
| Nginx config | `docker-compose restart nginx` |

---

## 🆘 Troubleshooting

### Error: "502 Bad Gateway"
```bash
docker-compose logs app
# Busca "App failed to load" y el error real
```

### Error: "Cannot open database pruebabot"
```bash
# Verifica que la BD existe
docker-compose exec sqlserver /opt/mssql-tools18/bin/sqlcmd \
  -S localhost -U sa -P "tu_contraseña" \
  -C \
  -Q "SELECT name FROM sys.databases"
```

### Error: "Error al conectar a Redis"
```bash
# Verifica REDIS_HOST en .env (debe ser "redis", no "localhost")
grep REDIS_HOST .env
docker-compose restart app
```

### Error: "Failed to find attribute 'app' in 'main'"
```bash
# Reconstruye la imagen
docker-compose up -d --build
```

### Docker Compose v1.29 instalado
```bash
# Desinstala y reinstala v2
sudo apt-get remove -y docker-compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.27.0/docker-compose-$(uname -s)-$(uname -m)" \
  -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
docker-compose --version
```

---

## 🔐 Seguridad

- [ ] `SECRET_KEY` es único y fuerte (no el del `.env.example`)
- [ ] `SQL_PWD` es fuerte (mínimo 8 caracteres, mayús, número, símbolo)
- [ ] Firewall permite solo puertos 80 y 443 desde internet
- [ ] Puerto 5000 (app) solo accesible desde Nginx (interno)
- [ ] Puerto 1433 (SQL Server) solo accesible internamente
- [ ] HTTPS habilitado si tienes dominio y certificados SSL

---

## 📊 Monitoreo

Para ver métricas en tiempo real:

```bash
# CPU y memoria de los contenedores
docker stats

# Logs de eventos
docker events --filter type=container
```

---

## 🎯 Checklist Despliegue

- [ ] Docker Compose v2.27+ instalado
- [ ] Repo clonado
- [ ] `.env` configurado correctamente
- [ ] Backup (`panchi.bak`) en `./backups/`
- [ ] SQL Server levantado
- [ ] BD restaurada y verificada
- [ ] Todos los servicios levantados (`docker-compose up -d --build`)
- [ ] Health check OK (`curl http://IP/health`)
- [ ] Logs sin errores (`docker-compose logs app`)
- [ ] Firewall configurado (puertos 80, 443 abiertos)

---

**Versión:** 1.0  
**Fecha:** 2026-04-01  
**Autor:** Deployment Guide
