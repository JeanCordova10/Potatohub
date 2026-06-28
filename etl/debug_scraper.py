import json

import httpx
from bs4 import BeautifulSoup

from etl.config import HEADERS


def debug_cookpad():
    url = "https://cookpad.com/pe/buscar/papa"
    print("\n=== COOKPAD ===")
    print(f"URL: {url}")

    resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
    print(f"Status: {resp.status_code}")

    soup = BeautifulSoup(resp.text, "html.parser")
    next_data = soup.find("script", id="__NEXT_DATA__")

    if next_data:
        print("Encontrado __NEXT_DATA__ (Next.js)")
        data = json.loads(next_data.string)
        page_props = data.get("props", {}).get("pageProps", {})
        print(f"  Keys en pageProps: {list(page_props.keys())}")
        for key, value in page_props.items():
            if isinstance(value, list) and value:
                primer = value[0]
                print(f"  Lista '{key}': {len(value)} items")
                if isinstance(primer, dict):
                    print(f"    Keys del primer item: {list(primer.keys())}")
    else:
        print("No hay __NEXT_DATA__")

    print("\nElementos HTML encontrados:")
    print(f"  li[data-recipe-id] : {len(soup.select('li[data-recipe-id]'))}")
    print(f"  article            : {len(soup.find_all('article'))}")
    print(f"  h2                 : {len(soup.find_all('h2'))}")
    links_count = len(soup.select('a[href*="/recetas/"]'))
    print(f"  a[href*='/recetas/']: {links_count}")

    body = soup.find("body")
    if body:
        texto = body.get_text(strip=True)
        print(f"\nPrimeros 300 chars del body:\n{texto[:300]}")


def debug_cookpad_links():
    url = "https://cookpad.com/pe/buscar/papa"
    resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
    soup = BeautifulSoup(resp.text, "html.parser")

    print("\n=== LINKS /recetas/ ENCONTRADOS EN COOKPAD ===")
    links = soup.select('a[href*="/recetas/"]')
    for link in links[:10]:
        href = link.get("href", "")
        texto = link.get_text(strip=True)[:60]
        print(f"  href : {href}")
        print(f"  texto: {texto}")
        print()


def debug_recipe_detail():
    url = "https://cookpad.com/pe/recetas/24680045"
    print("\n=== DETALLE RECETA COOKPAD ===")
    print(f"URL: {url}")

    resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
    print(f"Status: {resp.status_code}")

    soup = BeautifulSoup(resp.text, "html.parser")
    next_data = soup.find("script", id="__NEXT_DATA__")

    if next_data:
        print("Encontrado __NEXT_DATA__")
        data = json.loads(next_data.string)
        page_props = data.get("props", {}).get("pageProps", {})
        print(f"  Keys en pageProps: {list(page_props.keys())}")
        for key, value in page_props.items():
            key_lower = key.lower()
            if "ingredient" in key_lower or "step" in key_lower or "recipe" in key_lower:
                print(f"  -> '{key}': {str(value)[:200]}")
    else:
        print("No hay __NEXT_DATA__")

    print("\nElementos buscados:")
    print(f"  ul li          : {len(soup.select('ul li'))}")
    print(f"  [class*=ingred]: {len(soup.select('[class*=ingred]'))}")
    print(f"  [class*=step]  : {len(soup.select('[class*=step]'))}")
    print(f"  [id*=ingred]   : {len(soup.select('[id*=ingred]'))}")
    print(f"  [id*=step]     : {len(soup.select('[id*=step]'))}")

    print("\nElementos [id*=ingred]:")
    for el in soup.select('[id*=ingred]')[:5]:
        print(f"  id='{el.get('id')}' | texto: {el.get_text(strip=True)[:80]}")

    print("\nElementos [class*=ingred]:")
    for el in soup.select('[class*=ingred]')[:3]:
        print(f"  class='{el.get('class')}' | texto: {el.get_text(strip=True)[:80]}")

    print("\nElementos [class*=step]:")
    for el in soup.select('[class*=step]')[:5]:
        print(f"  class='{el.get('class')}' | texto: {el.get_text(strip=True)[:80]}")

    print("\nElementos [id*=step]:")
    for el in soup.select('[id*=step]')[:5]:
        print(f"  id='{el.get('id')}' | texto: {el.get_text(strip=True)[:80]}")

    lis = soup.select("ul li")
    if lis:
        print("\nPrimeros 5 li:")
        for li in lis[:5]:
            print(f"  -> {li.get_text(strip=True)[:80]}")


if __name__ == "__main__":
    debug_cookpad()
    debug_cookpad_links()
    debug_recipe_detail()
