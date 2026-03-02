FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# No fijes el ENV PORT aquí, deja que Railway lo inyecte
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium

COPY . .

# Cambiamos a formato de cadena simple para asegurar que el Shell expanda la variable
CMD python -c "import main; print('Importación exitosa')" && uvicorn main:app --host 0.0.0.0 --port $PORT