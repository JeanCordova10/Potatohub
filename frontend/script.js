document.addEventListener("DOMContentLoaded", function () {
    const API_BASE = "/api";
    const DEFAULT_PAGE_SIZE = 12;
    const AUTH_STORAGE_KEY = "potatohub.auth";
    const UI_STORAGE_KEY = "potatohub.ui";

    var state = {
        page: 0,
        query: "",
        category: "",
        difficulty: "",
        pageSize: DEFAULT_PAGE_SIZE,
    };

    var tabs = Array.prototype.slice.call(document.querySelectorAll(".tab-btn"));
    var tabContents = Array.prototype.slice.call(document.querySelectorAll(".tab-content"));
    var searchInput = document.getElementById("searchInput");
    var searchBtn = document.getElementById("searchBtn");
    var filterCategory = document.getElementById("filterCategory");
    var filterDifficulty = document.getElementById("filterDifficulty");
    var recommendationMode = document.getElementById("recommendationMode");
    var pageSizeSelect = document.getElementById("pageSizeSelect");
    var searchResults = document.getElementById("searchResults");
    var searchPagination = document.getElementById("searchPagination");
    var paginationSummary = document.getElementById("paginationSummary");
    var rankingResults = document.getElementById("rankingResults");
    var recommendResults = document.getElementById("recommendResults");
    var recipeIdInput = document.getElementById("recipeIdInput");
    var recommendBtn = document.getElementById("recommendBtn");
    var refreshBtn = document.getElementById("refreshBtn");
    var refreshStatus = document.getElementById("refreshStatus");
    var catalogCount = document.getElementById("catalogCount");
    var apiStatus = document.getElementById("apiStatus");
    var catalogModeBadge = document.getElementById("catalogModeBadge");
    var authBtn = document.getElementById("authBtn");
    var userChip = document.getElementById("userChip");
    var logoutBtn = document.getElementById("logoutBtn");
    var recipeModal = document.getElementById("recipeModal");
    var recipeModalBody = document.getElementById("recipeModalBody");
    var recipeModalTitle = document.getElementById("recipeModalTitle");
    var recipeModalClose = document.getElementById("recipeModalClose");
    var authModal = document.getElementById("authModal");
    var authModalClose = document.getElementById("authModalClose");
    var authModalTitle = document.getElementById("authModalTitle");
    var authStatus = document.getElementById("authStatus");
    var loginForm = document.getElementById("loginForm");
    var registerForm = document.getElementById("registerForm");
    var authTabButtons = Array.prototype.slice.call(document.querySelectorAll(".auth-tab"));
    var loginEmail = document.getElementById("loginEmail");
    var loginPassword = document.getElementById("loginPassword");
    var registerName = document.getElementById("registerName");
    var registerEmail = document.getElementById("registerEmail");
    var registerPassword = document.getElementById("registerPassword");
    var recipeCache = {};
    var currentRecipeId = "";
    var catalogRecipes = [];
    var catalogMode = "loading";
    var apiOnline = false;
    var liveCatalogLoading = false;
    var authState = {
        token: "",
        user: null,
    };

    function escapeHtml(value) {
        return String(value == null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function escapeJs(value) {
        return String(value == null ? "" : value)
            .replace(/\\/g, "\\\\")
            .replace(/'/g, "\\'")
            .replace(/"/g, '\\"')
            .replace(/\r/g, "\\r")
            .replace(/\n/g, "\\n");
    }

    function truncateText(value, maxLength) {
        var text = String(value == null ? "" : value);
        if (text.length <= maxLength) {
            return text;
        }
        return text.slice(0, Math.max(maxLength - 1, 0)) + "...";
    }

    function formatTime(minutes) {
        var value = Number(minutes);
        if (!isFinite(value) || value <= 0) {
            return "Tiempo no disponible";
        }
        return value + " min";
    }

    function formatCount(count, singular, plural) {
        var value = Number(count);
        if (!isFinite(value) || value <= 0) {
            return "Sin " + plural;
        }
        return value + " " + (value === 1 ? singular : plural);
    }

    function normalizeTextValue(value) {
        var text = String(value == null ? "" : value).trim().toLowerCase();
        if (text.normalize) {
            text = text.normalize("NFKD").replace(/[\u0300-\u036f]/g, "");
        }
        return text;
    }

    function slugify(value) {
        return normalizeTextValue(value)
            .replace(/[^a-z0-9]+/g, "-")
            .replace(/^-+|-+$/g, "");
    }

    function capitalizeText(value) {
        var text = String(value == null ? "" : value).trim();
        if (!text) {
            return "";
        }
        return text.charAt(0).toUpperCase() + text.slice(1);
    }

    function formatCategoryLabel(value) {
        var normalized = normalizeTextValue(value || "");
        var labels = {
            acompanamiento: "Acompañamiento",
            appetizer: "Entrada",
            breakfast: "Desayuno",
            cena: "Cena",
            dessert: "Postre",
            desayuno: "Desayuno",
            dinner: "Cena",
            drink: "Bebida",
            entrada: "Entrada",
            ensalada: "Ensalada",
            general: "General",
            lunch: "Almuerzo",
            "main course": "Plato principal",
            "main dish": "Plato principal",
            merienda: "Merienda",
            papa: "Papa",
            plato: "Plato",
            "plato principal": "Plato principal",
            potato: "Papa",
            postre: "Postre",
            salad: "Ensalada",
            "side dish": "Acompañamiento",
            snack: "Merienda",
            sopa: "Sopa",
            soup: "Sopa"
        };
        return labels[normalized] || capitalizeText(value);
    }

    function formatDifficultyLabel(value) {
        var normalized = normalizeTextValue(value || "");
        var labels = {
            advanced: "Avanzada",
            beginner: "Principiante",
            dificil: "Difícil",
            easy: "Fácil",
            facil: "Fácil",
            hard: "Difícil",
            intermediate: "Intermedia",
            medium: "Media",
            media: "Media"
        };
        return labels[normalized] || capitalizeText(value);
    }

    function formatCatalogModeLabel(mode) {
        var normalized = normalizeTextValue(mode || "");
        if (normalized === "live") {
            return "Catálogo en vivo";
        }
        if (normalized === "demo") {
            return "Catálogo demo";
        }
        if (normalized === "loading") {
            return "Cargando catálogo";
        }
        return "Catálogo";
    }

    function formatApiStatusLabel(value) {
        var normalized = normalizeTextValue(value || "");
        if (normalized === "ok" || normalized === "online") {
            return "En línea";
        }
        if (normalized === "degraded") {
            return "Con fallas";
        }
        if (normalized === "offline") {
            return "Sin conexión";
        }
        return capitalizeText(value);
    }

    function cloneRecipe(recipe) {
        return JSON.parse(JSON.stringify(recipe || {}));
    }

    function buildRecipe(recipe, index) {
        var item = cloneRecipe(recipe);
        item.id = String(item.id || ("demo-" + index + "-" + slugify(item.title || "recipe")));
        item.title = String(item.title || "Untitled recipe");
        item.description = String(item.description || "");
        item.category = String(item.category || "General");
        item.difficulty = String(item.difficulty || "easy");
        item.cooking_time = Number(item.cooking_time || 0);
        item.ingredients = Array.isArray(item.ingredients) ? item.ingredients : [];
        item.instructions = Array.isArray(item.instructions) ? item.instructions : [];
        item.tags = Array.isArray(item.tags) ? item.tags : [];
        item.source_name = String(item.source_name || "demo");
        item.source_url = String(item.source_url || "");
        item.image_url = item.image_url ? String(item.image_url).trim() : "";
        item.stats = item.stats && typeof item.stats === "object" ? item.stats : { views: 0, saved: 0 };
        item.stats.views = Number(item.stats.views || 0);
        item.stats.saved = Number(item.stats.saved || 0);
        item.stats.cooked = Number(item.stats.cooked || 0);
        item.score = Number(item.score || 0);
        item.created_at = item.created_at || new Date().toISOString();
        item.updated_at = item.updated_at || item.created_at;
        return item;
    }

    function getRecipeTone(recipe) {
        var category = normalizeTextValue(recipe && recipe.category);
        if (category.indexOf("potato") !== -1 || category.indexOf("pap") !== -1) {
            return "potato";
        }
        if (category.indexOf("soup") !== -1) {
            return "soup";
        }
        if (category.indexOf("salad") !== -1) {
            return "salad";
        }
        if (category.indexOf("breakfast") !== -1) {
            return "breakfast";
        }
        if (category.indexOf("dessert") !== -1) {
            return "dessert";
        }
        if (category.indexOf("snack") !== -1) {
            return "snack";
        }
        if (category.indexOf("main") !== -1 || category.indexOf("dish") !== -1) {
            return "main";
        }
        return "neutral";
    }

    function setCatalogMode(mode, label) {
        catalogMode = mode;
        if (!catalogModeBadge) {
            return;
        }
        catalogModeBadge.textContent = label || formatCatalogModeLabel(mode);
        catalogModeBadge.className = "inline-status " + (mode === "live" ? "success" : mode === "demo" ? "warning" : "idle");
    }

    function setCatalogRecipes(recipes, mode) {
        catalogRecipes = (recipes || []).map(function (recipe, index) {
            return buildRecipe(recipe, index);
        });
        recipeCache = {};
        catalogRecipes.forEach(storeRecipe);
        setCatalogMode(mode || "demo");
        updateCatalogCount(catalogRecipes.length);
    }

    function getRecipeById(recipeId) {
        if (!recipeId) {
            return null;
        }
        for (var i = 0; i < catalogRecipes.length; i += 1) {
            if (catalogRecipes[i].id === recipeId) {
                return catalogRecipes[i];
            }
        }
        return recipeCache[recipeId] || null;
    }

    function updateRecipeInCatalog(recipeId, updater) {
        var recipe = getRecipeById(recipeId);
        if (!recipe) {
            return null;
        }
        updater(recipe);
        recipe.updated_at = new Date().toISOString();
        recipeCache[recipeId] = recipe;
        return recipe;
    }

    function tokenizeText(value) {
        return normalizeTextValue(value)
            .split(/[^a-z0-9]+/g)
            .filter(Boolean);
    }

    function canonicalizeSemanticToken(token) {
        var aliases = {
            appetizer: "entrada",
            avocado: "palta",
            bean: "frijol",
            beans: "frijol",
            beef: "res",
            bread: "pan",
            breakfast: "desayuno",
            broccoli: "brocoli",
            bun: "pan",
            buns: "pan",
            butter: "mantequilla",
            carrot: "zanahoria",
            carrots: "zanahoria",
            cebollas: "cebolla",
            cheese: "queso",
            chicken: "pollo",
            chili: "aji",
            chilli: "aji",
            chile: "aji",
            corn: "maiz",
            dessert: "postre",
            dinner: "cena",
            eggs: "huevo",
            egg: "huevo",
            fish: "pescado",
            garlic: "ajo",
            lunch: "almuerzo",
            main: "principal",
            meat: "carne",
            milk: "leche",
            mushroom: "hongo",
            mushrooms: "hongo",
            onion: "cebolla",
            onions: "cebolla",
            papas: "papa",
            patata: "papa",
            patatas: "papa",
            pepper: "pimiento",
            peppers: "pimiento",
            pork: "cerdo",
            potato: "papa",
            potatoes: "papa",
            prawn: "camaron",
            prawns: "camaron",
            recipe: "receta",
            recipes: "receta",
            salad: "ensalada",
            scallion: "cebolla",
            scallions: "cebolla",
            shallot: "cebolla",
            shallots: "cebolla",
            shrimp: "camaron",
            snack: "merienda",
            soup: "sopa",
            spud: "papa",
            spuds: "papa",
            tomato: "tomate",
            tomatoes: "tomate",
            tuna: "atun",
            vegetable: "verdura",
            vegetables: "verdura"
        };
        token = normalizeTextValue(token || "");
        return aliases[token] || token;
    }

    function canonicalizeCategoryValue(value) {
        var normalized = normalizeTextValue(value || "");
        var aliases = {
            appetizer: "entrada",
            breakfast: "desayuno",
            dessert: "postre",
            dinner: "cena",
            general: "general",
            lunch: "almuerzo",
            merienda: "merienda",
            "main dish": "plato principal",
            "main course": "plato principal",
            potato: "papa",
            salad: "ensalada",
            snack: "merienda",
            soup: "sopa"
        };
        return aliases[normalized] || canonicalizeSemanticToken(normalized) || normalized;
    }

    function canonicalizeDifficultyValue(value) {
        var normalized = normalizeTextValue(value || "");
        var aliases = {
            easy: "facil",
            medium: "media",
            hard: "dificil",
            beginner: "facil",
            intermediate: "media",
            advanced: "dificil"
        };
        return aliases[normalized] || normalized;
    }

    function uniqueTokens(tokens, limit) {
        var seen = {};
        var results = [];
        for (var i = 0; i < tokens.length; i += 1) {
            var token = tokens[i];
            if (!token || seen[token]) {
                continue;
            }
            seen[token] = true;
            results.push(token);
            if (limit && results.length >= limit) {
                break;
            }
        }
        return results;
    }

    function normalizeRecommendationMode(mode) {
        mode = normalizeTextValue(mode || "hybrid");
        if (mode === "type") {
            return "category";
        }
        if (mode !== "hybrid" && mode !== "ingredients" && mode !== "category" && mode !== "title") {
            return "hybrid";
        }
        return mode;
    }

    function isUsefulRecipeToken(token) {
        var blocked = {
            a: true,
            al: true,
            and: true,
            baby: true,
            best: true,
            bite: true,
            bites: true,
            chopped: true,
            con: true,
            cup: true,
            cups: true,
            de: true,
            del: true,
            diced: true,
            dish: true,
            easy: true,
            el: true,
            en: true,
            for: true,
            fresh: true,
            freshly: true,
            fries: true,
            fry: true,
            gram: true,
            grams: true,
            homemade: true,
            kg: true,
            la: true,
            las: true,
            lb: true,
            los: true,
            medium: true,
            minced: true,
            ml: true,
            of: true,
            oil: true,
            optional: true,
            ounce: true,
            ounces: true,
            oz: true,
            papa: true,
            papas: true,
            para: true,
            peeled: true,
            pinch: true,
            por: true,
            potato: true,
            potatoes: true,
            pound: true,
            powder: true,
            quartered: true,
            recipe: true,
            recipes: true,
            shakes: true,
            simple: true,
            sin: true,
            sliced: true,
            small: true,
            spud: true,
            spuds: true,
            style: true,
            taste: true,
            tbsp: true,
            teaspoon: true,
            teaspoons: true,
            the: true,
            to: true,
            tsp: true,
            una: true,
            uno: true,
            unos: true,
            unas: true,
            whole: true,
            with: true,
            y: true,
        };
        return !!token && token.length > 2 && !blocked[token] && !/^\d+$/.test(token);
    }

    function buildIngredientTokenSet(recipe) {
        return new Set(
            uniqueTokens(
                tokenizeText((recipe.ingredients || []).join(" "))
                    .map(canonicalizeSemanticToken)
                    .filter(isUsefulRecipeToken),
                36
            )
        );
    }

    function buildTitleTokenSet(recipe) {
        return new Set(
            uniqueTokens(
                tokenizeText(recipe.title || "")
                    .map(canonicalizeSemanticToken)
                    .filter(isUsefulRecipeToken),
                12
            )
        );
    }

    function isSearchToken(token) {
        var blocked = {
            a: true,
            al: true,
            and: true,
            con: true,
            de: true,
            del: true,
            el: true,
            en: true,
            for: true,
            la: true,
            las: true,
            los: true,
            of: true,
            para: true,
            por: true,
            sin: true,
            the: true,
            to: true,
            una: true,
            uno: true,
            unos: true,
            unas: true,
            with: true,
            y: true,
        };
        return !!token && token.length > 2 && !blocked[token] && !/^\d+$/.test(token);
    }

    function expandSearchTokens(tokens) {
        var expanded = {};
        for (var i = 0; i < tokens.length; i += 1) {
            var token = canonicalizeSemanticToken(tokens[i]);
            if (!token) {
                continue;
            }
            expanded[token] = true;
            if (token.length > 4 && /es$/.test(token)) {
                expanded[token.slice(0, -2)] = true;
            } else if (token.length > 3 && /s$/.test(token)) {
                expanded[token.slice(0, -1)] = true;
            } else {
                expanded[token + "s"] = true;
            }
        }
        return expanded;
    }

    function buildQuerySignals(query) {
        var normalizedQuery = normalizeTextValue(query || "");
        var tokens = tokenizeText(query || "").filter(isSearchToken);
        return {
            rawQuery: String(query || "").trim(),
            normalizedQuery: normalizedQuery,
            queryTerms: expandSearchTokens(tokens),
        };
    }

    function buildRecipeDiscoverySignals(recipe) {
        return {
            normalizedTitle: normalizeTextValue(recipe.title || ""),
            titleTerms: expandSearchTokens(tokenizeText(recipe.title || "").map(canonicalizeSemanticToken).filter(isSearchToken)),
            normalizedIngredients: normalizeTextValue((recipe.ingredients || []).join(" ")),
            ingredientTerms: expandSearchTokens(tokenizeText((recipe.ingredients || []).join(" ")).map(canonicalizeSemanticToken).filter(isSearchToken)),
            normalizedCategory: canonicalizeCategoryValue(recipe.category || ""),
            categoryTerms: expandSearchTokens(tokenizeText(canonicalizeCategoryValue(recipe.category || "")).filter(isSearchToken)),
        };
    }

    function countSharedTerms(queryTerms, candidateTerms) {
        var total = 0;
        var seen = {};
        for (var term in queryTerms) {
            if (!Object.prototype.hasOwnProperty.call(queryTerms, term) || !queryTerms[term]) {
                continue;
            }
            if (candidateTerms[term] && !seen[term]) {
                total += 1;
                seen[term] = true;
            }
        }
        return total;
    }

    function scoreRecipeForQuery(query, recipe, mode) {
        var querySignals = buildQuerySignals(query);
        var recipeSignals = buildRecipeDiscoverySignals(recipe);
        var titleHits = countSharedTerms(querySignals.queryTerms, recipeSignals.titleTerms);
        var ingredientHits = countSharedTerms(querySignals.queryTerms, recipeSignals.ingredientTerms);
        var categoryHits = countSharedTerms(querySignals.queryTerms, recipeSignals.categoryTerms);
        var exactTitle = !!querySignals.normalizedQuery && recipeSignals.normalizedTitle.indexOf(querySignals.normalizedQuery) !== -1;
        var exactIngredients = !!querySignals.normalizedQuery && recipeSignals.normalizedIngredients.indexOf(querySignals.normalizedQuery) !== -1;
        var exactCategory = !!querySignals.normalizedQuery && recipeSignals.normalizedCategory.indexOf(querySignals.normalizedQuery) !== -1;
        var matched = false;
        var score = 0;

        if (mode === "ingredients") {
            score = (ingredientHits * 3) + (exactIngredients ? 4 : 0) + (titleHits * 0.55) + (categoryHits * 0.9);
            matched = ingredientHits > 0 || exactIngredients;
        } else if (mode === "category") {
            score = (categoryHits * 4.5) + (exactCategory ? 4 : 0) + (titleHits * 1) + (ingredientHits * 1);
            matched = categoryHits > 0 || exactCategory;
        } else if (mode === "title") {
            score = (titleHits * 3.5) + (exactTitle ? 4 : 0) + (ingredientHits * 0.5) + (categoryHits * 0.75);
            matched = titleHits > 0 || exactTitle;
        } else {
            score = (titleHits * 2) + (ingredientHits * 2.2) + (categoryHits * 2.8) +
                (exactTitle ? 3 : 0) + (exactIngredients ? 2.5 : 0) + (exactCategory ? 2 : 0);
            matched = titleHits > 0 || ingredientHits > 0 || categoryHits > 0 || exactTitle || exactIngredients || exactCategory;
        }

        score += Number(recipe.score || 0) * 0.06;
        return {
            matched: matched,
            score: score,
            sharedTitleTerms: titleHits,
            sharedIngredients: ingredientHits,
            sameCategory: categoryHits > 0 || exactCategory,
        };
    }

    function discoverLocalRecommendations(query, limit, mode) {
        limit = Math.max(Number(limit) || 6, 1);
        mode = normalizeRecommendationMode(mode);
        var normalizedQuery = String(query || "").trim();
        if (!normalizedQuery) {
            return [];
        }

        var scored = [];
        for (var i = 0; i < catalogRecipes.length; i += 1) {
            var recipe = catalogRecipes[i];
            var result = scoreRecipeForQuery(normalizedQuery, recipe, mode);
            if (!result.matched || result.score <= 0) {
                continue;
            }
            scored.push({ score: result.score, recipe: recipe });
        }

        scored.sort(function (a, b) {
            if (b.score !== a.score) {
                return b.score - a.score;
            }
            return String(a.recipe.title || "").localeCompare(String(b.recipe.title || ""));
        });

        return scored.slice(0, limit).map(function (item) {
            return item.recipe;
        });
    }

    function computeLocalRelevance(recipe, query, tokens) {
        if (!query || query === "*") {
            return Number(recipe.score || 0);
        }

        var haystack = normalizeTextValue(
            [
                recipe.title,
                recipe.description,
                recipe.category,
                recipe.difficulty,
                recipe.source_name,
                (recipe.ingredients || []).join(" "),
                (recipe.instructions || []).join(" "),
                (recipe.tags || []).join(" "),
            ].join(" ")
        );

        var normalizedQuery = normalizeTextValue(query);
        var score = 0;

        if (normalizedQuery && haystack.indexOf(normalizedQuery) !== -1) {
            score += 5;
        }

        for (var i = 0; i < tokens.length; i += 1) {
            if (haystack.indexOf(tokens[i]) !== -1) {
                score += 1;
            }
        }

        score += Number(recipe.score || 0) * 0.05;
        return score;
    }

    function searchLocalCatalog(query, category, difficulty, page, size) {
        query = query == null ? "*" : String(query);
        category = canonicalizeCategoryValue(category);
        difficulty = canonicalizeDifficultyValue(difficulty);
        page = Math.max(Number(page) || 0, 0);
        size = Math.max(Number(size) || DEFAULT_PAGE_SIZE, 1);

        var tokens = tokenizeText(query);
        var matches = [];

        for (var i = 0; i < catalogRecipes.length; i += 1) {
            var recipe = catalogRecipes[i];
            if (category && canonicalizeCategoryValue(recipe.category) !== category) {
                continue;
            }
            if (difficulty && canonicalizeDifficultyValue(recipe.difficulty) !== difficulty) {
                continue;
            }

            var relevance = computeLocalRelevance(recipe, query, tokens);
            if (query !== "" && query !== "*" && relevance <= 0) {
                continue;
            }
            matches.push({ relevance: relevance, score: Number(recipe.score || 0), updated_at: recipe.updated_at, recipe: recipe });
        }

        matches.sort(function (a, b) {
            if (b.relevance !== a.relevance) {
                return b.relevance - a.relevance;
            }
            if (b.score !== a.score) {
                return b.score - a.score;
            }
            return String(a.recipe.title || "").localeCompare(String(b.recipe.title || ""));
        });

        var total = matches.length;
        var start = page * size;
        var end = start + size;
        return {
            total: total,
            results: matches.slice(start, end).map(function (item) {
                return item.recipe;
            }),
        };
    }

    function rankingLocalCatalog(limit) {
        limit = Math.max(Number(limit) || 10, 1);
        var items = catalogRecipes.slice();
        items.sort(function (a, b) {
            var scoreA = Number(a.score || 0);
            var scoreB = Number(b.score || 0);
            if (scoreB !== scoreA) {
                return scoreB - scoreA;
            }
            var savedA = a.stats && a.stats.saved ? Number(a.stats.saved) : 0;
            var savedB = b.stats && b.stats.saved ? Number(b.stats.saved) : 0;
            if (savedB !== savedA) {
                return savedB - savedA;
            }
            var cookedA = a.stats && a.stats.cooked ? Number(a.stats.cooked) : 0;
            var cookedB = b.stats && b.stats.cooked ? Number(b.stats.cooked) : 0;
            if (cookedB !== cookedA) {
                return cookedB - cookedA;
            }
            var viewsA = a.stats && a.stats.views ? Number(a.stats.views) : 0;
            var viewsB = b.stats && b.stats.views ? Number(b.stats.views) : 0;
            if (viewsB !== viewsA) {
                return viewsB - viewsA;
            }
            return String(a.title || "").localeCompare(String(b.title || ""));
        });
        return items.slice(0, limit);
    }

    function recommendLocalCatalog(recipeId, limit, mode) {
        var anchor = getRecipeById(recipeId);
        if (!anchor) {
            return [];
        }

        limit = Math.max(Number(limit) || 6, 1);
        mode = normalizeRecommendationMode(mode);

        var anchorIngredients = buildIngredientTokenSet(anchor);
        var anchorTags = new Set(tokenizeText((anchor.tags || []).join(" ")));
        var anchorTitle = buildTitleTokenSet(anchor);
        var anchorCategory = canonicalizeCategoryValue(anchor.category);
        var anchorDifficulty = canonicalizeDifficultyValue(anchor.difficulty);
        var scored = [];

        for (var i = 0; i < catalogRecipes.length; i += 1) {
            var candidate = catalogRecipes[i];
            if (candidate.id === recipeId) {
                continue;
            }

            var candidateIngredients = buildIngredientTokenSet(candidate);
            var candidateTags = new Set(tokenizeText((candidate.tags || []).join(" ")));
            var candidateTitle = buildTitleTokenSet(candidate);
            var sharedIngredients = 0;
            anchorIngredients.forEach(function (item) {
                if (candidateIngredients.has(item)) {
                    sharedIngredients += 1;
                }
            });
            var sharedTags = 0;
            anchorTags.forEach(function (item) {
                if (candidateTags.has(item)) {
                    sharedTags += 1;
                }
            });
            var sharedTitle = 0;
            anchorTitle.forEach(function (item) {
                if (candidateTitle.has(item)) {
                    sharedTitle += 1;
                }
            });
            var sameCategory = anchorCategory && canonicalizeCategoryValue(candidate.category) === anchorCategory;
            var sameDifficulty = anchorDifficulty && canonicalizeDifficultyValue(candidate.difficulty) === anchorDifficulty;

            if (mode === "ingredients" && sharedIngredients <= 0) {
                continue;
            }
            if (mode === "category" && !sameCategory) {
                continue;
            }
            if (mode === "title" && sharedTitle <= 0) {
                continue;
            }
            if (mode === "hybrid" && sharedIngredients <= 0 && sharedTitle <= 0 && !sameCategory) {
                continue;
            }

            var score = 0;
            if (mode === "ingredients") {
                score += sharedIngredients * 3;
                score += sharedTags * 0.75;
                score += sharedTitle * 0.55;
                score += sameCategory ? 0.9 : 0;
                score += sameDifficulty ? 0.2 : 0;
            } else if (mode === "category") {
                score += sameCategory ? 4.5 : 0;
                score += sharedIngredients * 1.2;
                score += sharedTags * 0.75;
                score += sharedTitle * 1;
                score += sameDifficulty ? 0.4 : 0;
            } else if (mode === "title") {
                score += sharedTitle * 3.5;
                score += sharedIngredients * 1;
                score += sharedTags * 0.5;
                score += sameCategory ? 1.5 : 0;
                score += sameDifficulty ? 0.2 : 0;
            } else {
                score += sharedIngredients * 2.2;
                score += sharedTags * 1;
                score += sharedTitle * 1.8;
                score += sameCategory ? 2.8 : 0;
                score += sameDifficulty ? 0.4 : 0;
            }

            score += Number(candidate.score || 0) * 0.1;
            scored.push({ score: score, updated_at: candidate.updated_at, recipe: candidate });
        }

        scored.sort(function (a, b) {
            if (b.score !== a.score) {
                return b.score - a.score;
            }
            return String(a.recipe.title || "").localeCompare(String(b.recipe.title || ""));
        });

        return scored.slice(0, limit).map(function (item) {
            return item.recipe;
        });
    }

    function buildFilterOptions(recipes) {
        recipes = Array.isArray(recipes) ? recipes : catalogRecipes;
        var categoryCounts = {};
        var difficultyCounts = {};
        var sourceCounts = {};

        recipes.forEach(function (recipe) {
            var category = canonicalizeCategoryValue(String(recipe.category || "").trim());
            var difficulty = canonicalizeDifficultyValue(String(recipe.difficulty || "").trim());
            var source = String(recipe.source_name || "").trim();

            if (category) {
                categoryCounts[category] = (categoryCounts[category] || 0) + 1;
            }
            if (difficulty) {
                difficultyCounts[difficulty] = (difficultyCounts[difficulty] || 0) + 1;
            }
            if (source) {
                sourceCounts[source] = (sourceCounts[source] || 0) + 1;
            }
        });

        var categories = Object.keys(categoryCounts)
            .sort(function (a, b) {
                return categoryCounts[b] - categoryCounts[a] || String(a).localeCompare(String(b));
            })
            .map(function (value) {
                return { value: value, label: formatCategoryLabel(value), count: categoryCounts[value] };
            });

        var difficulties = Object.keys(difficultyCounts)
            .sort(function (a, b) {
                var order = { easy: 0, medium: 1, hard: 2 };
                if (order[a] !== order[b]) {
                    var rankA = typeof order[a] === "number" ? order[a] : 99;
                    var rankB = typeof order[b] === "number" ? order[b] : 99;
                    return rankA - rankB;
                }
                return difficultyCounts[b] - difficultyCounts[a] || String(a).localeCompare(String(b));
            })
            .map(function (value) {
                return { value: value, label: formatDifficultyLabel(value), count: difficultyCounts[value] };
            });

        var sources = Object.keys(sourceCounts)
            .sort(function (a, b) {
                return sourceCounts[b] - sourceCounts[a] || String(a).localeCompare(String(b));
            })
            .map(function (value) {
                return { value: value, label: value.charAt(0).toUpperCase() + value.slice(1), count: sourceCounts[value] };
            });

        return {
            categories: categories,
            difficulties: difficulties,
            sources: sources,
        };
    }

    function normalizeRemoteFilterOptions(payload) {
        if (!payload || typeof payload !== "object") {
            return null;
        }

        function toOptionList(items, formatter) {
            return (Array.isArray(items) ? items : []).map(function (item) {
                if (typeof item === "string") {
                    return formatter({ value: item, label: item, count: 0 });
                }
                if (!item || typeof item !== "object") {
                    return null;
                }
                var value = String(item.value || item.name || item.label || "").trim();
                if (!value) {
                    return null;
                }
                return formatter({
                    value: value,
                    label: String(item.label || item.value || item.name || value),
                    count: typeof item.count === "number" ? item.count : 0,
                });
            }).filter(Boolean);
        }

        return {
            categories: toOptionList(payload.categories, function (item) {
                item.label = formatCategoryLabel(item.label || item.value || "");
                return item;
            }),
            difficulties: toOptionList(payload.difficulties, function (item) {
                item.label = formatDifficultyLabel(item.label || item.value || "");
                return item;
            }),
            sources: toOptionList(payload.sources, function (item) {
                return item;
            }),
        };
    }

    function loadDemoCatalog() {
        setCatalogRecipes(DEMO_RECIPES, "demo");
    }

    function updateCatalogModeText() {
        if (catalogModeBadge) {
            if (catalogMode === "live") {
                catalogModeBadge.textContent = "Catálogo en vivo";
                catalogModeBadge.className = "inline-status success";
            } else if (catalogMode === "demo") {
                catalogModeBadge.textContent = "Catálogo demo";
                catalogModeBadge.className = "inline-status warning";
            } else if (catalogMode === "loading") {
                catalogModeBadge.textContent = "Cargando catálogo";
                catalogModeBadge.className = "inline-status idle";
            }
        }
    }

    function normalizeCatalogText(text) {
        return normalizeTextValue(text).replace(/\s+/g, " ").trim();
    }

    var DEMO_RECIPES = [
        buildRecipe(
            {
                id: "demo-potato-garden-pan",
                title: "Sartén de papas con hierbas",
                description: "Papas doradas, hierbas frescas y un toque de limón. Rápida, colorida y fácil de probar de punta a punta.",
                category: "Papa",
                difficulty: "facil",
                cooking_time: 25,
                ingredients: ["3 papas", "2 cucharadas de aceite de oliva", "1 cucharadita de sal", "1 cucharadita de pimentón", "1 cucharada de perejil"],
                instructions: ["Corta las papas en cubos.", "Fríelas en la sartén hasta dorar.", "Sazona con pimentón y sal.", "Termina con perejil y limón."],
                tags: ["sartén", "rápida", "hierbas"],
                stats: { views: 18, saved: 4 },
                score: 24,
            },
            0
        ),
        buildRecipe(
            {
                id: "demo-cheesy-potato-bites",
                title: "Bocaditos de papa con queso",
                description: "Crujientes por fuera, suaves por dentro, con un centro cremoso ideal para verificar la tarjeta.",
                category: "Merienda",
                difficulty: "media",
                cooking_time: 35,
                ingredients: ["4 papas", "1 taza de queso rallado", "1 huevo", "2 cucharadas de harina", "sal"],
                instructions: ["Haz puré con las papas.", "Mezcla con el queso y el huevo.", "Forma bocaditos pequeños.", "Hornea hasta que queden crujientes."],
                tags: ["reunión", "horneado", "queso"],
                stats: { views: 12, saved: 5 },
                score: 29,
            },
            1
        ),
        buildRecipe(
            {
                id: "demo-creamy-potato-soup",
                title: "Sopa cremosa de papa",
                description: "Un tazón reconfortante con textura suave, ideal para revisar clasificación y recomendaciones.",
                category: "Sopa",
                difficulty: "facil",
                cooking_time: 40,
                ingredients: ["5 papas", "1 cebolla", "2 tazas de caldo de verduras", "1/2 taza de crema", "sal y pimienta"],
                instructions: ["Sofríe la cebolla.", "Agrega las papas y el caldo.", "Cocina a fuego lento hasta que ablanden.", "Licúa y termina con crema."],
                tags: ["confort", "licuado", "invierno"],
                stats: { views: 24, saved: 9 },
                score: 42,
            },
            2
        ),
        buildRecipe(
            {
                id: "demo-roasted-potato-salad",
                title: "Ensalada de papa asada",
                description: "Una ensalada fresca con aderezo de mostaza, hierbas frescas y una vista limpia para la interfaz.",
                category: "Ensalada",
                difficulty: "media",
                cooking_time: 30,
                ingredients: ["4 papas", "1 pepino", "2 cucharadas de mostaza", "1 cucharada de vinagre", "hierbas"],
                instructions: ["Hornea las papas.", "Mezcla el aderezo.", "Combina todo mientras esté tibio.", "Sirve con hierbas."],
                tags: ["fresca", "acompañamiento", "mostaza"],
                stats: { views: 14, saved: 3 },
                score: 21,
            },
            3
        ),
        buildRecipe(
            {
                id: "demo-potato-breakfast-hash",
                title: "Desayuno de papa en sartén",
                description: "Papas, huevos y pimientos en una sola sartén. Ideal para probar filtros e interacciones rápidas.",
                category: "Desayuno",
                difficulty: "facil",
                cooking_time: 20,
                ingredients: ["3 papas", "2 huevos", "1 pimiento", "1 cebolla", "aceite"],
                instructions: ["Cocina las papas.", "Agrega la cebolla y el pimiento.", "Añade los huevos.", "Sirve de inmediato."],
                tags: ["brunch", "una sartén", "salado"],
                stats: { views: 31, saved: 12 },
                score: 51,
            },
            4
        ),
        buildRecipe(
            {
                id: "demo-loaded-potato-main",
                title: "Plato fuerte de papa cargada",
                description: "Un plato más contundente con sazón ahumada, crema agria y un tono más intenso para las tarjetas.",
                category: "Plato principal",
                difficulty: "dificil",
                cooking_time: 55,
                ingredients: ["4 papas", "1 taza de crema agria", "1 taza de queso", "cebollín", "pimentón ahumado"],
                instructions: ["Hornea las papas.", "Ábrelas y esponja el centro.", "Agrega crema agria y queso.", "Termina con cebollín."],
                tags: ["contundente", "horno", "cena"],
                stats: { views: 22, saved: 8 },
                score: 39,
            },
            5
        ),
        buildRecipe(
            {
                id: "demo-potato-dessert-cakes",
                title: "Mini tortas de camote",
                description: "Una receta dulce y suave para verificar contraste, detalle en modal y estados de clasificación.",
                category: "Postre",
                difficulty: "media",
                cooking_time: 45,
                ingredients: ["2 camotes", "1/2 taza de azúcar", "1 taza de harina", "2 huevos", "canela"],
                instructions: ["Cocina y aplasta los camotes.", "Mezcla con el resto de la masa.", "Distribuye en moldes.", "Hornea hasta que cuaje."],
                tags: ["dulce", "horneado", "canela"],
                stats: { views: 11, saved: 2 },
                score: 17,
            },
            6
        ),
    ];

    function readJsonStorage(key) {
        try {
            var raw = window.localStorage.getItem(key);
            if (!raw) {
                return null;
            }
            return JSON.parse(raw);
        } catch (error) {
            return null;
        }
    }

    function writeJsonStorage(key, value) {
        try {
            if (value == null) {
                window.localStorage.removeItem(key);
            } else {
                window.localStorage.setItem(key, JSON.stringify(value));
            }
        } catch (error) {
            // Ignore storage failures in private mode / restricted browsers.
        }
    }

    function loadStoredPreferences() {
        var settings = readJsonStorage(UI_STORAGE_KEY) || {};
        var preferredPageSize = Number(settings.pageSize || DEFAULT_PAGE_SIZE);
        if ([6, 12, 24].indexOf(preferredPageSize) === -1) {
            preferredPageSize = DEFAULT_PAGE_SIZE;
        }
        state.pageSize = preferredPageSize;
        if (pageSizeSelect) {
            pageSizeSelect.value = String(preferredPageSize);
        }
    }

    function savePreferences() {
        writeJsonStorage(UI_STORAGE_KEY, {
            pageSize: state.pageSize,
        });
    }

    function getPageSize() {
        var selected = Number(pageSizeSelect && pageSizeSelect.value ? pageSizeSelect.value : state.pageSize);
        if ([6, 12, 24].indexOf(selected) === -1) {
            selected = DEFAULT_PAGE_SIZE;
        }
        return selected;
    }

    function setPageSize(pageSize) {
        var value = Number(pageSize) || DEFAULT_PAGE_SIZE;
        if ([6, 12, 24].indexOf(value) === -1) {
            value = DEFAULT_PAGE_SIZE;
        }
        state.pageSize = value;
        if (pageSizeSelect) {
            pageSizeSelect.value = String(value);
        }
        savePreferences();
    }

    function loadStoredAuth() {
        var session = readJsonStorage(AUTH_STORAGE_KEY);
        if (!session || !session.token) {
            return;
        }
        authState.token = String(session.token);
        authState.user = session.user || null;
    }

    function saveAuthState() {
        if (!authState.token || !authState.user) {
            writeJsonStorage(AUTH_STORAGE_KEY, null);
            return;
        }
        writeJsonStorage(AUTH_STORAGE_KEY, {
            token: authState.token,
            user: authState.user,
        });
    }

    function clearAuthState() {
        authState.token = "";
        authState.user = null;
        saveAuthState();
        renderAuthState();
    }

    function authHeaders() {
        var headers = {};
        if (authState.token) {
            headers.Authorization = "Bearer " + authState.token;
        }
        return headers;
    }

    function currentUserId() {
        return authState.user && authState.user.id ? String(authState.user.id) : "";
    }

    function setAuthStatus(message, kind) {
        if (!authStatus) {
            return;
        }
        authStatus.textContent = message || "";
        authStatus.className = "inline-status" + (kind ? " " + kind : "");
    }

    function setAuthModalMode(mode) {
        var activeMode = mode === "register" ? "register" : "login";

        authTabButtons.forEach(function (button) {
            button.classList.toggle("active", button.dataset.authTab === activeMode);
        });

        if (loginForm) {
            loginForm.classList.toggle("active", activeMode === "login");
        }
        if (registerForm) {
            registerForm.classList.toggle("active", activeMode === "register");
        }
        if (authModalTitle) {
            authModalTitle.textContent = activeMode === "register" ? "Crear cuenta" : "Iniciar sesión";
        }
    }

    function openAuthModal(mode) {
        if (!authModal) {
            return;
        }
        setAuthStatus("", "idle");
        setAuthModalMode(mode || "login");
        authModal.hidden = false;
        authModal.classList.add("is-open");
        authModal.style.display = "grid";
        authModal.setAttribute("aria-hidden", "false");
        document.body.classList.add("modal-open");
    }

    function closeAuthModal() {
        if (!authModal) {
            return;
        }
        authModal.hidden = true;
        authModal.classList.remove("is-open");
        authModal.style.display = "none";
        authModal.setAttribute("aria-hidden", "true");
        document.body.classList.remove("modal-open");
    }

    function renderAuthState() {
        if (!authBtn || !userChip || !logoutBtn) {
            return;
        }

        var isLoggedIn = Boolean(authState.user && authState.token);
        authBtn.hidden = isLoggedIn;
        userChip.hidden = !isLoggedIn;
        logoutBtn.hidden = !isLoggedIn;
        authBtn.style.display = isLoggedIn ? "none" : "";
        userChip.style.display = isLoggedIn ? "inline-flex" : "none";
        logoutBtn.style.display = isLoggedIn ? "" : "none";

        if (isLoggedIn) {
            var userName = authState.user.name || authState.user.email || "Usuario";
            userChip.textContent = userName;
            userChip.title = authState.user.email || userName;
        } else {
            userChip.textContent = "";
            userChip.title = "";
        }
    }

    async function restoreAuthSession() {
        loadStoredAuth();
        renderAuthState();

        if (!authState.token) {
            return;
        }

        try {
            var response = await fetch(API_BASE + "/auth/me", {
                headers: authHeaders(),
            });
            if (!response.ok) {
                throw new Error("session invalid");
            }
            applyAuthSession({
                token: authState.token,
                user: await response.json(),
            });
        } catch (error) {
            clearAuthState();
        }
    }

    function applyAuthSession(session) {
        authState.token = String(session && session.token ? session.token : "");
        authState.user = session && session.user ? session.user : null;
        saveAuthState();
        renderAuthState();
    }

    async function sendAuthRequest(path, payload) {
        var response = await fetch(API_BASE + "/auth/" + path, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(payload),
        });
        var data = await response.json().catch(function () {
            return {};
        });
        if (!response.ok) {
            throw new Error((data && data.detail) || "Auth request failed");
        }
        return data;
    }

    async function submitLoginForm(event) {
        event.preventDefault();
        if (!loginEmail || !loginPassword) {
            return;
        }

        setAuthStatus("Ingresando...", "loading");
        try {
            var session = await sendAuthRequest("login", {
                email: loginEmail.value,
                password: loginPassword.value,
            });
            applyAuthSession(session);
            setAuthStatus("Sesión iniciada como " + (session.user && session.user.name ? session.user.name : "usuario"), "success");
            closeAuthModal();
            setStatusMessage("Sesión iniciada correctamente", "success");
        } catch (error) {
            setAuthStatus(error.message || "No se pudo iniciar sesión", "error");
        }
    }

    async function submitRegisterForm(event) {
        event.preventDefault();
        if (!registerName || !registerEmail || !registerPassword) {
            return;
        }

        setAuthStatus("Creando cuenta...", "loading");
        try {
            var session = await sendAuthRequest("register", {
                name: registerName.value,
                email: registerEmail.value,
                password: registerPassword.value,
            });
            applyAuthSession(session);
            setAuthStatus("Cuenta creada y sesión activa", "success");
            closeAuthModal();
            setStatusMessage("Cuenta creada correctamente", "success");
        } catch (error) {
            setAuthStatus(error.message || "No se pudo crear la cuenta", "error");
        }
    }

    function logoutUser() {
        clearAuthState();
        setAuthStatus("Sesión cerrada", "warning");
        closeAuthModal();
        setStatusMessage("Sesión cerrada", "warning");
    }

    function createFallbackImageData(recipe, label) {
        var tone = getRecipeTone(recipe);
        var palette = {
            potato: ["#a96d1f", "#f1cf74", "#fff8e2"],
            soup: ["#2c6f61", "#8fd6c5", "#f1fbf8"],
            salad: ["#4f8f59", "#b6dea9", "#f2fbec"],
            breakfast: ["#b76439", "#f1b079", "#fff4ea"],
            main: ["#7c5434", "#d8b082", "#fbf3e8"],
            snack: ["#8c5c2b", "#e4c37e", "#fff6e5"],
            dessert: ["#ae6b56", "#efc1ae", "#fff4ef"],
            neutral: ["#6d7b88", "#d2dae3", "#f5f8fb"],
        };
        var colors = palette[tone] || palette.neutral;
        var safeTitle = escapeHtml(truncateText(recipe && recipe.title ? recipe.title : label || "PotatoHub", 36));
        var safeCategory = escapeHtml(formatCategoryLabel(recipe && recipe.category ? recipe.category : "General"));
        var svg = [
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 520" role="img" aria-label="' + safeTitle + '">',
            "<defs>",
            '<linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">',
            '<stop offset="0%" stop-color="' + colors[0] + '"/>',
            '<stop offset="58%" stop-color="' + colors[1] + '"/>',
            '<stop offset="100%" stop-color="' + colors[2] + '"/>',
            "</linearGradient>",
            "</defs>",
            '<rect width="800" height="520" fill="url(#g)"/>',
            '<circle cx="642" cy="104" r="122" fill="#ffffff" opacity="0.26"/>',
            '<circle cx="104" cy="412" r="160" fill="#ffffff" opacity="0.18"/>',
            '<text x="56" y="90" fill="#ffffff" fill-opacity="0.92" font-family="Georgia, serif" font-size="26" font-weight="700" letter-spacing="4">POTATOHUB</text>',
            '<text x="56" y="230" fill="#18212d" fill-opacity="0.9" font-family="Georgia, serif" font-size="42" font-weight="700">' + safeTitle + "</text>",
            '<text x="56" y="286" fill="#18212d" fill-opacity="0.74" font-family="Trebuchet MS, sans-serif" font-size="22" font-weight="600">' + safeCategory + "</text>",
            "</svg>",
        ].join("");
        return "data:image/svg+xml;charset=UTF-8," + encodeURIComponent(svg);
    }

    function renderRecipeImage(recipe, className, altText) {
        var fallback = createFallbackImageData(recipe, altText);
        var imageUrl = recipe && recipe.image_url ? String(recipe.image_url).trim() : "";
        if (!imageUrl) {
            imageUrl = fallback;
        }
        return [
            '<img class="' + className + '"',
            ' src="' + escapeHtml(imageUrl) + '"',
            ' alt="' + escapeHtml(altText || recipe.title || "Receta") + '"',
            ' loading="lazy" decoding="async" referrerpolicy="no-referrer"',
            ' data-fallback="' + escapeHtml(fallback) + '"',
            ' onerror="this.onerror=null;if(this.dataset.fallback&&this.src!==this.dataset.fallback){this.src=this.dataset.fallback;}"',
            ">",
        ].join("");
    }

    function storeRecipe(recipe) {
        if (recipe && recipe.id) {
            recipeCache[recipe.id] = recipe;
        }
    }

    function syncRecipeCardStats(recipeId, data) {
        var cards = Array.prototype.slice.call(document.querySelectorAll(".recipe-card"));
        var card = null;
        for (var i = 0; i < cards.length; i += 1) {
            if (cards[i].dataset.id === recipeId) {
                card = cards[i];
                break;
            }
        }
        if (!card) {
            return;
        }
        var views = card.querySelector('[data-field="views"]');
        var saved = card.querySelector('[data-field="saved"]');
        var cooked = card.querySelector('[data-field="cooked"]');
        var score = card.querySelector('[data-field="score"]');
        if (views) {
            views.textContent = "Vistas: " + data.views;
        }
        if (saved) {
            saved.textContent = "Guardadas: " + data.saved;
        }
        if (cooked) {
            cooked.textContent = "Cocinadas: " + (data.cooked || 0);
        }
        if (score) {
            score.textContent = "Puntuación: " + data.score;
        }
    }

    function syncRecipeModalStats(recipeId, data) {
        if (!recipeModal || recipeModal.hidden || currentRecipeId !== recipeId) {
            return;
        }
        var views = recipeModal.querySelector('[data-detail-field="views"]');
        var saved = recipeModal.querySelector('[data-detail-field="saved"]');
        var cooked = recipeModal.querySelector('[data-detail-field="cooked"]');
        var score = recipeModal.querySelector('[data-detail-field="score"]');
        if (views) {
            views.textContent = "Vistas: " + data.views;
        }
        if (saved) {
            saved.textContent = "Guardadas: " + data.saved;
        }
        if (cooked) {
            cooked.textContent = "Cocinadas: " + (data.cooked || 0);
        }
        if (score) {
            score.textContent = "Puntuación: " + data.score;
        }
    }

    function closeRecipeModal() {
        if (!recipeModal) {
            return;
        }
        recipeModal.hidden = true;
        recipeModal.classList.remove("is-open");
        recipeModal.style.display = "none";
        recipeModal.setAttribute("aria-hidden", "true");
        document.body.classList.remove("modal-open");
        currentRecipeId = "";
    }

    function renderRecipeDetail(recipe) {
        var title = escapeHtml(recipe.title || "Receta sin título");
        var description = escapeHtml(recipe.description || "No hay descripción disponible.");
        var category = escapeHtml(formatCategoryLabel(recipe.category || "General"));
        var difficulty = escapeHtml(formatDifficultyLabel(recipe.difficulty || "n/d"));
        var cookingTime = recipe.cooking_time || 0;
        var ingredientCount = Array.isArray(recipe.ingredients) ? recipe.ingredients.length : 0;
        var instructionCount = Array.isArray(recipe.instructions) ? recipe.instructions.length : 0;
        var views = recipe.stats && recipe.stats.views ? recipe.stats.views : 0;
        var saved = recipe.stats && recipe.stats.saved ? recipe.stats.saved : 0;
        var cooked = recipe.stats && recipe.stats.cooked ? recipe.stats.cooked : 0;
        var score = recipe.score != null ? recipe.score : 0;
        var sourceName = escapeHtml(recipe.source_name || "demo");
        var sourceUrl = recipe.source_url ? escapeHtml(recipe.source_url) : "";
        var ingredients = Array.isArray(recipe.ingredients) ? recipe.ingredients : [];
        var instructions = Array.isArray(recipe.instructions) ? recipe.instructions : [];
        var tags = Array.isArray(recipe.tags) ? recipe.tags : [];
        var tone = getRecipeTone(recipe);
        var visual = renderRecipeImage(recipe, "recipe-detail-image", recipe.title || "Receta");

        return [
            '<article class="recipe-detail" data-tone="' + escapeHtml(tone) + '">',
            '<div class="recipe-detail-hero">',
            '<div class="recipe-detail-visual">' + visual + "</div>",
            '<div class="recipe-detail-summary">',
            '<div class="recipe-detail-pills">',
            '<span class="source-pill soft">' + sourceName + "</span>",
            '<span class="tag">' + category + "</span>",
            '<span class="tag">' + difficulty + "</span>",
            "</div>",
            '<h3 class="recipe-detail-title">' + title + "</h3>",
            '<p class="recipe-detail-description">' + description + "</p>",
            '<div class="recipe-detail-meta">',
            '<span data-detail-field="time">' + formatTime(cookingTime) + "</span>",
            '<span data-detail-field="views">Vistas: ' + views + "</span>",
            '<span data-detail-field="saved">Guardadas: ' + saved + "</span>",
            '<span data-detail-field="cooked">Cocinadas: ' + cooked + "</span>",
            '<span data-detail-field="score">Puntuación: ' + score + "</span>",
            '<span>' + formatCount(ingredientCount, "ingrediente", "ingredientes") + "</span>",
            '<span>' + formatCount(instructionCount, "paso", "pasos") + "</span>",
            "</div>",
            '<div class="recipe-detail-actions">',
            '<button class="action-btn" type="button" onclick="interact(\'' + escapeJs(recipe.id) + '\', \'save\')">Guardar</button>',
            '<button class="action-btn" type="button" onclick="interact(\'' + escapeJs(recipe.id) + '\', \'cook\')">Cocinada</button>',
            '<button class="action-btn secondary" type="button" onclick="getRecommendations(\'' + escapeJs(recipe.id) + '\')">Similares</button>',
            sourceUrl
                ? '<a class="action-link" href="' + sourceUrl + '" target="_blank" rel="noopener">Abrir fuente</a>'
                : "",
            "</div>",
            "</div>",
            "</div>",
            '<div class="recipe-detail-grid">',
            '<section class="recipe-detail-block">',
            "<h3>Ingredientes</h3>",
            ingredients.length
                ? '<ul class="detail-list">' + ingredients.map(function (item) {
                      return "<li>" + escapeHtml(item) + "</li>";
                  }).join("") + "</ul>"
                : '<p class="muted">No hay ingredientes disponibles.</p>',
            "</section>",
            '<section class="recipe-detail-block">',
            "<h3>Instrucciones</h3>",
            instructions.length
                ? '<ol class="detail-list ordered">' + instructions.map(function (item) {
                      return "<li>" + escapeHtml(item) + "</li>";
                  }).join("") + "</ol>"
                : '<p class="muted">No hay instrucciones disponibles.</p>',
            "</section>",
            "</div>",
            tags.length
                ? '<div class="recipe-detail-footer"><div class="source-tags">' + tags.map(function (item) {
                      return '<span class="tag soft">' + escapeHtml(item) + "</span>";
                  }).join("") + "</div></div>"
                : "",
            "</article>",
        ].join("");
    }

    function showRecipeModal(recipe) {
        if (!recipeModal || !recipeModalBody || !recipeModalTitle) {
            return;
        }
        currentRecipeId = recipe.id;
        recipeModalTitle.textContent = recipe.title || "Receta";
        recipeModalBody.innerHTML = renderRecipeDetail(recipe);
        recipeModal.hidden = false;
        recipeModal.classList.add("is-open");
        recipeModal.style.display = "grid";
        recipeModal.setAttribute("aria-hidden", "false");
        document.body.classList.add("modal-open");
    }

    async function openRecipe(recipeId) {
        if (!recipeId) {
            return;
        }

        var recipe = recipeCache[recipeId];
        var needsFetch =
            !recipe ||
            !Array.isArray(recipe.ingredients) ||
            !recipe.ingredients.length ||
            !Array.isArray(recipe.instructions) ||
            !recipe.instructions.length;

        if (needsFetch) {
            try {
                if (recipeModal && recipeModalBody && recipeModalTitle) {
                    recipeModalTitle.textContent = "Receta";
                    recipeModalBody.innerHTML = '<div class="loading-state">Cargando receta...</div>';
                    recipeModal.hidden = false;
                    recipeModal.classList.add("is-open");
                    recipeModal.style.display = "grid";
                    recipeModal.setAttribute("aria-hidden", "false");
                    document.body.classList.add("modal-open");
                }
                var response = await fetch(API_BASE + "/recipes/" + encodeURIComponent(recipeId));
                if (!response.ok) {
                    throw new Error("recipe not found");
                }
                recipe = await response.json();
                storeRecipe(recipe);
            } catch (error) {
                console.error("Recipe detail error:", error);
                if (recipeModal && recipeModalBody && recipeModalTitle) {
                    recipeModalTitle.textContent = "Receta no disponible";
                    recipeModalBody.innerHTML = '<div class="error-state">No se pudieron cargar los detalles de la receta.</div>';
                    recipeModal.hidden = false;
                    recipeModal.classList.add("is-open");
                    recipeModal.style.display = "grid";
                    recipeModal.setAttribute("aria-hidden", "false");
                    document.body.classList.add("modal-open");
                }
                return;
            }
        }

        showRecipeModal(recipe);

        try {
            await interact(recipeId, "view");
        } catch (error) {
            console.warn("View tracking failed:", error);
        }
    }

    function populateSelect(select, options, placeholder) {
        if (!select) {
            return;
        }

        var currentValue = select.value;
        var html = ['<option value="">' + escapeHtml(placeholder) + "</option>"];

        (options || []).forEach(function (option) {
            var label = option.label || option.value || "";
            if (typeof option.count === "number" && option.count > 0) {
                label += " (" + option.count + ")";
            }
            html.push(
                '<option value="' + escapeHtml(option.value) + '">' + escapeHtml(label) + "</option>"
            );
        });

        select.innerHTML = html.join("");

        if (currentValue) {
            var hasCurrent = Array.prototype.some.call(select.options, function (option) {
                return option.value === currentValue;
            });
            select.value = hasCurrent ? currentValue : "";
        }
    }

    function loadFilterOptions() {
        var filters = buildFilterOptions();
        populateSelect(filterCategory, filters.categories || [], "Todas las categorías");
        populateSelect(filterDifficulty, filters.difficulties || [], "Todas las dificultades");
        state.category = filterCategory ? filterCategory.value : "";
        state.difficulty = filterDifficulty ? filterDifficulty.value : "";
    }

    async function loadRemoteFilterOptions() {
        if (!apiOnline) {
            return false;
        }

        try {
            var response = await fetch(API_BASE + "/recipes/filters");
            if (!response.ok) {
                throw new Error("filters failed");
            }
            var filters = normalizeRemoteFilterOptions(await response.json());
            if (!filters) {
                throw new Error("invalid filters payload");
            }
            populateSelect(filterCategory, filters.categories || [], "Todas las categorías");
            populateSelect(filterDifficulty, filters.difficulties || [], "Todas las dificultades");
            state.category = filterCategory ? filterCategory.value : "";
            state.difficulty = filterDifficulty ? filterDifficulty.value : "";
            return true;
        } catch (error) {
            console.warn("Remote filters unavailable:", error);
            return false;
        }
    }

    async function fetchSearchResultsFromApi(query, category, difficulty, page, size) {
        var params = new URLSearchParams();
        params.set("q", query && query.trim() ? query.trim() : "*");
        params.set("page", String(Math.max(Number(page) || 0, 0)));
        params.set("size", String(Math.max(Number(size) || DEFAULT_PAGE_SIZE, 1)));
        if (category) {
            params.set("category", category);
        }
        if (difficulty) {
            params.set("difficulty", difficulty);
        }

        var response = await fetch(API_BASE + "/recipes/search?" + params.toString());
        if (!response.ok) {
            throw new Error("search failed");
        }
        return response.json();
    }

    async function fetchAllCatalogFromApi() {
        var collected = [];
        var page = 0;
        var total = 0;

        while (page === 0 || collected.length < total) {
            var params = new URLSearchParams();
            params.set("q", "*");
            params.set("page", String(page));
            params.set("size", "50");

            var response = await fetch(API_BASE + "/recipes/search?" + params.toString());
            if (!response.ok) {
                throw new Error("search failed");
            }

            var data = await response.json();
            var batch = Array.isArray(data.results) ? data.results : [];
            collected = collected.concat(batch);
            total = typeof data.total === "number" ? data.total : collected.length;

            if (!batch.length || collected.length >= total) {
                break;
            }

            page += 1;
        }

        return collected;
    }

    async function loadLiveCatalogFromApi(force) {
        if (liveCatalogLoading) {
            return;
        }

        liveCatalogLoading = true;
        var previousMode = catalogMode;
        setCatalogMode("loading");

        try {
            var recipes = await fetchAllCatalogFromApi();
            if (!recipes.length) {
                throw new Error("empty catalog");
            }

            apiOnline = true;
            setCatalogRecipes(recipes, "live");
            loadFilterOptions();
            state.page = 0;
            setStatusMessage("Loaded " + recipes.length + " recipes from the live catalog", "success");
            doSearch();

            if (document.querySelector('[data-tab="ranking"]').classList.contains("active")) {
                loadRanking();
            }
        } catch (error) {
            apiOnline = false;
            if (!catalogRecipes.length) {
                loadDemoCatalog();
                loadFilterOptions();
                doSearch();
            } else {
                setCatalogMode(previousMode === "live" ? "live" : "demo");
            }
            if (force) {
                setStatusMessage("Catálogo demo activo: " + error.message, "warning");
            }
            console.warn("Live catalog unavailable:", error);
        } finally {
            liveCatalogLoading = false;
            if (catalogMode === "loading") {
                setCatalogMode(previousMode === "live" ? "live" : "demo");
            }
            updateCatalogModeText();
        }
    }

    function setActiveTab(tabName) {
        tabs.forEach(function (btn) {
            btn.classList.toggle("active", btn.dataset.tab === tabName);
        });
        tabContents.forEach(function (section) {
            section.classList.toggle("active", section.id === "tab-" + tabName);
        });
        if (tabName === "ranking") {
            loadRanking();
        }
    }

    function updateCatalogCount(total) {
        if (catalogCount) {
            catalogCount.textContent = total + " recipes";
        }
    }

    function setStatusMessage(message, kind) {
        if (!refreshStatus) {
            return;
        }
        refreshStatus.textContent = message || "";
        refreshStatus.className = "inline-status" + (kind ? " " + kind : "");
    }

    function renderRecipeCard(recipe, options) {
        options = options || {};
        var title = escapeHtml(recipe.title || "Receta sin título");
        var description = escapeHtml(truncateText(recipe.description || "", 140));
        var category = escapeHtml(formatCategoryLabel(recipe.category || "General"));
        var difficulty = escapeHtml(formatDifficultyLabel(recipe.difficulty || "n/d"));
        var cookingTime = recipe.cooking_time || 0;
        var ingredientCount = Array.isArray(recipe.ingredients) ? recipe.ingredients.length : 0;
        var instructionCount = Array.isArray(recipe.instructions) ? recipe.instructions.length : 0;
        var views = recipe.stats && recipe.stats.views ? recipe.stats.views : 0;
        var saved = recipe.stats && recipe.stats.saved ? recipe.stats.saved : 0;
        var cooked = recipe.stats && recipe.stats.cooked ? recipe.stats.cooked : 0;
        var score = recipe.score != null ? recipe.score : 0;
        var sourceName = escapeHtml(recipe.source_name || "demo");
        var sourceUrl = recipe.source_url ? escapeHtml(recipe.source_url) : "";
        var ingredients = Array.isArray(recipe.ingredients) ? recipe.ingredients.slice(0, 3) : [];
        var tags = Array.isArray(recipe.tags) ? recipe.tags.slice(0, 3) : [];
        var rankBadge = options.rank ? '<div class="rank-badge">#' + options.rank + "</div>" : "";
        var tone = getRecipeTone(recipe);
        var visual = renderRecipeImage(recipe, "recipe-image", recipe.title || "Receta");

        return [
            '<article class="recipe-card" data-id="' + escapeHtml(recipe.id) + '" data-tone="' + escapeHtml(tone) + '">',
            rankBadge,
            '<div class="recipe-visual">',
            visual,
            "</div>",
            '<div class="recipe-body">',
            '<div class="recipe-topline">',
            '<span class="source-pill">' + sourceName + "</span>",
            "</div>",
            '<h3 class="recipe-title">' + title + "</h3>",
            '<p class="recipe-description">' + description + "</p>",
            '<div class="tag-row">',
            '<span class="tag">' + category + "</span>",
            '<span class="tag">' + difficulty + "</span>",
            "</div>",
            '<div class="recipe-meta">',
            '<span data-field="time">' + formatTime(cookingTime) + "</span>",
            '<span data-field="views">Vistas: ' + views + "</span>",
            '<span data-field="saved">Guardadas: ' + saved + "</span>",
            '<span data-field="cooked">Cocinadas: ' + cooked + "</span>",
            '<span data-field="score">Puntuación: ' + score + "</span>",
            '<span>' + formatCount(ingredientCount, "ingrediente", "ingredientes") + "</span>",
            '<span>' + formatCount(instructionCount, "paso", "pasos") + "</span>",
            "</div>",
            ingredients.length
                ? '<div class="ingredient-row">' + ingredients.map(function (item) {
                      return '<span class="ingredient-chip">' + escapeHtml(item) + "</span>";
                  }).join("") + "</div>"
                : "",
            '<div class="action-row">',
            '<button class="action-btn" type="button" onclick="openRecipe(\'' + escapeJs(recipe.id) + '\')">Ver receta</button>',
            '<button class="action-btn" type="button" onclick="interact(\'' + escapeJs(recipe.id) + '\', \'save\')">Guardar</button>',
            '<button class="action-btn secondary" type="button" onclick="getRecommendations(\'' + escapeJs(recipe.id) + '\')">Similares</button>',
            sourceUrl
                ? '<a class="action-link" href="' + sourceUrl + '" target="_blank" rel="noopener">Fuente</a>'
                : "",
            "</div>",
            tags.length
                ? '<div class="source-tags">' + tags.map(function (item) {
                      return '<span class="tag soft">' + escapeHtml(item) + "</span>";
                  }).join("") + "</div>"
                : "",
            "</div>",
            "</article>",
        ].join("");
    }

    function renderRecipeGrid(container, recipes, options) {
        options = options || {};
        if (!recipes || !recipes.length) {
            container.innerHTML = '<div class="empty-state">No se encontraron recetas.</div>';
            return;
        }
        recipes.forEach(function (recipe) {
            storeRecipe(recipe);
        });
        container.innerHTML = recipes.map(function (recipe, index) {
            var cardOptions = {};
            if (typeof options.rankOffset === "number") {
                cardOptions.rank = options.rankOffset + index + 1;
            }
            return renderRecipeCard(recipe, cardOptions);
        }).join("");
    }

    function renderPagination(total) {
        var pageSize = getPageSize();
        var totalPages = Math.ceil(total / pageSize);
        var currentPage = Math.min(state.page, Math.max(totalPages - 1, 0));
        var startItem = total > 0 ? currentPage * pageSize + 1 : 0;
        var endItem = total > 0 ? Math.min(startItem + pageSize - 1, total) : 0;

        if (paginationSummary) {
            paginationSummary.textContent = total
                ? "Página " + (currentPage + 1) + " de " + Math.max(totalPages, 1) + " | Mostrando " + startItem + "-" + endItem + " de " + total
                : "No se encontraron recetas";
        }

        if (totalPages <= 1) {
            searchPagination.innerHTML = "";
            return;
        }

        var buttons = [];
        var addButton = function (page, label, disabled, active) {
            buttons.push(
                '<button type="button" class="page-btn' +
                    (active ? " active" : "") +
                    '" onclick="goToPage(' + page + ')"' +
                    (disabled ? " disabled" : "") +
                    '>' +
                    label +
                    "</button>"
            );
        };

        addButton(0, "Primera", currentPage === 0, false);
        addButton(Math.max(currentPage - 1, 0), "Anterior", currentPage === 0, false);

        var startPage = Math.max(0, currentPage - 2);
        var endPage = Math.min(totalPages - 1, currentPage + 2);

        if (startPage > 0) {
            buttons.push('<span class="page-ellipsis">...</span>');
        }

        for (var i = startPage; i <= endPage; i += 1) {
            addButton(i, String(i + 1), false, i === currentPage);
        }

        if (endPage < totalPages - 1) {
            buttons.push('<span class="page-ellipsis">...</span>');
        }

        addButton(Math.min(currentPage + 1, totalPages - 1), "Siguiente", currentPage >= totalPages - 1, false);
        addButton(totalPages - 1, "Última", currentPage >= totalPages - 1, false);
        searchPagination.innerHTML = buttons.join("");
    }

    async function checkHealth() {
        try {
            var response = await fetch("/health");
            if (!response.ok) {
                throw new Error("health check failed");
            }
            var data = await response.json();
            apiOnline = true;
            apiStatus.textContent = data.status === "ok" ? "En línea" : "Con fallas";
            apiStatus.className = "status-badge online";

            if (catalogMode !== "live" && !liveCatalogLoading) {
                await loadRemoteFilterOptions();
                await doSearch();
            }
        } catch (error) {
            apiOnline = false;
            apiStatus.textContent = "Sin conexión";
            apiStatus.className = "status-badge offline";
        }
    }

    async function doSearch() {
        searchResults.innerHTML = '<div class="loading-state">Buscando en el catálogo...</div>';
        searchPagination.innerHTML = "";

        var pageSize = getPageSize();
        setPageSize(pageSize);

        if (apiOnline) {
            try {
                var data = await fetchSearchResultsFromApi(
                    state.query || "*",
                    state.category,
                    state.difficulty,
                    state.page,
                    pageSize
                );
                var total = Number(data.total || 0);
                var totalPages = Math.ceil(total / pageSize);

                if (state.page > Math.max(totalPages - 1, 0)) {
                    state.page = Math.max(totalPages - 1, 0);
                    data = await fetchSearchResultsFromApi(
                        state.query || "*",
                        state.category,
                        state.difficulty,
                        state.page,
                        pageSize
                    );
                    total = Number(data.total || 0);
                }

                var results = (Array.isArray(data.results) ? data.results : []).map(function (recipe, index) {
                    return buildRecipe(recipe, index);
                });
                results.forEach(storeRecipe);
                renderRecipeGrid(searchResults, results);
                setCatalogMode("live");
                renderPagination(total);
                updateCatalogCount(total);
                setStatusMessage("Mostrando " + total + " recetas del catálogo en vivo", "success");
                return;
            } catch (error) {
                console.warn("Live search fallback:", error);
                apiOnline = false;
                apiStatus.textContent = "Sin conexión";
                apiStatus.className = "status-badge offline";
            }
        }

        var data = searchLocalCatalog(state.query || "*", state.category, state.difficulty, state.page, pageSize);
        var totalPages = Math.ceil((data.total || 0) / pageSize);
        if (state.page > Math.max(totalPages - 1, 0)) {
            state.page = Math.max(totalPages - 1, 0);
            data = searchLocalCatalog(state.query || "*", state.category, state.difficulty, state.page, pageSize);
        }
        renderRecipeGrid(searchResults, data.results || []);
        renderPagination(data.total || 0);
        updateCatalogCount(data.total || 0);
        setStatusMessage(
            "Mostrando " + (data.total || 0) + " recetas del " + (catalogMode === "live" ? "catálogo en vivo" : "catálogo demo"),
            catalogMode === "live" ? "success" : "warning"
        );
    }

    async function loadRanking() {
        rankingResults.innerHTML = '<div class="loading-state">Cargando clasificación...</div>';

        if (apiOnline) {
            try {
                var response = await fetch(API_BASE + "/recipes/ranking/month?limit=10");
                if (!response.ok) {
                    throw new Error("ranking failed");
                }
                var data = await response.json();
                var liveRecipes = Array.isArray(data.results) ? data.results : [];
                if (liveRecipes.length) {
                    liveRecipes.forEach(storeRecipe);
                    renderRecipeGrid(rankingResults, liveRecipes, { rankOffset: 0 });
                    return;
                }
            } catch (error) {
                console.warn("Ranking sync fallback:", error);
            }
        }

        var recipes = rankingLocalCatalog(10);
        if (!recipes.length) {
            rankingResults.innerHTML = '<div class="empty-state">Todavía no hay datos de clasificación.</div>';
            return;
        }
        renderRecipeGrid(rankingResults, recipes, { rankOffset: 0 });
    }

    function getOrCreateUserId() {
        var key = "ph_user_id";
        var existing = window.localStorage.getItem(key);
        if (existing) {
            return existing;
        }
        var id = "u-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 9);
        window.localStorage.setItem(key, id);
        return id;
    }

    async function interact(recipeId, action) {
        if ((action === "save" || action === "cook") && !currentUserId()) {
            setStatusMessage("Inicia sesión para guardar o marcar recetas como cocinadas", "warning");
            openAuthModal("login");
            return null;
        }

        var snapshot = null;
        var existingRecipe = getRecipeById(recipeId);
        if (existingRecipe) {
            snapshot = {
                views: existingRecipe.stats && existingRecipe.stats.views ? existingRecipe.stats.views : 0,
                saved: existingRecipe.stats && existingRecipe.stats.saved ? existingRecipe.stats.saved : 0,
                cooked: existingRecipe.stats && existingRecipe.stats.cooked ? existingRecipe.stats.cooked : 0,
                score: existingRecipe.score != null ? existingRecipe.score : 0,
            };
        }

        var localRecipe = updateRecipeInCatalog(recipeId, function (recipe) {
            if (action === "view") {
                recipe.stats.views += 1;
            } else if (action === "save") {
                recipe.stats.saved += 1;
            } else if (action === "cook") {
                recipe.stats.cooked += 1;
            }
            recipe.score = Math.round(((recipe.stats.saved * 5.0) + (recipe.stats.views * 0.5) + (recipe.stats.cooked * 8.0)) * 100) / 100;
        });

        if (!localRecipe) {
            return null;
        }

        var localData = {
            success: true,
            recipe_id: recipeId,
            action: action,
            user_id: currentUserId() || "anonymous",
            views: localRecipe.stats.views,
            saved: localRecipe.stats.saved,
            cooked: localRecipe.stats.cooked || 0,
            score: localRecipe.score,
        };

        syncRecipeCardStats(recipeId, localData);
        syncRecipeModalStats(recipeId, localData);

        if (recipeCache[recipeId]) {
            recipeCache[recipeId].stats = {
                views: localData.views,
                saved: localData.saved,
                cooked: localData.cooked,
            };
            recipeCache[recipeId].score = localData.score;
        }

        if (action === "save") {
            var cards = Array.prototype.slice.call(document.querySelectorAll(".recipe-card"));
            var card = null;
            for (var i = 0; i < cards.length; i += 1) {
                if (cards[i].dataset.id === recipeId) {
                    card = cards[i];
                    break;
                }
            }
            if (card) {
                var buttons = card.querySelectorAll(".action-btn");
                var saveBtn = buttons.length > 1 ? buttons[1] : null;
                if (saveBtn) {
                    saveBtn.textContent = "Guardado";
                    setTimeout(function () {
                        saveBtn.textContent = "Guardar";
                    }, 1200);
                }
            }
        }

        if (!apiOnline) {
            return localData;
        }

        try {
            var response = await fetch(API_BASE + "/recipes/" + encodeURIComponent(recipeId) + "/interact", {
                method: "POST",
                headers: Object.assign({
                    "Content-Type": "application/json",
                }, authHeaders()),
                body: JSON.stringify({ action: action, user_id: currentUserId() || getOrCreateUserId() }),
            });
            if (!response.ok) {
                var failure = await response.json().catch(function () {
                    return {};
                });
                throw new Error((failure && failure.detail) || "interaction failed");
            }
            var data = await response.json();
            syncRecipeCardStats(recipeId, data);
            syncRecipeModalStats(recipeId, data);
            updateRecipeInCatalog(recipeId, function (recipe) {
                recipe.stats.views = data.views;
                recipe.stats.saved = data.saved;
                recipe.stats.cooked = data.cooked || 0;
                recipe.score = data.score;
            });
            if (recipeCache[recipeId]) {
                recipeCache[recipeId].stats = {
                    views: data.views,
                    saved: data.saved,
                    cooked: data.cooked || 0,
                };
                recipeCache[recipeId].score = data.score;
            }
            return data;
        } catch (error) {
            if (action !== "view" && /login|auth/i.test(String(error && error.message))) {
                if (snapshot) {
                    updateRecipeInCatalog(recipeId, function (recipe) {
                        recipe.stats.views = snapshot.views;
                        recipe.stats.saved = snapshot.saved;
                        recipe.stats.cooked = snapshot.cooked;
                        recipe.score = snapshot.score;
                    });
                    syncRecipeCardStats(recipeId, snapshot);
                    syncRecipeModalStats(recipeId, snapshot);
                }
                openAuthModal("login");
            }
            console.warn("Interaction sync fallback:", error);
            return localData;
        }
    }

    async function getPersonalRecommendations() {
        if (!currentUserId()) {
        setStatusMessage("Inicia sesión para ver recomendaciones personalizadas", "warning");
            openAuthModal("login");
            return;
        }

        recommendResults.innerHTML = '<div class="loading-state">Cargando recomendaciones para ti...</div>';

        try {
            var response = await fetch(API_BASE + "/users/me/recommendations?limit=6", {
                headers: authHeaders(),
            });
            if (!response.ok) {
                throw new Error("personalized recommendations failed");
            }
            var data = await response.json();
            var recipes = data.results || [];
            if (!recipes.length) {
                recommendResults.innerHTML = '<div class="empty-state">Aún no hay recomendaciones personalizadas.</div>';
            } else {
                renderRecipeGrid(recommendResults, recipes);
            }
            setActiveTab("recomendaciones");
        } catch (error) {
            console.warn("Personal recommendation error:", error);
            recommendResults.innerHTML = '<div class="empty-state">Aún no hay recomendaciones personalizadas.</div>';
        }
    }

    async function getRecommendations(recipeId) {
        var inputValue = String(recipeId == null ? "" : recipeId).trim();
        recipeIdInput.value = inputValue;
        recommendResults.innerHTML = '<div class="loading-state">Cargando recomendaciones...</div>';
        var mode = normalizeRecommendationMode(recommendationMode ? recommendationMode.value || "hybrid" : "hybrid");
        var anchorRecipe = getRecipeById(inputValue);
        var localRecipes = anchorRecipe ? recommendLocalCatalog(anchorRecipe.id, 6, mode) : discoverLocalRecommendations(inputValue, 6, mode);

        if (apiOnline) {
            try {
                var params = new URLSearchParams();
                params.set("limit", "6");
                params.set("mode", mode);
                params.set("q", inputValue);

                var response = await fetch(
                    API_BASE + "/recipes/recommendations/discover?" + params.toString(),
                    {
                        headers: authHeaders(),
                    }
                );
                if (!response.ok) {
                    throw new Error("recommendations failed");
                }
                var data = await response.json();
                var recipes = data.results || [];
                if (!recipes.length && localRecipes.length) {
                    recipes = localRecipes;
                }
                if (!recipes.length) {
                    recommendResults.innerHTML = '<div class="empty-state">No recipes matched that recommendation search.</div>';
                    setStatusMessage("No encontramos coincidencias para: " + inputValue, "warning");
                } else {
                    renderRecipeGrid(recommendResults, recipes);
                    if (inputValue) {
                    setStatusMessage("Recomendaciones basadas en: " + inputValue, "success");
                    }
                }
                closeRecipeModal();
                setActiveTab("recomendaciones");
                return;
            } catch (error) {
                console.warn("Recommendation sync fallback:", error);
            }
        }

        if (!localRecipes.length) {
            recommendResults.innerHTML = '<div class="empty-state">No recipes matched that recommendation search.</div>';
            setStatusMessage("No encontramos coincidencias para: " + inputValue, "warning");
        } else {
            renderRecipeGrid(recommendResults, localRecipes);
            if (inputValue) {
                setStatusMessage("Recomendaciones basadas en: " + inputValue + " (local)", "warning");
            }
        }
        closeRecipeModal();
        setActiveTab("recomendaciones");
    }

    async function refreshCatalog() {
        setStatusMessage("Actualizando catálogo...", "loading");
        refreshBtn.disabled = true;
        try {
            if (apiOnline) {
                var response = await fetch(API_BASE + "/recipes/refresh", {
                    method: "POST",
                });
                if (!response.ok) {
                    throw new Error("refresh failed");
                }
                var data = await response.json();
                setStatusMessage(
                    "Se actualizaron " + data.stored + " recetas desde " + (data.sources && data.sources.length ? data.sources.join(", ") : "demo"),
                    data.fallback_used ? "warning" : "success"
                );
                await loadRemoteFilterOptions();
                state.page = 0;
                await doSearch();
            } else {
                loadDemoCatalog();
                loadFilterOptions();
                state.page = 0;
                doSearch();
                setStatusMessage(
                    catalogMode === "demo" ? "Catálogo demo actualizado" : "Catálogo actual actualizado",
                    "warning"
                );
                if (document.querySelector('[data-tab="ranking"]').classList.contains("active")) {
                    loadRanking();
                }
            }
        } catch (error) {
            apiOnline = false;
            if (!catalogRecipes.length) {
                loadDemoCatalog();
            }
            loadFilterOptions();
            state.page = 0;
            doSearch();
            setStatusMessage(
                "Error al actualizar: " + error.message + (catalogMode === "demo" ? " - se restauró el catálogo demo" : " - se mantiene el catálogo actual"),
                "error"
            );
        } finally {
            refreshBtn.disabled = false;
        }
    }

    function runSearchFromInputs() {
        state.query = searchInput.value.trim();
        state.category = filterCategory.value;
        state.difficulty = filterDifficulty.value;
        state.page = 0;
        doSearch();
    }

    function goToPage(page) {
        state.page = Math.max(Number(page) || 0, 0);
        doSearch();
        window.scrollTo({ top: searchResults.offsetTop - 40, behavior: "smooth" });
    }

    window.interact = interact;
    window.openRecipe = openRecipe;
    window.getRecommendations = getRecommendations;
    window.goToPage = goToPage;

    tabs.forEach(function (btn) {
        btn.addEventListener("click", function () {
            setActiveTab(btn.dataset.tab);
        });
    });

    searchBtn.addEventListener("click", runSearchFromInputs);
    searchInput.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
            runSearchFromInputs();
        }
    });

    if (pageSizeSelect) {
        pageSizeSelect.addEventListener("change", function () {
            setPageSize(pageSizeSelect.value);
            state.page = 0;
            doSearch();
        });
    }

    [filterCategory, filterDifficulty].forEach(function (select) {
        select.addEventListener("change", function () {
            runSearchFromInputs();
        });
    });

    if (authBtn) {
        authBtn.addEventListener("click", function () {
            openAuthModal("login");
        });
    }

    if (logoutBtn) {
        logoutBtn.addEventListener("click", logoutUser);
    }

    authTabButtons.forEach(function (button) {
        button.addEventListener("click", function () {
            setAuthModalMode(button.dataset.authTab);
        });
    });

    if (loginForm) {
        loginForm.addEventListener("submit", submitLoginForm);
    }

    if (registerForm) {
        registerForm.addEventListener("submit", submitRegisterForm);
    }

    recommendBtn.addEventListener("click", function () {
        var recipeId = recipeIdInput.value.trim();
        if (recipeId) {
            getRecommendations(recipeId);
        } else {
            getPersonalRecommendations();
        }
    });

    recipeIdInput.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
            recommendBtn.click();
        }
    });

    refreshBtn.addEventListener("click", refreshCatalog);

    if (authModal) {
        authModal.addEventListener("click", function (event) {
            if (event.target && event.target.dataset && event.target.dataset.closeAuth === "true") {
                closeAuthModal();
            }
        });
    }

    if (authModalClose) {
        authModalClose.addEventListener("click", closeAuthModal);
    }

    if (recipeModal) {
        recipeModal.addEventListener("click", function (event) {
            if (event.target && event.target.dataset && event.target.dataset.closeModal === "true") {
                closeRecipeModal();
            }
        });
    }

    if (recipeModalClose) {
        recipeModalClose.addEventListener("click", closeRecipeModal);
    }

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
            closeRecipeModal();
            closeAuthModal();
        }
    });

    loadStoredPreferences();
    loadStoredAuth();
    renderAuthState();
    loadDemoCatalog();
    loadFilterOptions();
    doSearch();
    restoreAuthSession();
    checkHealth();
    setInterval(checkHealth, 30000);
});
