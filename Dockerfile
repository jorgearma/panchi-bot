FROM python:3.11-slim

# Instala ODBC Driver 18 for SQL Server
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    unixodbc-dev \
    && curl https://packages.microsoft.com/keys/microsoft.asc -o /usr/share/keyrings/microsoft-prod.asc \
    && echo "deb [signed-by=/usr/share/keyrings/microsoft-prod.asc] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y msodbcsql18 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Descarga modelo de spaCy (después de instalar pip)
RUN python -m spacy download es_core_news_sm

COPY . .

EXPOSE 5000

CMD ["gunicorn", "--config", "gunicorn.conf.py", "main:app"]
