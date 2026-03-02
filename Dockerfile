FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencias base del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2-dev libxslt1-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# playwright install-deps instala automáticamente las libs correctas para Chromium
RUN playwright install-deps chromium
RUN playwright install chromium

COPY . .

CMD sh -c "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"