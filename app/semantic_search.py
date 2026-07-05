import re
import unicodedata
from typing import Any, Iterable


SEMANTIC_VERSION = 2

COMMON_STOPWORDS = {
    "a",
    "al",
    "and",
    "con",
    "de",
    "del",
    "el",
    "en",
    "for",
    "la",
    "las",
    "los",
    "of",
    "para",
    "por",
    "sin",
    "the",
    "to",
    "una",
    "uno",
    "unos",
    "unas",
    "with",
    "y",
}

GENERIC_RECIPE_TERMS = {
    "baby",
    "best",
    "bite",
    "bites",
    "bowl",
    "dish",
    "easy",
    "fresh",
    "fries",
    "fry",
    "homemade",
    "papa",
    "papas",
    "potato",
    "potatoes",
    "recipe",
    "recipes",
    "simple",
    "spud",
    "spuds",
    "style",
}

INGREDIENT_NOISE_TERMS = {
    "about",
    "chopped",
    "cup",
    "cups",
    "diced",
    "freshly",
    "gram",
    "grams",
    "kg",
    "large",
    "lb",
    "medium",
    "minced",
    "ml",
    "oil",
    "optional",
    "ounce",
    "ounces",
    "oz",
    "peeled",
    "pinch",
    "pound",
    "powder",
    "quartered",
    "shakes",
    "sliced",
    "small",
    "taste",
    "tbsp",
    "teaspoon",
    "teaspoons",
    "to",
    "tsp",
    "whole",
}

TOKEN_ALIASES = {
    "aji": "aji",
    "ajo": "ajo",
    "avocado": "palta",
    "bean": "frijol",
    "beans": "frijol",
    "beef": "res",
    "bread": "pan",
    "broccoli": "brocoli",
    "bun": "pan",
    "buns": "pan",
    "butter": "mantequilla",
    "camote": "camote",
    "carrot": "zanahoria",
    "carrots": "zanahoria",
    "cebollas": "cebolla",
    "cheese": "queso",
    "chicken": "pollo",
    "chickens": "pollo",
    "chile": "aji",
    "chili": "aji",
    "chilli": "aji",
    "corn": "maiz",
    "egg": "huevo",
    "eggs": "huevo",
    "fish": "pescado",
    "garlic": "ajo",
    "green": "verde",
    "greens": "verde",
    "meat": "carne",
    "milk": "leche",
    "mushroom": "hongo",
    "mushrooms": "hongo",
    "onion": "cebolla",
    "onions": "cebolla",
    "palta": "palta",
    "papas": "papa",
    "patata": "papa",
    "patatas": "papa",
    "pepper": "pimiento",
    "peppers": "pimiento",
    "pork": "cerdo",
    "potato": "papa",
    "potatoes": "papa",
    "prawn": "camaron",
    "prawns": "camaron",
    "rice": "arroz",
    "salmon": "salmon",
    "scallion": "cebolla",
    "scallions": "cebolla",
    "shallot": "cebolla",
    "shallots": "cebolla",
    "shrimp": "camaron",
    "soup": "sopa",
    "spud": "papa",
    "spuds": "papa",
    "sweet": "dulce",
    "tomato": "tomate",
    "tomatoes": "tomate",
    "tuna": "atun",
    "vegetable": "verdura",
    "vegetables": "verdura",
}

CATEGORY_ALIASES = {
    "acompanamiento": "acompanamiento",
    "appetizer": "entrada",
    "beverage": "bebida",
    "breakfast": "desayuno",
    "cena": "cena",
    "dessert": "postre",
    "desayuno": "desayuno",
    "dinner": "cena",
    "drink": "bebida",
    "entrada": "entrada",
    "ensalada": "ensalada",
    "general": "general",
    "lunch": "almuerzo",
    "main course": "plato principal",
    "main dish": "plato principal",
    "merienda": "merienda",
    "papa": "papa",
    "plato principal": "plato principal",
    "potato": "papa",
    "postre": "postre",
    "salad": "ensalada",
    "side dish": "acompanamiento",
    "snack": "merienda",
    "sopa": "sopa",
    "soup": "sopa",
}

DIFFICULTY_ALIASES = {
    "advanced": "dificil",
    "beginner": "facil",
    "dificil": "dificil",
    "easy": "facil",
    "facil": "facil",
    "hard": "dificil",
    "intermediate": "media",
    "medium": "media",
    "media": "media",
}

MOJIBAKE_MARKERS = ("Ã", "Â", "â", "ð", "ï¿½", "�")
EMOJI_RANGES = re.compile("[\U0001F1E6-\U0001F1FF\U0001F300-\U0001FAFF\U00002700-\U000027BF]")


def repair_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    for _ in range(2):
        if not any(marker in text for marker in MOJIBAKE_MARKERS):
            break
        repaired = text
        for encoding in ("latin-1", "cp1252"):
            try:
                candidate = repaired.encode(encoding).decode("utf-8")
            except UnicodeError:
                continue
            if candidate and candidate != repaired:
                repaired = candidate
                break
        if repaired == text:
            break
        text = repaired
    text = "".join(char for char in text if char.isprintable() or char in "\n\r\t")
    return re.sub(r"\s+", " ", text).strip()


def clean_human_text(value: Any) -> str:
    text = repair_text(value)
    text = EMOJI_RANGES.sub("", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_text(value: Any) -> str:
    text = clean_human_text(value).lower().strip()
    if not text:
        return ""
    text = text.replace("&", " y ")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-z0-9\s]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def tokenize_text(value: Any) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9]+", normalize_text(value)) if token]


def ordered_unique(tokens: Iterable[str], limit: int = 64) -> list[str]:
    results: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if not token or token in seen:
            continue
        seen.add(token)
        results.append(token)
        if len(results) >= limit:
            break
    return results


def canonicalize_token(token: Any) -> str:
    normalized = normalize_text(token)
    if not normalized:
        return ""
    return TOKEN_ALIASES.get(normalized, normalized)


def canonicalize_category(value: Any) -> str:
    normalized = normalize_text(value)
    if not normalized:
        return "general"
    if normalized in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[normalized]
    return CATEGORY_ALIASES.get(canonicalize_token(normalized), normalized)


def canonicalize_difficulty(value: Any) -> str:
    normalized = normalize_text(value)
    if not normalized:
        return ""
    if normalized in DIFFICULTY_ALIASES:
        return DIFFICULTY_ALIASES[normalized]
    return DIFFICULTY_ALIASES.get(canonicalize_token(normalized), normalized)


def is_search_token(token: str) -> bool:
    return bool(token) and len(token) > 2 and token not in COMMON_STOPWORDS and not token.isdigit()


def is_useful_recipe_token(token: str) -> bool:
    return (
        is_search_token(token)
        and token not in GENERIC_RECIPE_TERMS
        and token not in INGREDIENT_NOISE_TERMS
    )


def singularize_token(token: str) -> list[str]:
    variants = [token]
    if token.endswith("es") and len(token) > 4:
        variants.append(token[:-2])
    elif token.endswith("s") and len(token) > 3:
        variants.append(token[:-1])
    else:
        variants.append(token + "s")
    return ordered_unique(variants, limit=4)


def expand_semantic_terms(tokens: Iterable[str]) -> list[str]:
    expanded: list[str] = []
    for token in tokens:
        canonical = canonicalize_token(token)
        for variant in singularize_token(canonical):
            if is_search_token(variant):
                expanded.append(variant)
        if canonical != token:
            for variant in singularize_token(token):
                if is_search_token(variant):
                    expanded.append(variant)
    return ordered_unique(expanded, limit=64)


def extract_title_terms(title: Any) -> list[str]:
    tokens = [
        canonicalize_token(token)
        for token in tokenize_text(title)
        if is_useful_recipe_token(token)
    ]
    tokens = [
        token
        for token in tokens
        if token and token not in GENERIC_RECIPE_TERMS and token not in COMMON_STOPWORDS
    ]
    return ordered_unique(tokens, limit=16)


def extract_ingredient_terms(ingredients: Iterable[Any]) -> list[str]:
    extracted: list[str] = []
    for ingredient in ingredients or []:
        for token in tokenize_text(ingredient):
            if not is_useful_recipe_token(token):
                continue
            canonical = canonicalize_token(token)
            if canonical and canonical not in GENERIC_RECIPE_TERMS and canonical not in INGREDIENT_NOISE_TERMS:
                extracted.append(canonical)
    return ordered_unique(extracted, limit=48)


def extract_free_text_terms(value: Any, limit: int = 24) -> list[str]:
    extracted = [
        canonicalize_token(token)
        for token in tokenize_text(value)
        if is_search_token(token) and token not in GENERIC_RECIPE_TERMS
    ]
    return ordered_unique([token for token in extracted if token], limit=limit)


def build_query_signals(query: Any) -> dict:
    raw_query = clean_human_text(query)
    normalized_query = normalize_text(raw_query)
    query_terms = expand_semantic_terms(tokenize_text(raw_query))
    category_canonical = CATEGORY_ALIASES.get(normalized_query, "")
    difficulty_canonical = DIFFICULTY_ALIASES.get(normalized_query, "")
    return {
        "raw_query": raw_query,
        "normalized_query": normalized_query,
        "query_terms": set(query_terms),
        "category_canonical": category_canonical,
        "difficulty_canonical": difficulty_canonical,
    }


def build_recipe_search_fields(recipe: dict) -> dict:
    title = clean_human_text(recipe.get("title") or "")
    description = clean_human_text(recipe.get("description") or "")
    ingredients = [clean_human_text(item) for item in recipe.get("ingredients") or [] if clean_human_text(item)]
    instructions = [clean_human_text(item) for item in recipe.get("instructions") or [] if clean_human_text(item)]
    tags = [clean_human_text(item) for item in recipe.get("tags") or [] if clean_human_text(item)]
    category_value = recipe.get("category_canonical") or recipe.get("category_potato") or recipe.get("category") or "general"
    difficulty_value = recipe.get("difficulty_canonical") or recipe.get("difficulty") or ""

    title_canonical = normalize_text(title)
    description_canonical = normalize_text(description)
    ingredients_canonical = [normalize_text(item) for item in ingredients if normalize_text(item)]
    instructions_canonical = [normalize_text(item) for item in instructions if normalize_text(item)]
    category_canonical = canonicalize_category(category_value)
    difficulty_canonical = canonicalize_difficulty(difficulty_value)

    title_terms = extract_title_terms(title)
    ingredient_terms = extract_ingredient_terms(ingredients)
    description_terms = extract_free_text_terms(description, limit=28)
    tag_terms = extract_free_text_terms(" ".join(tags), limit=16)

    search_terms = ordered_unique(
        title_terms
        + ingredient_terms
        + description_terms
        + tag_terms
        + tokenize_text(category_canonical)
        + tokenize_text(difficulty_canonical),
        limit=128,
    )
    search_text_canonical = " ".join(
        ordered_unique(
            [title_canonical, description_canonical]
            + ingredients_canonical
            + instructions_canonical[:8]
            + [category_canonical, difficulty_canonical, " ".join(search_terms)],
            limit=48,
        )
    )

    return {
        "title_canonical": title_canonical,
        "description_canonical": description_canonical,
        "ingredients_canonical": ingredients_canonical,
        "instructions_canonical": instructions_canonical,
        "category_canonical": category_canonical,
        "difficulty_canonical": difficulty_canonical,
        "title_terms": title_terms,
        "ingredient_terms": ingredient_terms,
        "search_terms": search_terms,
        "search_text_canonical": search_text_canonical,
        "language": "es",
    }
