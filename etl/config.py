# Terminos de busqueda para Cookpad PE
COOKPAD_TERMS = [
    "papa",
    "causa",
    "papa-a-la-huancaina",
    "papa-rellena",
    "ocopa",
    "papa-seca",
    "papa-amarilla",
    "pure-de-papa",
    "papas-fritas",
]

# Maximo de paginas por termino en Cookpad
MAX_PAGES = 40

# 1 request cada 4 segundos para scraping responsable
RATE_LIMIT_SECONDS = 5

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-PE,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

CATEGORY_KEYWORDS = {
    "CAUSA": ["causa", "causa limeña", "causa limena"],
    "PURE": ["puré", "pure", "purée"],
    "OCOPA": ["ocopa", "huancaína", "huancaina"],
    "FRITA": ["frita", "fritas", "chips", "croqueta", "croquetas"],
    "RELLENA": ["rellena", "rellenas", "relleno"],
    "SOPA": ["sopa", "chupe", "caldo", "locro", "crema"],
    "GUISO": ["guiso", "estofado", "saltado", "seco", "aji de"],
    "HORNEADA": ["horneada", "horneadas", "al horno", "gratinada", "gratín"],
    "CHUÑO": ["chuño", "chuno", "papa seca", "moraya"],
}
