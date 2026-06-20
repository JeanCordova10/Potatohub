document.addEventListener("DOMContentLoaded", function () {
    const API_BASE = "/api";
    const PAGE_SIZE = 6;

    var state = {
        page: 0,
        query: "",
        category: "",
        difficulty: "",
    };

    var tabs = Array.prototype.slice.call(document.querySelectorAll(".tab-btn"));
    var tabContents = Array.prototype.slice.call(document.querySelectorAll(".tab-content"));
    var searchInput = document.getElementById("searchInput");
    var searchBtn = document.getElementById("searchBtn");
    var filterCategory = document.getElementById("filterCategory");
    var filterDifficulty = document.getElementById("filterDifficulty");
    var recommendationMode = document.getElementById("recommendationMode");
    var searchResults = document.getElementById("searchResults");
    var searchPagination = document.getElementById("searchPagination");
    var rankingResults = document.getElementById("rankingResults");
    var recommendResults = document.getElementById("recommendResults");
    var recipeIdInput = document.getElementById("recipeIdInput");
    var recommendBtn = document.getElementById("recommendBtn");
    var refreshBtn = document.getElementById("refreshBtn");
    var refreshStatus = document.getElementById("refreshStatus");
    var catalogCount = document.getElementById("catalogCount");
    var apiStatus = document.getElementById("apiStatus");
    var catalogModeBadge = document.getElementById("catalogModeBadge");
    var recipeModal = document.getElementById("recipeModal");
    var recipeModalBody = document.getElementById("recipeModalBody");
    var recipeModalTitle = document.getElementById("recipeModalTitle");
    var recipeModalClose = document.getElementById("recipeModalClose");
    var recipeCache = {};
    var currentRecipeId = "";
    var catalogRecipes = [];
    var catalogMode = "loading";
    var apiOnline = false;
    var liveCatalogLoading = false;

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
        item.image_url = item.image_url ? String(item.image_url) : "";
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
        size = Math.max(Number(size) || PAGE_SIZE, 1);

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

    function buildFilterOptions() {
        var categoryCounts = {};
        var difficultyCounts = {};
        var sourceCounts = {};

        catalogRecipes.forEach(function (recipe) {
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
        var imageUrl = recipe.image_url ? escapeHtml(recipe.image_url) : "";
        var ingredients = Array.isArray(recipe.ingredients) ? recipe.ingredients : [];
        var instructions = Array.isArray(recipe.instructions) ? recipe.instructions : [];
        var tags = Array.isArray(recipe.tags) ? recipe.tags : [];
        var tone = getRecipeTone(recipe);
        var visual = imageUrl
            ? '<img class="recipe-detail-image" src="' + imageUrl + '" alt="' + title + '" loading="lazy">'
            : '<div class="recipe-detail-placeholder">' + escapeHtml((recipe.title || "R").charAt(0).toUpperCase()) + "</div>";

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
        var imageUrl = recipe.image_url ? escapeHtml(recipe.image_url) : "";
        var rankBadge = options.rank ? '<div class="rank-badge">#' + options.rank + "</div>" : "";
        var tone = getRecipeTone(recipe);
        var visual = imageUrl
            ? '<img class="recipe-image" src="' + imageUrl + '" alt="' + title + '" loading="lazy">'
            : '<div class="recipe-placeholder">' + escapeHtml((recipe.title || "R").charAt(0).toUpperCase()) + "</div>";

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
        var totalPages = Math.ceil(total / PAGE_SIZE);
        if (totalPages <= 1) {
            searchPagination.innerHTML = "";
            return;
        }

        var buttons = [];
        for (var i = 0; i < totalPages; i += 1) {
            buttons.push(
                '<button type="button" class="page-btn' +
                    (i === state.page ? " active" : "") +
                    '" onclick="goToPage(' + i + ')">' +
                    (i + 1) +
                    "</button>"
            );
        }
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
                await loadLiveCatalogFromApi(false);
            }
        } catch (error) {
            apiOnline = false;
            apiStatus.textContent = "Offline";
            apiStatus.className = "status-badge offline";
        }
    }

    function doSearch() {
        searchResults.innerHTML = '<div class="loading-state">Searching catalog...</div>';
        searchPagination.innerHTML = "";

        var data = searchLocalCatalog(state.query || "*", state.category, state.difficulty, state.page, PAGE_SIZE);
        renderRecipeGrid(searchResults, data.results || []);
        renderPagination(data.total || 0);
        updateCatalogCount(data.total || 0);
        setStatusMessage(
            "Showing " + (data.total || 0) + " recipes from " + (catalogMode === "live" ? "live catalog" : "demo catalog"),
            catalogMode === "live" ? "success" : "warning"
        );
    }

    function loadRanking() {
        rankingResults.innerHTML = '<div class="loading-state">Loading ranking...</div>';
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
                await loadLiveCatalogFromApi(true);
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
        state.page = page;
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

    [filterCategory, filterDifficulty].forEach(function (select) {
        select.addEventListener("change", function () {
            runSearchFromInputs();
        });
    });

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
        }
    });

    loadDemoCatalog();
    loadFilterOptions();
    doSearch();
    checkHealth();
    setInterval(checkHealth, 30000);
});
