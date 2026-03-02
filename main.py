import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from scraper import UniversalScraper

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="JosueScraper API")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # En producción usa tu dominio de Vercel
    allow_methods=["*"],
    allow_headers=["*"],
)

class ScrapeRequest(BaseModel):
    url: str
    modo: str = "auto"

@app.post("/scrape")
@limiter.limit("10/minute")
async def handle_scrape(request: Request, body: ScrapeRequest):
    scraper = UniversalScraper()
    try:
        data = await scraper.scrape(body.url, modo=body.modo)
        if data.get("error"):
            raise HTTPException(status_code=422, detail=data["error"])
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await scraper.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))