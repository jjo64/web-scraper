# Usamos la imagen oficial de Playwright (Ubuntu Jammy + Python)
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

# Evitar que Python genere archivos .pyc y forzar logs en tiempo real
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Usamos el PORT que configuraste en Railway, por defecto 8080
ENV PORT=8080

WORKDIR /app

# Instalar dependencias del proyecto
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instalar el navegador Chromium (las librerías de sistema ya están presentes)
RUN playwright install chromium

# Copiar el resto del código
COPY . .

# Exponer el puerto que Railway asignará dinámicamente
EXPOSE ${PORT}

# Comando para arrancar la app
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]