# config.py

import os

# OpenAI
OPENAI_API_KEY: str | None = os.environ.get("OPENAI_API_KEY")

# Flask
SECRET_KEY: str | None = os.environ.get("SECRET_KEY")

# Twilio
TWILIO_ACCOUNT_SID: str | None = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN: str | None = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER: str | None = os.environ.get("TWILIO_WHATSAPP_NUMBER")

# Monei
MONEI_API_KEY: str | None = os.environ.get("MONEI_API_KEY")
MONEI_WEBHOOK_SECRET: str | None = os.environ.get("MONEI_WEBHOOK_SECRET")

# Google Maps
GOOGLE_MAPS_API_KEY: str | None = os.environ.get("GOOGLE_MAPS_API_KEY")

# Public URL (ngrok or production)
PUBLIC_URL: str | None = os.environ.get("PUBLIC_URL")

# SQL Server
SQL_SERVER: str = os.environ.get("SQL_SERVER", "localhost,1433")
SQL_DATABASE: str = os.environ.get("SQL_DATABASE", "pruebabot")
SQL_UID: str = os.environ.get("SQL_UID", "sa")
SQL_PWD: str = os.environ.get("SQL_PWD", "")

# Redis
REDIS_HOST: str = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT: int = int(os.environ.get("REDIS_PORT", 6379))
REDIS_DB: int = int(os.environ.get("REDIS_DB", 0))
