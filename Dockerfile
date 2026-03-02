FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright ya viene instalado en la imagen base, pero por si acaso:
RUN playwright install chromium

COPY . .

# ✅ Usar sh -c para que $PORT se expanda en runtime
CMD sh -c "uvicorn main:app --host 0.0.0.0 --port $PORT"