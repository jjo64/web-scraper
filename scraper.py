import re
import json
import jmespath
from urllib.parse import urljoin, urlparse
from curl_cffi.requests import AsyncSession
from bs4 import BeautifulSoup

# Optional dependencies for Python 3.14 compatibility
try:
    from playwright.async_api import async_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

try:
    from readability import Document
    HAS_READABILITY = True
except ImportError:
    HAS_READABILITY = False

try:
    from markdownify import markdownify as md
    HAS_MARKDOWNIFY = True
except ImportError:
    HAS_MARKDOWNIFY = False

# Detect if lxml is available
try:
    import lxml
    BS4_PARSER = "lxml"
except ImportError:
    BS4_PARSER = "html.parser"

BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "DNT": "1",
}

class UniversalScraper:
    def __init__(self):
        # Impersonate imita el fingerprint TLS de un navegador real
        self.session = AsyncSession(impersonate="chrome124", headers=BASE_HEADERS)

    async def close(self):
        await self.session.close()

    async def _get_html_playwright(self, url: str) -> str:
        """Renderiza JS solo cuando es estrictamente necesario."""
        if not HAS_PLAYWRIGHT:
            raise Exception("Playwright no está disponible en este entorno (Python 3.14).")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=BASE_HEADERS["User-Agent"])
            page = await context.new_page()
            
            # Bloqueamos multimedia para ahorrar ancho de banda y tiempo
            await page.route("**/*.{png,jpg,jpeg,svg,css,woff2,ttf}", lambda route: route.abort())
            
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            html = await page.content()
            await browser.close()
            return html

    def _detectar_api_json(self, url: str) -> str | None:
        parsed = urlparse(url)
        if "reddit.com" in parsed.netloc:
            return url.split("?")[0].rstrip("/") + ".json"
        if "news.ycombinator.com" in parsed.netloc:
            item_id = re.search(r"id=(\d+)", url)
            if item_id:
                return f"https://hacker-news.firebaseio.com/v0/item/{item_id.group(1)}.json"
        return None

    def _extraer_datos_estructurados(self, html: str, soup: BeautifulSoup) -> dict:
        datos = {}
        # Next.js & Nuxt 3
        next_data = soup.find("script", id="__NEXT_DATA__")
        if next_data:
            try: datos["nextjs"] = json.loads(next_data.string)
            except: pass
        
        nuxt_v3 = soup.find("script", id="__NUXT_DATA__")
        if nuxt_v3:
            try: datos["nuxt_v3"] = json.loads(nuxt_v3.string)
            except: pass

        # JSON-LD (SEO & Rich Snippets)
        json_ld_tags = soup.find_all("script", type="application/ld+json")
        if json_ld_tags:
            datos["json_ld"] = []
            for tag in json_ld_tags:
                try: datos["json_ld"].append(json.loads(tag.string))
                except: continue
        return datos

    def _extraer_tablas(self, soup: BeautifulSoup) -> list:
        tablas_data = []
        for table in soup.find_all("table")[:5]:
            filas = []
            headers = [th.get_text(strip=True) for th in table.find_all("th")]
            for tr in table.find_all("tr"):
                celdas = [td.get_text(strip=True) for td in tr.find_all("td")]
                if celdas:
                    if headers and len(headers) == len(celdas):
                        filas.append(dict(zip(headers, celdas)))
                    else:
                        filas.append({f"col_{i}": val for i, val in enumerate(celdas)})
            if filas: tablas_data.append(filas)
        return tablas_data

    async def scrape(self, url: str, modo: str = "auto") -> dict:
        if not url.startswith("http"): url = "https://" + url
        
        resultado = {
            "url": url, "metodo_usado": "html_cffi", "titulo": None, 
            "descripcion": None, "titulos": [], "articulo_principal_md": None, 
            "imagenes": [], "links": [], "tablas": [], 
            "datos_estructurados": {}, "error": None, "meta": {}
        }

        try:
            # Estrategia 1: API Directa
            api_url = self._detectar_api_json(url)
            if modo in ["auto", "api"] and api_url:
                r = await self.session.get(api_url)
                if r.status_code == 200:
                    resultado["datos_estructurados"]["api_directa"] = r.json()
                    resultado["metodo_usado"] = "api_rest"
                    return resultado

            # Estrategia 2: Obtener HTML (JS o Estático)
            if modo == "js":
                html = await self._get_html_playwright(url)
                resultado["metodo_usado"] = "playwright_js"
            else:
                r = await self.session.get(url, timeout=15)
                html = r.text

            # Estrategia 3: Parseo
            soup = BeautifulSoup(html, BS4_PARSER)
            
            # Metadata básica
            for tag in soup.find_all("meta"):
                n = tag.get("name") or tag.get("property")
                if n and tag.get("content"): 
                    resultado["meta"][n.lower()] = tag.get("content")

            resultado["titulo"] = resultado["meta"].get("og:title") or (soup.title.string if soup.title else None)
            resultado["descripcion"] = resultado["meta"].get("description") or resultado["meta"].get("og:description")
            
            # Listas: Imágenes, Links, Títulos
            resultado["titulos"] = [h.get_text(strip=True) for h in soup.find_all(["h1", "h2"])[:15]]
            resultado["links"] = [{"texto": a.get_text(strip=True)[:50], "url": urljoin(url, a['href'])} 
                                 for a in soup.find_all("a", href=True) if len(a.get_text()) > 2][:30]
            
            resultado["imagenes"] = []
            for img in soup.find_all("img")[:15]:
                src = img.get("src") or img.get("data-src")
                if src: resultado["imagenes"].append({"src": urljoin(url, src), "alt": img.get("alt", "")})

            # Datos complejos
            resultado["tablas"] = self._extraer_tablas(soup)
            resultado["datos_estructurados"].update(self._extraer_datos_estructurados(html, soup))
            
            # Readability (Contenido principal)
            if HAS_READABILITY and HAS_MARKDOWNIFY:
                doc = Document(html)
                resultado["articulo_principal_md"] = md(doc.summary(), strip=['a', 'img']).strip()
            else:
                resultado["articulo_principal_md"] = "Contenido no disponible (Falta readability/markdownify)"

            return resultado

        except Exception as e:
            resultado["error"] = str(e)
            return resultado