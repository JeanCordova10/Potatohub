from __future__ import annotations

import asyncio
from typing import Iterable, List, Optional
from urllib.parse import quote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from etl.transformer import extract_recipe_from_html


BASE_URL = "https://recetas.elperiodico.com"
DEFAULT_TERMS = ["papa", "patata", "pollo", "ensalada", "postre", "arroz"]


def _is_recipe_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.netloc and "recetas.elperiodico.com" not in parsed.netloc:
        return False

    path = parsed.path.lower()
    if "listado_receta" in path:
        return False
    if "receta-" not in path:
        return False
    return path.endswith(".html")


def _discover_links(html_text: str, page_url: str, limit: int) -> List[str]:
    soup = BeautifulSoup(html_text, "html.parser")
    discovered: List[str] = []

    for anchor in soup.find_all("a", href=True):
        href = urljoin(page_url, anchor["href"])
        if not _is_recipe_url(href):
            continue
        if href not in discovered:
            discovered.append(href)
        if len(discovered) >= limit:
            break

    return discovered


async def _fetch_text(client: httpx.AsyncClient, url: str) -> str:
    try:
        response = await client.get(url)
        response.raise_for_status()
        return response.text
    except Exception:
        return ""


async def _fetch_recipes(client: httpx.AsyncClient, urls: Iterable[str], source_name: str):
    responses = await asyncio.gather(*(client.get(url) for url in urls), return_exceptions=True)
    recipes = []
    for url, response in zip(urls, responses):
        if isinstance(response, Exception):
            continue
        try:
            response.raise_for_status()
        except Exception:
            continue
        recipe = extract_recipe_from_html(response.text, url, source_name)
        if recipe:
            recipes.append(recipe)
    return recipes


async def scrape_recetasgratis(
    terms: Optional[Iterable[str]] = None,
    limit: int = 8,
    user_agent: str = "PotatoHubBot/1.0",
    timeout_seconds: float = 15.0,
):
    search_terms = list(terms) if terms else DEFAULT_TERMS
    headers = {
        "User-Agent": user_agent,
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    }
    timeout = httpx.Timeout(timeout_seconds)
    discovered: List[str] = []
    seen = set()

    async with httpx.AsyncClient(headers=headers, timeout=timeout, follow_redirects=True) as client:
        home_html = await _fetch_text(client, BASE_URL)
        if home_html:
            for link in _discover_links(home_html, BASE_URL, limit * 4):
                if link not in seen:
                    seen.add(link)
                    discovered.append(link)

            soup = BeautifulSoup(home_html, "html.parser")
            category_urls = []
            for anchor in soup.find_all("a", href=True):
                href = urljoin(BASE_URL, anchor["href"])
                parsed = urlparse(href)
                if parsed.netloc and "recetas.elperiodico.com" not in parsed.netloc:
                    continue
                if "listado_receta" in parsed.path.lower() and href not in category_urls:
                    category_urls.append(href)
                if len(category_urls) >= 6:
                    break

            for category_url in category_urls[:4]:
                category_html = await _fetch_text(client, category_url)
                if not category_html:
                    continue
                for link in _discover_links(category_html, category_url, limit * 4):
                    if link not in seen:
                        seen.add(link)
                        discovered.append(link)

        for term in search_terms:
            search_url = "%s/busqueda/q/%s" % (BASE_URL, quote(term, safe=""))
            search_html = await _fetch_text(client, search_url)
            if not search_html:
                continue
            for link in _discover_links(search_html, search_url, limit * 4):
                if link not in seen:
                    seen.add(link)
                    discovered.append(link)
            if len(discovered) >= limit * 5:
                break

        if not discovered:
            return []

        return await _fetch_recipes(client, discovered[:limit], "recetasgratis")
