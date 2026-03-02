from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import uvicorn
import os
from dotenv import load_dotenv

from scraper import UniversalScraper

# Cargar variables de entorno para desarrollo local
load_dotenv()

# ── Configurar SlowAPI para Rate Limiting ──
# Esto limita las peticiones basadas en la IP del usuario.
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Universal Web Scraper API", 
    version="1.1.0",
    description="API avanzada para extraer datos de páginas web, con soporte para JS rendering y extracción custom."
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Configuración de CORS dinámica
allowed_origins = os.getenv("ALLOWED_ORIGINS", "https://josuecueva.vercel.app").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ScrapeRequest(BaseModel):
    url: str
    modo: str = "auto"  # auto | api | html | js
    extract_rules: dict[str, str] | None = None
    output_format: str = "json" # json | markdown

class ScrapeResponse(BaseModel):
    url: str
    metodo_usado: str
    titulo: str | None
    descripcion: str | None
    titulos: list[str]
    articulo_principal_md: str | None
    imagenes: list[dict]
    links: list[dict]
    tablas: list[list[dict]]
    datos_estructurados: dict
    datos_custom: dict
    meta: dict
    error: str | None

@app.get("/")
def root():
    return {"status": "ok", "message": "Universal Scraper API - Operativa"}

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.post("/scrape")
@limiter.limit("10/minute")  # Máximo 10 peticiones por minuto por IP para evitar abusos
async def scrape(request: Request, body: ScrapeRequest):
    """
    Endpoint principal. Devuelve los datos extraídos en JSON puro, o un archivo descargable.
    """
    scraper = UniversalScraper()
    try:
        # El scraping ahora es 100% asíncrono
        result = await scraper.scrape(url=body.url, modo=body.modo, extract_rules=body.extract_rules)
        
        # ── Sistema de descargas integrado ──
        # Si el usuario pide output_format="markdown", devolvemos el archivo en lugar del JSON
        if body.output_format.lower() == "markdown":
            md_content = result.get("articulo_principal_md")
            if not md_content:
                md_content = "# No se encontró contenido de artículo en la página."
            
            return PlainTextResponse(
                content=md_content,
                media_type="text/markdown",
                headers={"Content-Disposition": 'attachment; filename="articulo_extraido.md"'}
            )
            
        # Si no, devuelve el JSON completo que validará el schema implícitamente
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al scrapear: {str(e)}")
    finally:
        # Muy importante cerrar la sesión asíncrona para liberar recursos
        await scraper.close()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
else:
    # Esto es por si Railway intenta importar 'app' directamente sin pasar por __main__
    port = int(os.environ.get("PORT", 8000))
