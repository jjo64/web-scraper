"""
Universal Scraper
-----------------
Estrategia automática:
  1. Detecta si la URL es una API JSON conocida (ej: reddit .json)
  2. Intenta obtener __NEXT_DATA__ / __NUXT_DATA__ (Next.js / Nuxt)
  3. Parsea HTML estático con BeautifulSoup
  4. Si todo falla, devuelve lo que pueda extraer
  5. Modo JS opcional usando Playwright
  6. Modo extracción a medida con reglas CSS
"""

import re
import json
from urllib.parse import urljoin, urlparse

import jmespath
from curl_cffi.requests import AsyncSession
from curl_cffi.requests.errors import RequestsError
from bs4 import BeautifulSoup

from playwright.async_api import async_playwright
from readability import Document
from markdownify import markdownify as md


# ─────────────────────────────────────────────────────────────────────────────
# HEADERS base — imita Chrome real
# ─────────────────────────────────────────────────────────────────────────────

BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
}


# ─────────────────────────────────────────────────────────────────────────────
# DETECTORES
# ─────────────────────────────────────────────────────────────────────────────

def detectar_api_json(url: str) -> str | None:
    parsed = urlparse(url)
    if "reddit.com" in parsed.netloc:
        if not url.endswith(".json"):
            clean = url.split("?")[0].rstrip("/")
            return clean + ".json"
    if "news.ycombinator.com" in parsed.netloc:
        item_id = re.search(r"id=(\d+)", url)
        if item_id:
            return f"https://hacker-news.firebaseio.com/v0/item/{item_id.group(1)}.json"
    return None

def extraer_next_data(html: str) -> dict | None:
    match = re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', html, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
    return None

def extraer_nuxt_data(html: str) -> dict | None:
    match = re.search(r'window\.__NUXT__\s*=\s*(\{.*?\});', html, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
    return None

def extraer_json_ld(soup: BeautifulSoup) -> list[dict]:
    results = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
            if isinstance(data, list):
                results.extend(data)
            else:
                results.append(data)
        except (json.JSONDecodeError, TypeError):
            continue
    return results


# ─────────────────────────────────────────────────────────────────────────────
# EXTRACTORES HTML
# ─────────────────────────────────────────────────────────────────────────────

def extraer_titulos(soup: BeautifulSoup) -> list[str]:
    titulos = []
    for tag in soup.find_all(["h1", "h2", "h3"]):
        texto = tag.get_text(strip=True)
        if texto and len(texto) > 2:
            titulos.append(texto)
    return titulos[:20]

def extraer_imagenes(soup: BeautifulSoup, base_url: str) -> list[dict]:
    imagenes = []
    seen = set()
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
        if not src:
            continue
        src = urljoin(base_url, src)
        width = img.get("width", "")
        height = img.get("height", "")
        try:
            if int(width) < 50 or int(height) < 50:
                continue
        except (ValueError, TypeError):
            pass
        if src not in seen and src.startswith("http"):
            seen.add(src)
            imagenes.append({"src": src, "alt": img.get("alt", "").strip(), "width": width, "height": height})
    return imagenes[:20]

def extraer_links(soup: BeautifulSoup, base_url: str) -> list[dict]:
    links = []
    seen = set()
    base_domain = urlparse(base_url).netloc
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        href_abs = urljoin(base_url, href)
        if href_abs in seen:
            continue
        seen.add(href_abs)
        links.append({"texto": a.get_text(strip=True)[:80], "url": href_abs, "externo": urlparse(href_abs).netloc != base_domain})
    return links[:50]

def extraer_tablas(soup: BeautifulSoup) -> list[list[dict]]:
    tablas = []
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        filas = []
        for tr in table.find_all("tr"):
            celdas = [td.get_text(strip=True) for td in tr.find_all("td")]
            if not celdas:
                continue
            if headers:
                fila = dict(zip(headers, celdas))
            else:
                fila = {f"col_{i}": v for i, v in enumerate(celdas)}
            filas.append(fila)
        if filas:
            tablas.append(filas)
    return tablas[:5]

def extraer_meta(soup: BeautifulSoup) -> dict:
    meta = {}
    title_tag = soup.find("title")
    if title_tag:
        meta["title"] = title_tag.get_text(strip=True)
    for tag in soup.find_all("meta"):
        name = tag.get("name") or tag.get("property") or ""
        content = tag.get("content", "")
        if name and content:
            meta[name.lower()] = content
    return meta

def procesar_articulo(html: str) -> dict:
    """Extrae el contenido principal usando readability y lo convierte a markdown."""
    try:
        doc = Document(html)
        title = doc.title()
        summary = doc.summary()
        markdown = md(summary, strip=['a', 'img'])
        return {
            "title_readability": title,
            "markdown_content": markdown.strip()
        }
    except Exception:
        return {"title_readability": None, "markdown_content": None}

def aplicar_reglas_css(soup: BeautifulSoup, reglas: dict) -> dict:
    """Aplica selectores CSS provistos por el usuario."""
    resultado = {}
    for clave, selector in reglas.items():
        elementos = soup.select(selector)
        if elementos:
            if len(elementos) == 1:
                resultado[clave] = elementos[0].get_text(strip=True)
            else:
                resultado[clave] = [el.get_text(strip=True) for el in elementos]
        else:
            resultado[clave] = None
    return resultado

# ─────────────────────────────────────────────────────────────────────────────
# SCRAPER PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

class UniversalScraper:

    def __init__(self):
        self.session = AsyncSession(impersonate="chrome124", headers=BASE_HEADERS)

    async def close(self):
        self.session.close()

    async def _get_html_playwright(self, url: str) -> str:
        """Obtiene el HTML rendereado usando Playwright."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=BASE_HEADERS["User-Agent"]
            )
            page = await context.new_page()
            # Esperar hasta que network idle
            await page.goto(url, wait_until="networkidle", timeout=20000)
            html = await page.content()
            await browser.close()
            return html

    async def scrape(self, url: str, modo: str = "auto", extract_rules: dict | None = None) -> dict:
        """
        Punto de entrada asíncrono. Devuelve un dict con todos los datos.
        """
        if not url.startswith("http"):
            url = "https://" + url

        resultado = {
            "url": url,
            "metodo_usado": "",
            "titulo": None,
            "descripcion": None,
            "titulos": [],
            "articulo_principal_md": None,
            "imagenes": [],
            "links": [],
            "tablas": [],
            "datos_estructurados": {},
            "datos_custom": {},
            "meta": {},
            "error": None
        }

        html = ""

        # ── Estrategia 1: API JSON conocida ──────────────────────────────────
        if modo in ("auto", "api"):
            api_url = detectar_api_json(url)
            if api_url:
                try:
                    r = await self.session.get(api_url, timeout=15, headers={"Accept": "application/json"})
                    if r.status_code == 200:
                        data = r.json()
                        resultado["metodo_usado"] = "api_json"
                        resultado["datos_estructurados"] = data
                        resultado["titulo"] = (
                            jmespath.search("data.children[0].data.subreddit_name_prefixed", data)
                            or jmespath.search("title", data)
                            or jmespath.search("name", data)
                        )
                        return resultado
                except Exception:
                    pass  # fallback a HTML/JS

        # ── Estrategia 2: JS con Playwright ──────────────────────────────────
        if modo == "js":
            try:
                html = await self._get_html_playwright(url)
                resultado["metodo_usado"] = "html_playwright"
            except Exception as e:
                resultado["error"] = f"Error en Playwright: {str(e)}"
                return resultado

        # ── Estrategia 3: Petición Curl CFFI (HTML) ──────────────────────────
        elif modo in ("auto", "html"):
            try:
                r = await self.session.get(url, timeout=15, allow_redirects=True)
                if r.status_code != 200:
                    resultado["error"] = f"Código de estado inválido HTTP {r.status_code}"
                    return resultado
                html = r.text
                resultado["metodo_usado"] = "html_cffi"
            except Exception as e:
                resultado["error"] = f"Error al obtener HTML: {str(e)}"
                return resultado

        if not html:
            resultado["error"] = "HTML vacío obtenido."
            return resultado

        soup = BeautifulSoup(html, "html.parser")

        # Extraer custom rules si el usuario las pide (CSS Selectors)
        if extract_rules:
            resultado["datos_custom"] = aplicar_reglas_css(soup, extract_rules)

        # ── Autodetección Next/Nuxt ──────────────────────────────────────────
        next_data = extraer_next_data(html)
        if next_data:
            resultado["datos_estructurados"]["nextjs"] = next_data

        nuxt_data = extraer_nuxt_data(html)
        if nuxt_data:
            resultado["datos_estructurados"]["nuxtjs"] = nuxt_data

        # ── Parseo Clásico ───────────────────────────────────────────────────
        meta = extraer_meta(soup)
        resultado["meta"] = meta
        resultado["titulo"] = (
            meta.get("og:title") or meta.get("twitter:title") or meta.get("title")
        )
        resultado["descripcion"] = (
            meta.get("og:description") or meta.get("description") or meta.get("twitter:description")
        )
        resultado["titulos"] = extraer_titulos(soup)
        resultado["imagenes"] = extraer_imagenes(soup, url)
        resultado["links"] = extraer_links(soup, url)
        resultado["tablas"] = extraer_tablas(soup)

        json_ld = extraer_json_ld(soup)
        if json_ld:
            resultado["datos_estructurados"]["json_ld"] = json_ld

        # ── Readability -> Markdown para el contenido principal ──────────────
        datos_lectura = procesar_articulo(html)
        resultado["articulo_principal_md"] = datos_lectura.get("markdown_content")
        
        if not resultado["titulo"] and datos_lectura.get("title_readability"):
            resultado["titulo"] = datos_lectura.get("title_readability")

        return resultado