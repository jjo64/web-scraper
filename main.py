import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from scraper import UniversalScraper

# Configuración del limitador de peticiones (Rate Limiting)
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(
    title="JosueScraper API",
    description="API de extracción universal con soporte para JS, APIs y Datos Estructurados",
    version="1.0.0"
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- CONFIGURACIÓN DE CORS ---
# Lee la variable que pusiste en Railway. Si no existe, permite todo por defecto en local.
allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Modelo de datos para la petición
class ScrapeRequest(BaseModel):
    url: str
    modo: str = "auto"

# --- ENDPOINTS ---

@app.get("/")
async def root():
    """Endpoint de bienvenida para verificar que la API está viva."""
    return {
        "message": "JosueScraper API está funcionando",
        "status": "online",
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    """Endpoint para el Health Check de Railway."""
    return {"status": "healthy"}

@app.post("/scrape")
@limiter.limit("10/minute")
async def handle_scrape(request: Request, body: ScrapeRequest):
    """
    Endpoint principal de scraping.
    Recibe una URL y un modo (auto, html, js, api).
    """
    scraper = UniversalScraper()
    try:
        # Ejecutamos el scraping
        data = await scraper.scrape(body.url, modo=body.modo)
        
        # Si el scraper devuelve un error interno
        if data.get("error"):
            raise HTTPException(status_code=422, detail=data["error"])
            
        return data
        
    except Exception as e:
        # Error genérico del servidor
        raise HTTPException(status_code=500, detail=str(e))
        
    finally:
        # IMPORTANTE: Cerramos la sesión de scraping para evitar fugas de memoria
        await scraper.close()

# NOTA: No incluimos uvicorn.run() aquí. 
# El Dockerfile se encarga de lanzar el servidor usando la variable $PORT.