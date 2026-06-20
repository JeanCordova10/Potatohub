import httpx
import json
import os
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from etl.config import HEADERS

load_dotenv()


def debug_cookpad():
    url = "https://cookpad.com/pe/buscar/papa"
    print("\n=== COOKPAD ===")
    print(f"URL: {url}")
    resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
    print(f"Status: {resp.status_code}")
    soup = BeautifulSoup(resp.text, "html.parser")
    next_data = soup.find("script", id="__NEXT_DATA__")
    if next_data:
        print("✓ Encontrado __NEXT_DATA__ (Next.js)")
        data = json.loads(next_data.string)
        page_props = data.get("props", {}).get("pageProps", {})
        print(f"  Keys en pageProps: {list(page_props.keys())}")
        for key, value in page_props.items():
            if isinstance(value, list) and len(value) > 0:
                primer = value[0]
                print(f"  Lista '{key}': {len(value)} items")
                if isinstance(primer, dict):
                    print(f"    Keys del primer item: {list(primer.keys())}")
    else:
        print("✗ No hay __NEXT_DATA__")
    print(f"\nElementos HTML encontrados:")
    print(f"  li[data-recipe-id] : {len(soup.select('li[data-recipe-id]'))}")
    print(f"  article            : {len(soup.find_all('article'))}")
    print(f"  h2                 : {len(soup.find_all('h2'))}")
    selector = 'a[href*="/recetas/"]'
    print(f"  a[href*='/recetas/']: {len(soup.select(selector))}")
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


def debug_recetasgratis():
    print("\n=== RECETASGRATIS ===")
    urls = [
        "https://recetas.elperiodico.com/busqueda?q=papa",
        "https://recetas.elperiodico.com/busqueda?q=causa",
        "https://recetas.elperiodico.com/tag/papa/",
        "https://recetas.elperiodico.com/tags/papa/",
    ]
    for url in urls:
        try:
            resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
            status = resp.status_code
            if status == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                articles = len(soup.find_all("article"))
                h2s = len(soup.find_all("h2"))
                links_receta = len(soup.select("a[href*='/receta']"))
                print(f"✓ {status} | articles={articles} h2={h2s} links_receta={links_receta} | {url}")
                if articles > 0 or h2s > 3:
                    for h2 in soup.find_all("h2")[:3]:
                        print(f"    → {h2.get_text(strip=True)}")
            else:
                print(f"✗ {status} | {url}")
        except Exception as e:
            print(f"✗ Error | {url} | {e}")


def debug_recipe_detail():
    """Ver qué hay en una página de receta individual de Cookpad."""
    url = "https://cookpad.com/pe/recetas/24680045"
    print(f"\n=== DETALLE RECETA COOKPAD ===")
    print(f"URL: {url}")
    resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
    print(f"Status: {resp.status_code}")
    soup = BeautifulSoup(resp.text, "html.parser")
    next_data = soup.find("script", id="__NEXT_DATA__")
    if next_data:
        print("✓ Encontrado __NEXT_DATA__")
        data = json.loads(next_data.string)
        page_props = data.get("props", {}).get("pageProps", {})
        print(f"  Keys en pageProps: {list(page_props.keys())}")
        for key, value in page_props.items():
            if "ingredient" in key.lower() or "step" in key.lower() or "recipe" in key.lower():
                print(f"  → '{key}': {str(value)[:200]}")
    else:
        print("✗ No hay __NEXT_DATA__")
    print(f"\nElementos buscados:")
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
        print(f"\nPrimeros 5 li:")
        for li in lis[:5]:
            print(f"  → {li.get_text(strip=True)[:80]}")


def debug_otras_fuentes():
    """Debug de páginas de detalle para RecetasGratis, CeciliaTupac y MariaPerez."""
    from pymongo import MongoClient
    client = MongoClient(os.getenv("MONGO_URI_LOCAL", "mongodb://localhost:27017/?directConnection=true"))
    db = client.potatohub

    fuentes = ["recetasgratis", "ceciliatupac", "mariaperez"]

    for fuente in fuentes:
        receta = db.recipes.find_one({"source": fuente, "ingredients": []})
        if not receta:
            print(f"\n=== {fuente.upper()} — sin recetas pendientes ===")
            continue

        url   = receta["source_url"]
        title = receta["title"]
        print(f"\n=== {fuente.upper()} ===")
        print(f"Título : {title}")
        print(f"URL    : {url}")

        resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
        print(f"Status : {resp.status_code}")
        if resp.status_code != 200:
            continue

        soup = BeautifulSoup(resp.text, "html.parser")

        print(f"\nElementos:")
        print(f"  ul li           : {len(soup.select('ul li'))}")
        print(f"  ol li           : {len(soup.select('ol li'))}")
        print(f"  [class*=ingred] : {len(soup.select('[class*=ingred]'))}")
        print(f"  [class*=ingredi]: {len(soup.select('[class*=ingredi]'))}")
        print(f"  [class*=step]   : {len(soup.select('[class*=step]'))}")
        print(f"  [class*=instruc]: {len(soup.select('[class*=instruc]'))}")
        print(f"  [class*=prepar] : {len(soup.select('[class*=prepar]'))}")
        print(f"  [id*=ingred]    : {len(soup.select('[id*=ingred]'))}")
        print(f"  [id*=step]      : {len(soup.select('[id*=step]'))}")
        print(f"  [id*=instruc]   : {len(soup.select('[id*=instruc]'))}")

        ul_lis = soup.select("ul li")
        if ul_lis:
            print(f"\nPrimeros 5 ul > li:")
            for li in ul_lis[:5]:
                print(f"  → {li.get_text(strip=True)[:80]}")

        ol_lis = soup.select("ol li")
        if ol_lis:
            print(f"\nPrimeros 5 ol > li:")
            for li in ol_lis[:5]:
                print(f"  → {li.get_text(strip=True)[:80]}")

        ingred_els = soup.select('[class*=ingred]')
        if ingred_els:
            print(f"\nElementos [class*=ingred]:")
            for el in ingred_els[:3]:
                print(f"  class={el.get('class')} | {el.get_text(strip=True)[:80]}")

        for selector in ['[class*=instruc]', '[class*=prepar]', '[class*=step]']:
            els = soup.select(selector)
            if els:
                print(f"\nElementos {selector}:")
                for el in els[:3]:
                    print(f"  class={el.get('class')} | {el.get_text(strip=True)[:80]}")
                break


if __name__ == "__main__":
    debug_otras_fuentes()