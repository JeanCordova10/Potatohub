import httpx
import re
import time
from bs4 import BeautifulSoup
from etl.config import HEADERS, RATE_LIMIT_SECONDS, MAX_PAGES, MAX_PAGES_RECETASGRATIS
import urllib.parse


def fetch_page(url: str) -> BeautifulSoup | None:
    try:
        response = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
        if response.status_code == 200:
            return BeautifulSoup(response.text, "html.parser")
        else:
            print(f"  [!] Status {response.status_code} en {url}")
            return None
    except Exception as e:
        print(f"  [!] Error al acceder {url}: {e}")
        return None


def scrape_cookpad(term: str) -> list[dict]:
    resultados = []

    for page in range(1, MAX_PAGES + 1):
        url = f"https://cookpad.com/pe/buscar/{term}?page={page}"
        print(f"  Cookpad [{term}] pág {page}: {url}")

        soup = fetch_page(url)
        if not soup:
            break

        # Links reales de recetas: /pe/recetas/{número}
        # Excluye /pe/recetas/nuevo y otros que no son recetas
        todos_links = soup.select('a[href*="/recetas/"]')
        recipe_links = [
            l for l in todos_links
            if re.search(r'/recetas/\d+', l.get("href", ""))
        ]

        if not recipe_links:
            print(f"  [!] Sin recetas en página {page}, terminando término '{term}'")
            break

        for link in recipe_links:
            href  = link.get("href", "")
            title = link.get_text(strip=True)

            if not title or not href:
                continue

            resultados.append({
                "title":       title,
                "source_url":  f"https://cookpad.com{href}",
                "source":      "cookpad_pe",
                "search_term": term,
                "lang":        "es",
                "country":     "PE",
            })

        print(f"  -> {len(recipe_links)} recetas encontradas")
        time.sleep(RATE_LIMIT_SECONDS)

    return resultados



def scrape_recetasgratis(term: str) -> list[dict]:
    resultados = []
    term_encoded = urllib.parse.quote(term)   # ← encode espacios a %20

    for page in range(1, MAX_PAGES_RECETASGRATIS + 1):
        if page == 1:
            url = f"https://recetas.elperiodico.com/busqueda?q={term_encoded}"
        else:
            url = f"https://recetas.elperiodico.com/busqueda?q={term_encoded}&page={page}"

        print(f"  RecetasGratis [{term}] pág {page}: {url}")

        soup = fetch_page(url)
        if not soup:
            break

        # Sin barra al final — así lo encontró el debug (82 links)
        recipe_links = soup.select('a[href*="/receta"]')

        if not recipe_links:
            print(f"  [!] Sin recetas en página {page}, terminando término '{term}'")
            break

        nuevas = 0
        for link in recipe_links:
            href  = link.get("href", "")
            title = link.get_text(strip=True)

            if not title or len(title) < 5:
                continue

            url_receta = (
                f"https://recetas.elperiodico.com{href}"
                if href.startswith("/") else href
            )

            resultados.append({
                "title":       title,
                "source_url":  url_receta,
                "source":      "recetasgratis",
                "search_term": term,
                "lang":        "es",
                "country":     "ES",
            })
            nuevas += 1

        print(f"  -> {nuevas} recetas encontradas")
        time.sleep(RATE_LIMIT_SECONDS)

    return resultados

def scrape_ceciliatupac() -> list[dict]:
    """Página de listado de recetas con papas — sin paginación."""
    url = "https://www.ceciliatupac.com/recetas-con-papas"
    print(f"  CeciliaTupac: {url}")

    soup = fetch_page(url)
    if not soup:
        return []

    # Links individuales de recetas: contienen "papa" en la URL
    # y no son links de navegación general
    NAV_KEYWORDS = ["recetas-rapidas", "recetas-al-horno", "recetas-con-pollo",
                    "recetas-con-carne", "recetas-faciles", "category", "tag"]

    todos = soup.select('a[href*="papa"], a[href*="receta"]')
    resultados = []

    vistos = set()
    for link in todos:
        href  = link.get("href", "")
        title = link.get_text(strip=True)

        # Filtrar navegación y duplicados
        if any(kw in href for kw in NAV_KEYWORDS):
            continue
        if not title or len(title) < 8:
            continue
        if href in vistos:
            continue
        vistos.add(href)

        url_receta = href if href.startswith("http") else f"https://www.ceciliatupac.com{href}"

        resultados.append({
            "title":       title,
            "source_url":  url_receta,
            "source":      "ceciliatupac",
            "search_term": "papa",
            "lang":        "es",
            "country":     "PE",
        })

    print(f"  -> {len(resultados)} recetas encontradas")
    time.sleep(RATE_LIMIT_SECONDS)
    return resultados


def scrape_mariaperez(max_pages: int = 5) -> list[dict]:
    """WordPress blog — paginación /category/patatas/page/{n}/"""
    resultados = []

    for page in range(1, max_pages + 1):
        if page == 1:
            url = "https://www.mariaperezmunoz.com/category/patatas/"
        else:
            url = f"https://www.mariaperezmunoz.com/category/patatas/page/{page}/"

        print(f"  MariaPerez pág {page}: {url}")

        soup = fetch_page(url)
        if not soup:
            break

        articles = soup.find_all("article")
        if not articles:
            print(f"  [!] Sin artículos en página {page}, terminando")
            break

        nuevas = 0
        for article in articles:
            # Buscar el link con el título real:
            # el primer link suele ser la imagen (texto vacío)
            # el título está en el link con texto de 10+ caracteres
            title = ""
            href  = ""

            for link in article.find_all("a", href=True):
                texto = link.get_text(strip=True)
                # Ignorar: texto vacío, fechas cortas ("15 Feb '19"), textos muy cortos
                if len(texto) >= 10:
                    title = texto
                    href  = link.get("href", "")
                    break

            if not title or not href:
                continue

            resultados.append({
                "title":       title,
                "source_url":  href,
                "source":      "mariaperez",
                "search_term": "patatas",
                "lang":        "es",
                "country":     "ES",
            })
            nuevas += 1

        print(f"  -> {nuevas} recetas encontradas")
        time.sleep(RATE_LIMIT_SECONDS)

    return resultados