import os
import logging

# ── Logging primero que todo ──
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

logger.info("=== INICIANDO APLICACIÓN ===")
logger.info(f"Python path: {os.sys.path}")
logger.info(f"PORT env: {os.getenv('PORT', 'NO DEFINIDO')}")
logger.info(f"ALLOWED_ORIGINS env: {os.getenv('ALLOWED_ORIGINS', 'NO DEFINIDO')}")

try:
    from fastapi import FastAPI, Request, HTTPException
    logger.info("✓ FastAPI importado")
except Exception as e:
    logger.error(f"✗ Error importando FastAPI: {e}")
    raise

try:
    from fastapi.middleware.cors import CORSMiddleware
    logger.info("✓ CORSMiddleware importado")
except Exception as e:
    logger.error(f"✗ Error importando CORSMiddleware: {e}")
    raise

try:
    from pydantic import BaseModel
    logger.info("✓ Pydantic importado")
except Exception as e:
    logger.error(f"✗ Error importando Pydantic: {e}")
    raise

try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    logger.info("✓ SlowAPI importado")
except Exception as e:
    logger.error(f"✗ Error importando SlowAPI: {e}")
    raise

try:
    from scraper import UniversalScraper
    logger.info("✓ UniversalScraper importado")
except Exception as e:
    logger.error(f"✗ Error importando scraper: {e}")
    raise

logger.info("=== TODOS LOS IMPORTS OK, CREANDO APP ===")

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(
    title="JosueScraper API",
    description="API de extracción universal",
    version="1.0.0"
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
logger.info(f"CORS origins configurados: {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://josuecueva.vercel.app"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

class ScrapeRequest(BaseModel):
    url: str
    modo: str = "auto"

@app.on_event("startup")
async def startup_event():
    logger.info("=== APP STARTUP COMPLETO ===")
    logger.info(f"Escuchando en puerto: {os.getenv('PORT', '8000')}")

@app.get("/")
async def root():
    logger.info("GET / llamado")
    return {"message": "JosueScraper API está funcionando", "status": "online"}

@app.get("/health")
async def health_check():
    logger.info("GET /health llamado")
    return {"status": "healthy"}

@app.post("/scrape")
@limiter.limit("10/minute")
async def handle_scrape(request: Request, body: ScrapeRequest):
    logger.info(f"POST /scrape - URL: {body.url} - Modo: {body.modo}")
    scraper = UniversalScraper()
    try:
        data = await scraper.scrape(body.url, modo=body.modo)
        if data.get("error"):
            logger.warning(f"Scraper error interno: {data['error']}")
            raise HTTPException(status_code=422, detail=data["error"])
        logger.info("Scrape completado OK")
        return data
    except Exception as e:
        logger.error(f"Excepción en /scrape: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await scraper.close()