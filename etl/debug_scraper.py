import httpx
import json
from bs4 import BeautifulSoup
from etl.config import HEADERS


def debug_cookpad():
    url = "https://cookpad.com/pe/buscar/papa"
    print("\n=== COOKPAD ===")
    print(f"URL: {url}")

    resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
    print(f"Status: {resp.status_code}")

    soup = BeautifulSoup(resp.text, "html.parser")

    # Cookpad usa Next.js — buscar el bloque de datos JSON
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

    # Contar elementos HTML directos
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
                    # Mostrar títulos encontrados
                    for h2 in soup.find_all("h2")[:3]:
                        print(f"    → {h2.get_text(strip=True)}")
            else:
                print(f"✗ {status} | {url}")
        except Exception as e:
            print(f"✗ Error | {url} | {e}")

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

if __name__ == "__main__":
    debug_cookpad()
    debug_cookpad_links()   # ← agregar esta línea
    debug_recetasgratis()