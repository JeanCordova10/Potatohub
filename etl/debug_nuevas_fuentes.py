import httpx
from bs4 import BeautifulSoup
from etl.config import HEADERS

SITIOS = [
    ("CeciliaTupac",    "https://www.ceciliatupac.com/recetas-con-papas"),
    ("PequeRecetas",    "https://www.pequerecetas.com/receta/20-recetas-de-patatas/"),
    ("MariaPerez",      "https://www.mariaperezmunoz.com/category/patatas/"),
    ("GallinaBlanca",   "https://www.gallinablanca.es/recetas/patata/"),
]

def debug_sitio(nombre: str, url: str):
    print(f"\n=== {nombre} ===")
    print(f"URL: {url}")
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
        print(f"Status: {resp.status_code}")
        if resp.status_code != 200:
            return

        soup = BeautifulSoup(resp.text, "html.parser")

        # Contar elementos comunes en sitios de recetas
        print(f"  article     : {len(soup.find_all('article'))}")
        print(f"  h2          : {len(soup.find_all('h2'))}")
        print(f"  h3          : {len(soup.find_all('h3'))}")
        sel_receta = 'a[href*="receta"]'
        sel_recipe = 'a[href*="recipe"]'
        sel_patata = 'a[href*="patata"]'
        sel_papa   = 'a[href*="papa"]'
        print(f"  a[href*=receta] : {len(soup.select(sel_receta))}")
        print(f"  a[href*=recipe] : {len(soup.select(sel_recipe))}")
        print(f"  a[href*=patata] : {len(soup.select(sel_patata))}")
        print(f"  a[href*=papa]   : {len(soup.select(sel_papa))}")
        # Mostrar los primeros 5 h2 para entender la estructura
        h2s = soup.find_all("h2")
        if h2s:
            print("  Primeros h2:")
            for h in h2s[:5]:
                print(f"    → {h.get_text(strip=True)[:60]}")

        # Mostrar primeros 3 links relevantes
        links = (
            soup.select('a[href*="receta"]') or
            soup.select('a[href*="patata"]') or
            soup.select('a[href*="papa"]')
        )
        if links:
            print("  Primeros links:")
            for l in links[:3]:
                print(f"    href : {l.get('href', '')[:80]}")
                print(f"    texto: {l.get_text(strip=True)[:50]}")

    except Exception as e:
        print(f"  [!] Error: {e}")


if __name__ == "__main__":
    for nombre, url in SITIOS:
        debug_sitio(nombre, url)