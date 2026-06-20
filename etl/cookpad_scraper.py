from __future__ import annotations

import asyncio
from typing import Iterable, List, Optional
from urllib.parse import quote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from etl.transformer import extract_recipe_from_html


BASE_URL = "https://cookpad.com"
DEFAULT_TERMS = ["potato", "lasagna", "chicken soup", "pancakes", "mashed potato", "baked potato"]


def _is_recipe_url(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower()

    if parsed.netloc and "cookpad.com" not in parsed.netloc:
        return False
    if "/recipes/" not in path:
        return False
    if "/me/recipes/" in path:
        return False
    return bool(path.rstrip("/").split("/")[-1].isdigit())


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


async def scrape_cookpad(
    terms: Optional[Iterable[str]] = None,
    limit: int = 8,
    user_agent: str = "PotatoHubBot/1.0",
    timeout_seconds: float = 15.0,
):
    search_terms = list(terms) if terms else DEFAULT_TERMS
    headers = {
        "User-Agent": user_agent,
        "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
    }
    timeout = httpx.Timeout(timeout_seconds)
    discovered: List[str] = []
    seen = set()

    async with httpx.AsyncClient(headers=headers, timeout=timeout, follow_redirects=True) as client:
        home_html = await _fetch_text(client, "%s/us" % BASE_URL)
        if home_html:
            for link in _discover_links(home_html, "%s/us" % BASE_URL, limit * 4):
                if link not in seen:
                    seen.add(link)
                    discovered.append(link)

        for term in search_terms:
            search_url = "%s/eng/search/%s" % (BASE_URL, quote(term, safe=""))
            search_html = await _fetch_text(client, search_url)
            if not search_html:
                continue
            for link in _discover_links(search_html, search_url, limit * 5):
                if link not in seen:
                    seen.add(link)
                    discovered.append(link)
            if len(discovered) >= limit * 6:
                break

        # Popularity sort often surfaces different recipe ids for the same term.
        if len(discovered) < limit * 6:
            for term in search_terms[:4]:
                search_url = "%s/eng/search/%s?order=popularity" % (BASE_URL, quote(term, safe=""))
                search_html = await _fetch_text(client, search_url)
                if not search_html:
                    continue
                for link in _discover_links(search_html, search_url, limit * 5):
                    if link not in seen:
                        seen.add(link)
                        discovered.append(link)
                if len(discovered) >= limit * 6:
                    break

        if not discovered:
            return []

        return await _fetch_recipes(client, discovered[:limit], "cookpad")
