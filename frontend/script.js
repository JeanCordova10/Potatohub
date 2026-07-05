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
        catalogModeBadge.textContent = label || (mode === "live" ? "Live catalog" : mode === "demo" ? "Demo catalog" : "Loading catalog");
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
        category = normalizeTextValue(category);
        difficulty = normalizeTextValue(difficulty);
        page = Math.max(Number(page) || 0, 0);
        size = Math.max(Number(size) || DEFAULT_PAGE_SIZE, 1);

        var tokens = tokenizeText(query);
        var matches = [];

        for (var i = 0; i < catalogRecipes.length; i += 1) {
            var recipe = catalogRecipes[i];
            if (category && normalizeTextValue(recipe.category) !== category) {
                continue;
            }
            if (difficulty && normalizeTextValue(recipe.difficulty) !== difficulty) {
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
        mode = normalizeTextValue(mode || "hybrid");
        if (mode !== "hybrid" && mode !== "ingredients" && mode !== "type") {
            mode = "hybrid";
        }

        var anchorIngredients = new Set(tokenizeText((anchor.ingredients || []).join(" ")));
        var anchorTags = new Set(tokenizeText((anchor.tags || []).join(" ")));
        var anchorTitle = new Set(tokenizeText(anchor.title));
        var anchorCategory = normalizeTextValue(anchor.category);
        var anchorDifficulty = normalizeTextValue(anchor.difficulty);
        var scored = [];

        for (var i = 0; i < catalogRecipes.length; i += 1) {
            var candidate = catalogRecipes[i];
            if (candidate.id === recipeId) {
                continue;
            }

            var candidateIngredients = new Set(tokenizeText((candidate.ingredients || []).join(" ")));
            var candidateTags = new Set(tokenizeText((candidate.tags || []).join(" ")));
            var candidateTitle = new Set(tokenizeText(candidate.title));
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
            var sameCategory = anchorCategory && normalizeTextValue(candidate.category) === anchorCategory;
            var sameDifficulty = anchorDifficulty && normalizeTextValue(candidate.difficulty) === anchorDifficulty;

            var score = 0;
            if (mode === "ingredients") {
                score += sharedIngredients * 3;
                score += sharedTags * 0.75;
                score += sameCategory ? 1 : 0;
                score += sameDifficulty ? 0.2 : 0;
            } else if (mode === "type") {
                score += sameCategory ? 4 : 0;
                score += sharedIngredients * 1.25;
                score += sharedTags * 0.75;
                score += sameDifficulty ? 0.5 : 0;
            } else {
                score += sharedIngredients * 2;
                score += sharedTags * 1;
                score += sharedTitle * 0.5;
                score += sameCategory ? 3 : 0;
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
            var category = String(recipe.category || "").trim();
            var difficulty = String(recipe.difficulty || "").trim();
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
                return { value: value, label: value, count: categoryCounts[value] };
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
                return { value: value, label: value.charAt(0).toUpperCase() + value.slice(1), count: difficultyCounts[value] };
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
                return item;
            }),
            difficulties: toOptionList(payload.difficulties, function (item) {
                item.label = item.label.charAt(0).toUpperCase() + item.label.slice(1);
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
                catalogModeBadge.textContent = "Live catalog";
                catalogModeBadge.className = "inline-status success";
            } else if (catalogMode === "demo") {
                catalogModeBadge.textContent = "Demo catalog";
                catalogModeBadge.className = "inline-status warning";
            } else if (catalogMode === "loading") {
                catalogModeBadge.textContent = "Loading catalog";
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
                title: "Garden Potato Skillet",
                description: "Golden potatoes, herbs and a bright finish of lemon. Quick, colorful and easy to test end to end.",
                category: "Potato",
                difficulty: "easy",
                cooking_time: 25,
                ingredients: ["3 potatoes", "2 tbsp olive oil", "1 tsp salt", "1 tsp paprika", "1 tbsp parsley"],
                instructions: ["Dice the potatoes.", "Pan-fry until golden.", "Season with paprika and salt.", "Finish with parsley and lemon."],
                tags: ["skillet", "quick", "herb-forward"],
                stats: { views: 18, saved: 4 },
                score: 24,
            },
            0
        ),
        buildRecipe(
            {
                id: "demo-cheesy-potato-bites",
                title: "Cheesy Potato Bites",
                description: "Crisp on the outside, soft on the inside, with a cheesy center that makes the card easy to verify.",
                category: "Snack",
                difficulty: "medium",
                cooking_time: 35,
                ingredients: ["4 potatoes", "1 cup grated cheese", "1 egg", "2 tbsp flour", "salt"],
                instructions: ["Mash the potatoes.", "Mix with cheese and egg.", "Shape small bites.", "Bake until crisp."],
                tags: ["party food", "baked", "cheese"],
                stats: { views: 12, saved: 5 },
                score: 29,
            },
            1
        ),
        buildRecipe(
            {
                id: "demo-creamy-potato-soup",
                title: "Creamy Potato Soup",
                description: "A cozy bowl with a smooth texture, ideal for ranking and recommendation checks.",
                category: "Soup",
                difficulty: "easy",
                cooking_time: 40,
                ingredients: ["5 potatoes", "1 onion", "2 cups vegetable stock", "1/2 cup cream", "salt and pepper"],
                instructions: ["Saute the onion.", "Add potatoes and stock.", "Simmer until tender.", "Blend and finish with cream."],
                tags: ["comfort food", "blended", "winter"],
                stats: { views: 24, saved: 9 },
                score: 42,
            },
            2
        ),
        buildRecipe(
            {
                id: "demo-roasted-potato-salad",
                title: "Roasted Potato Salad",
                description: "A bright salad with mustard dressing, fresh herbs and a clean layout for the search UI.",
                category: "Salad",
                difficulty: "medium",
                cooking_time: 30,
                ingredients: ["4 potatoes", "1 cucumber", "2 tbsp mustard", "1 tbsp vinegar", "herbs"],
                instructions: ["Roast the potatoes.", "Mix the dressing.", "Combine everything while warm.", "Serve with herbs."],
                tags: ["fresh", "side dish", "mustard"],
                stats: { views: 14, saved: 3 },
                score: 21,
            },
            3
        ),
        buildRecipe(
            {
                id: "demo-potato-breakfast-hash",
                title: "Potato Breakfast Hash",
                description: "Potatoes, eggs and peppers in one pan. Good for testing filters and quick interactions.",
                category: "Breakfast",
                difficulty: "easy",
                cooking_time: 20,
                ingredients: ["3 potatoes", "2 eggs", "1 pepper", "1 onion", "oil"],
                instructions: ["Cook the potatoes.", "Add onion and pepper.", "Crack the eggs.", "Serve immediately."],
                tags: ["brunch", "one pan", "savory"],
                stats: { views: 31, saved: 12 },
                score: 51,
            },
            4
        ),
        buildRecipe(
            {
                id: "demo-loaded-potato-main",
                title: "Loaded Potato Main",
                description: "A heartier main dish with smoked seasoning, sour cream and a stronger tone for the cards.",
                category: "Main Dish",
                difficulty: "hard",
                cooking_time: 55,
                ingredients: ["4 potatoes", "1 cup sour cream", "1 cup cheese", "chives", "smoked paprika"],
                instructions: ["Bake the potatoes.", "Slice open and fluff the center.", "Top with sour cream and cheese.", "Finish with chives."],
                tags: ["hearty", "oven", "dinner"],
                stats: { views: 22, saved: 8 },
                score: 39,
            },
            5
        ),
        buildRecipe(
            {
                id: "demo-potato-dessert-cakes",
                title: "Sweet Potato Mini Cakes",
                description: "A softer dessert-style card to verify contrast, modal detail and ranking states.",
                category: "Dessert",
                difficulty: "medium",
                cooking_time: 45,
                ingredients: ["2 sweet potatoes", "1/2 cup sugar", "1 cup flour", "2 eggs", "cinnamon"],
                instructions: ["Cook and mash the sweet potatoes.", "Mix with the rest of the batter.", "Portion into molds.", "Bake until set."],
                tags: ["sweet", "bake", "cinnamon"],
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
            authModalTitle.textContent = activeMode === "register" ? "Crear cuenta" : "Iniciar sesion";
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
            setAuthStatus("Sesion iniciada como " + (session.user && session.user.name ? session.user.name : "usuario"), "success");
            closeAuthModal();
            setStatusMessage("Sesion iniciada correctamente", "success");
        } catch (error) {
            setAuthStatus(error.message || "No se pudo iniciar sesion", "error");
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
            setAuthStatus("Cuenta creada y sesion activa", "success");
            closeAuthModal();
            setStatusMessage("Cuenta creada correctamente", "success");
        } catch (error) {
            setAuthStatus(error.message || "No se pudo crear la cuenta", "error");
        }
    }

    function logoutUser() {
        clearAuthState();
        setAuthStatus("Sesion cerrada", "warning");
        closeAuthModal();
        setStatusMessage("Sesion cerrada", "warning");
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
        var safeCategory = escapeHtml(String(recipe && recipe.category ? recipe.category : "Recipe"));
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
            ' alt="' + escapeHtml(altText || recipe.title || "Recipe") + '"',
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
        var score = card.querySelector('[data-field="score"]');
        if (views) {
            views.textContent = "Views: " + data.views;
        }
        if (saved) {
            saved.textContent = "Saved: " + data.saved;
        }
        if (score) {
            score.textContent = "Score: " + data.score;
        }
    }

    function syncRecipeModalStats(recipeId, data) {
        if (!recipeModal || recipeModal.hidden || currentRecipeId !== recipeId) {
            return;
        }
        var views = recipeModal.querySelector('[data-detail-field="views"]');
        var saved = recipeModal.querySelector('[data-detail-field="saved"]');
        var score = recipeModal.querySelector('[data-detail-field="score"]');
        if (views) {
            views.textContent = "Views: " + data.views;
        }
        if (saved) {
            saved.textContent = "Saved: " + data.saved;
        }
        if (score) {
            score.textContent = "Score: " + data.score;
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
        var title = escapeHtml(recipe.title || "Untitled recipe");
        var description = escapeHtml(recipe.description || "No description available.");
        var category = escapeHtml(recipe.category || "General");
        var difficulty = escapeHtml(recipe.difficulty || "n/a");
        var cookingTime = recipe.cooking_time || 0;
        var ingredientCount = Array.isArray(recipe.ingredients) ? recipe.ingredients.length : 0;
        var instructionCount = Array.isArray(recipe.instructions) ? recipe.instructions.length : 0;
        var views = recipe.stats && recipe.stats.views ? recipe.stats.views : 0;
        var saved = recipe.stats && recipe.stats.saved ? recipe.stats.saved : 0;
        var score = recipe.score != null ? recipe.score : 0;
        var sourceName = escapeHtml(recipe.source_name || "demo");
        var sourceUrl = recipe.source_url ? escapeHtml(recipe.source_url) : "";
        var ingredients = Array.isArray(recipe.ingredients) ? recipe.ingredients : [];
        var instructions = Array.isArray(recipe.instructions) ? recipe.instructions : [];
        var tags = Array.isArray(recipe.tags) ? recipe.tags : [];
        var tone = getRecipeTone(recipe);
        var visual = renderRecipeImage(recipe, "recipe-detail-image", recipe.title || "Recipe");

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
            '<span data-detail-field="views">Views: ' + views + "</span>",
            '<span data-detail-field="saved">Saved: ' + saved + "</span>",
            '<span data-detail-field="score">Score: ' + score + "</span>",
            '<span>' + formatCount(ingredientCount, "ingrediente", "ingredientes") + "</span>",
            '<span>' + formatCount(instructionCount, "paso", "pasos") + "</span>",
            "</div>",
            '<div class="recipe-detail-actions">',
            '<button class="action-btn" type="button" onclick="interact(\'' + escapeJs(recipe.id) + '\', \'save\')">Guardar</button>',
            '<button class="action-btn secondary" type="button" onclick="getRecommendations(\'' + escapeJs(recipe.id) + '\')">Similares</button>',
            sourceUrl
                ? '<a class="action-link" href="' + sourceUrl + '" target="_blank" rel="noopener">Open source</a>'
                : "",
            "</div>",
            "</div>",
            "</div>",
            '<div class="recipe-detail-grid">',
            '<section class="recipe-detail-block">',
            "<h3>Ingredients</h3>",
            ingredients.length
                ? '<ul class="detail-list">' + ingredients.map(function (item) {
                      return "<li>" + escapeHtml(item) + "</li>";
                  }).join("") + "</ul>"
                : '<p class="muted">No ingredients available.</p>',
            "</section>",
            '<section class="recipe-detail-block">',
            "<h3>Instructions</h3>",
            instructions.length
                ? '<ol class="detail-list ordered">' + instructions.map(function (item) {
                      return "<li>" + escapeHtml(item) + "</li>";
                  }).join("") + "</ol>"
                : '<p class="muted">No instructions available.</p>',
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
        recipeModalTitle.textContent = recipe.title || "Recipe";
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
                    recipeModalTitle.textContent = "Recipe";
                    recipeModalBody.innerHTML = '<div class="loading-state">Loading recipe...</div>';
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
                    recipeModalTitle.textContent = "Recipe unavailable";
                    recipeModalBody.innerHTML = '<div class="error-state">Recipe details could not be loaded.</div>';
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
        populateSelect(filterCategory, filters.categories || [], "All categories");
        populateSelect(filterDifficulty, filters.difficulties || [], "All difficulty");
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
            populateSelect(filterCategory, filters.categories || [], "All categories");
            populateSelect(filterDifficulty, filters.difficulties || [], "All difficulty");
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
                setStatusMessage("Demo catalog active: " + error.message, "warning");
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
        var title = escapeHtml(recipe.title || "Untitled recipe");
        var description = escapeHtml(truncateText(recipe.description || "", 140));
        var category = escapeHtml(recipe.category || "General");
        var difficulty = escapeHtml(recipe.difficulty || "n/a");
        var cookingTime = recipe.cooking_time || 0;
        var ingredientCount = Array.isArray(recipe.ingredients) ? recipe.ingredients.length : 0;
        var instructionCount = Array.isArray(recipe.instructions) ? recipe.instructions.length : 0;
        var views = recipe.stats && recipe.stats.views ? recipe.stats.views : 0;
        var saved = recipe.stats && recipe.stats.saved ? recipe.stats.saved : 0;
        var score = recipe.score != null ? recipe.score : 0;
        var sourceName = escapeHtml(recipe.source_name || "demo");
        var sourceUrl = recipe.source_url ? escapeHtml(recipe.source_url) : "";
        var ingredients = Array.isArray(recipe.ingredients) ? recipe.ingredients.slice(0, 3) : [];
        var tags = Array.isArray(recipe.tags) ? recipe.tags.slice(0, 3) : [];
        var rankBadge = options.rank ? '<div class="rank-badge">#' + options.rank + "</div>" : "";
        var tone = getRecipeTone(recipe);
        var visual = renderRecipeImage(recipe, "recipe-image", recipe.title || "Recipe");

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
            '<span data-field="views">Views: ' + views + "</span>",
            '<span data-field="saved">Saved: ' + saved + "</span>",
            '<span data-field="score">Score: ' + score + "</span>",
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
                ? '<a class="action-link" href="' + sourceUrl + '" target="_blank" rel="noopener">Source</a>'
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
            container.innerHTML = '<div class="empty-state">No recipes found.</div>';
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
                ? "Page " + (currentPage + 1) + " of " + Math.max(totalPages, 1) + " | Showing " + startItem + "-" + endItem + " of " + total
                : "No recipes found";
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

        addButton(0, "First", currentPage === 0, false);
        addButton(Math.max(currentPage - 1, 0), "Prev", currentPage === 0, false);

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

        addButton(Math.min(currentPage + 1, totalPages - 1), "Next", currentPage >= totalPages - 1, false);
        addButton(totalPages - 1, "Last", currentPage >= totalPages - 1, false);
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
            apiStatus.textContent = data.status === "ok" ? "Online" : "Degraded";
            apiStatus.className = "status-badge online";

            if (catalogMode !== "live" && !liveCatalogLoading) {
                await loadRemoteFilterOptions();
                await doSearch();
            }
        } catch (error) {
            apiOnline = false;
            apiStatus.textContent = "Offline";
            apiStatus.className = "status-badge offline";
        }
    }

    async function doSearch() {
        searchResults.innerHTML = '<div class="loading-state">Searching catalog...</div>';
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
                setStatusMessage("Showing " + total + " recipes from live catalog", "success");
                return;
            } catch (error) {
                console.warn("Live search fallback:", error);
                apiOnline = false;
                apiStatus.textContent = "Offline";
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
            "Showing " + (data.total || 0) + " recipes from " + (catalogMode === "live" ? "live catalog" : "demo catalog"),
            catalogMode === "live" ? "success" : "warning"
        );
    }

    async function loadRanking() {
        rankingResults.innerHTML = '<div class="loading-state">Loading ranking...</div>';

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
            rankingResults.innerHTML = '<div class="empty-state">No ranking data yet.</div>';
            return;
        }
        renderRecipeGrid(rankingResults, recipes, { rankOffset: 0 });
    }

    async function interact(recipeId, action) {
        var localRecipe = updateRecipeInCatalog(recipeId, function (recipe) {
            if (action === "view") {
                recipe.stats.views += 1;
            } else if (action === "save") {
                recipe.stats.saved += 1;
            }
            recipe.score = Math.round(((recipe.stats.saved * 5.0) + (recipe.stats.views * 0.5)) * 100) / 100;
        });

        if (!localRecipe) {
            return null;
        }

        var localData = {
            success: true,
            recipe_id: recipeId,
            action: action,
            views: localRecipe.stats.views,
            saved: localRecipe.stats.saved,
            score: localRecipe.score,
        };

        syncRecipeCardStats(recipeId, localData);
        syncRecipeModalStats(recipeId, localData);

        if (recipeCache[recipeId]) {
            recipeCache[recipeId].stats = {
                views: localData.views,
                saved: localData.saved,
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
                    saveBtn.textContent = "Saved";
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
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ action: action }),
            });
            if (!response.ok) {
                throw new Error("interaction failed");
            }
            var data = await response.json();
            syncRecipeCardStats(recipeId, data);
            syncRecipeModalStats(recipeId, data);
            updateRecipeInCatalog(recipeId, function (recipe) {
                recipe.stats.views = data.views;
                recipe.stats.saved = data.saved;
                recipe.score = data.score;
            });
            if (recipeCache[recipeId]) {
                recipeCache[recipeId].stats = {
                    views: data.views,
                    saved: data.saved,
                };
                recipeCache[recipeId].score = data.score;
            }
            return data;
        } catch (error) {
            console.warn("Interaction sync fallback:", error);
            return localData;
        }
    }

    async function getRecommendations(recipeId) {
        recipeIdInput.value = recipeId;
        recommendResults.innerHTML = '<div class="loading-state">Loading recommendations...</div>';
        var mode = recommendationMode ? recommendationMode.value || "hybrid" : "hybrid";
        var localRecipes = recommendLocalCatalog(recipeId, 6, mode);

        if (apiOnline) {
            try {
                var params = new URLSearchParams();
                params.set("limit", "6");
                params.set("mode", mode);

                var response = await fetch(
                    API_BASE + "/recipes/" + encodeURIComponent(recipeId) + "/recommendations?" + params.toString()
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
                    recommendResults.innerHTML = '<div class="empty-state">No similar recipes found.</div>';
                } else {
                    renderRecipeGrid(recommendResults, recipes);
                }
                closeRecipeModal();
                setActiveTab("recomendaciones");
                return;
            } catch (error) {
                console.warn("Recommendation sync fallback:", error);
            }
        }

        if (!localRecipes.length) {
            recommendResults.innerHTML = '<div class="empty-state">No similar recipes found.</div>';
        } else {
            renderRecipeGrid(recommendResults, localRecipes);
        }
        closeRecipeModal();
        setActiveTab("recomendaciones");
    }

    async function refreshCatalog() {
        setStatusMessage("Refreshing catalog...", "loading");
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
                    "Updated " + data.stored + " recipes from " + (data.sources && data.sources.length ? data.sources.join(", ") : "demo"),
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
                    catalogMode === "demo" ? "Demo catalog refreshed" : "Current catalog refreshed",
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
                "Refresh error: " + error.message + (catalogMode === "demo" ? " - demo catalog restored" : " - keeping current catalog"),
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
