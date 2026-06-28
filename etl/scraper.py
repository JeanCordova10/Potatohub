import re
import time

import httpx
from bs4 import BeautifulSoup

from etl.config import HEADERS, MAX_PAGES, RATE_LIMIT_SECONDS


def fetch_page(url: str) -> BeautifulSoup | None:
    try:
        response = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
        if response.status_code == 200:
            return BeautifulSoup(response.text, "html.parser")

        print(f"  [!] Status {response.status_code} en {url}")
        return None
    except Exception as exc:
        print(f"  [!] Error al acceder {url}: {exc}")
        return None


def scrape_cookpad(term: str) -> list[dict]:
    resultados = []

    for page in range(1, MAX_PAGES + 1):
        url = f"https://cookpad.com/pe/buscar/{term}?page={page}"
        print(f"  Cookpad [{term}] pag {page}: {url}")

        soup = fetch_page(url)
        if not soup:
            break

        todos_links = soup.select('a[href*="/recetas/"]')
        recipe_links = [
            link for link in todos_links
            if re.search(r"/recetas/\d+", link.get("href", ""))
        ]

        if not recipe_links:
            print(f"  [!] Sin recetas en pagina {page}, terminando termino '{term}'")
            break

        for link in recipe_links:
            href = link.get("href", "")
            title = link.get_text(strip=True)

            if not title or not href:
                continue

            resultados.append({
                "title": title,
                "source_url": f"https://cookpad.com{href}",
                "source": "cookpad_pe",
                "search_term": term,
                "lang": "es",
                "country": "PE",
            })

        print(f"  -> {len(recipe_links)} recetas encontradas")
        time.sleep(RATE_LIMIT_SECONDS)

    return resultados
