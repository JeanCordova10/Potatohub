import httpx
import re
import time
from bs4 import BeautifulSoup
from etl.config import HEADERS, RATE_LIMIT_SECONDS, MAX_PAGES, MAX_PAGES_RECETASGRATIS



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


import urllib.parse

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