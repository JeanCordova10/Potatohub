# PotatoHub

PotatoHub is a local web app for exploring potato-centered recipes, built from live scraping and a small recommendation graph.

The project has three core ideas:

1. Scraping recipes from Cookpad and Recetas Gratis to build the dataset.
2. MongoDB as the main operational store for the catalog.
3. Neo4j as the recommendation layer, using ingredient similarity and recipe type.

The app still runs locally without those external services. In that mode it uses `data/recipes.json` as the local persistence file so the UI keeps working.

## What the project does

- Scrapes recipe data from live sources.
- Normalizes each recipe into a common schema.
- Lets the frontend search by text, category, and difficulty.
- Refreshes the catalog from live sources.
- Records simple interactions like views and saves.
- Generates recommendations from the catalog, or from Neo4j when it is enabled.
- Opens the full recipe view with ingredients, instructions, metadata, and source link.

## Architecture

### Scraping

The scraping pipeline pulls recipes from:

- Cookpad
- Recetas Gratis

The scraper is used to generate a dataset. For this project, the scraped potato recipes are the seed and refresh source for the catalog.

### Storage

The project has a layered storage model:

- Local JSON file: default persistence for development.
- MongoDB: operational catalog store when sync is enabled.
- Neo4j: graph model for recommendation queries when sync is enabled.

### Neo4j model

Neo4j stores the catalog as a graph with:

- `(:Recipe)`
- `(:Ingredient)`
- `(:Category)`
- `(:Difficulty)`

Relationships:

- `(:Recipe)-[:USES]->(:Ingredient)`
- `(:Recipe)-[:IN_CATEGORY]->(:Category)`
- `(:Recipe)-[:HAS_DIFFICULTY]->(:Difficulty)`

Recommendation modes:

- `hybrid`: combines ingredient overlap and recipe type
- `ingredients`: prioritizes shared ingredients
- `type`: prioritizes recipe category/type

## Local run

### 1. Install dependencies

```bash
py -3 -m pip install -r requirements.txt
```

### 2. Start local databases

```bash
docker compose -f docker-compose.local.yml up -d
```

This starts:

- MongoDB on `mongodb://127.0.0.1:27017`
- Neo4j on `bolt://127.0.0.1:7687`

### 3. Run the API against local services

PowerShell:

```powershell
$env:MONGO_URI='mongodb://127.0.0.1:27017'
$env:MONGO_DB='potatohub'
$env:NEO4J_URI='bolt://127.0.0.1:7687'
$env:NEO4J_USER='neo4j'
$env:NEO4J_PASSWORD='potatohub123'
$env:ENABLE_MONGO_SYNC='true'
$env:ENABLE_NEO4J_SYNC='true'
py -3 -m uvicorn app.main:app --host 127.0.0.1 --port 8002
```

Open:

```text
http://127.0.0.1:8002
```

## Optional services

Enable these only if you have the containers or local services running:

- `ENABLE_MONGO_SYNC=true`
- `ENABLE_NEO4J_SYNC=true`
- `ENABLE_REDIS_CACHE=true`

The default local setup keeps them off so the app can run with the JSON store only.

## API

### Health

`GET /health`

### Search

`GET /api/recipes/search?q=&category=&difficulty=&page=&size=`

### Refresh catalog

`POST /api/recipes/refresh`

### Filters

`GET /api/recipes/filters`

Returns the available categories, difficulties, and sources currently in the catalog.

### Recipe detail

`GET /api/recipes/{recipe_id}`

### Interactions

`POST /api/recipes/{recipe_id}/interact`

Payload:

```json
{ "action": "view" }
```

or

```json
{ "action": "save" }
```

### Recommendations

`GET /api/recipes/{recipe_id}/recommendations?limit=6&mode=hybrid`

Supported modes:

- `hybrid`
- `ingredients`
- `type`

### Ranking

`GET /api/recipes/ranking/{period}`

## Frontend behavior

The frontend is wired to real backend actions:

- Search runs against the API.
- Category and difficulty filters reload the result set.
- Refresh triggers a fresh scrape and catalog replacement.
- Recommendation buttons call the recommendation endpoint.
- If the API is not available, the frontend falls back to a built-in demo catalog so the layout and buttons can still be tested locally.

## Project layout

- `app/main.py`: FastAPI app bootstrap
- `app/database.py`: local recipe repository
- `app/models.py`: Pydantic models
- `app/routers/`: API routes
- `app/services/`: MongoDB, Redis, Neo4j, and sync wrappers
- `etl/`: scrapers, transformer, and Neo4j loader
- `frontend/`: single-page UI

## Notes

- The app can run without MongoDB and Neo4j.
- When Neo4j is enabled, the recommendation endpoint prefers graph queries and falls back to the in-memory catalog logic if needed.
- Scraping is meant to build and refresh the catalog, not to replace the recommendation layer.

## How to verify the data source

If you want to confirm whether the app is using local storage, MongoDB, or Neo4j, check the health endpoint:

```text
GET /health
```

The response includes:

- `storage_file`: the local JSON file used by the repository
- `mongo_enabled` and `mongo_status`
- `neo4j_enabled` and `neo4j_status`

In the default local setup:

- MongoDB is disabled unless you set `ENABLE_MONGO_SYNC=true`
- Neo4j is disabled unless you set `ENABLE_NEO4J_SYNC=true`
- data is always persisted in `data/recipes.json` for local fallback

When the local databases are running and the API is started with the env vars above, `health` should report:

- `mongo_enabled: true`
- `neo4j_enabled: true`
- `mongo_status: connected`
- `neo4j_status: connected`

You can also verify the payload directly with:

```text
GET /api/recipes/search?q=*&page=0&size=1
```

That response returns a recipe object with:

- `ingredients`
- `instructions`
- `source_name`
- `source_url`

So the catalog is not hardcoded in the frontend. The frontend only renders data from the backend.

## Full recipe view

The catalog card is just the preview. Use `Ver receta` to open the full recipe detail view, which shows:

- image
- description
- ingredients
- instructions
- stats
- source link
- tags

Recommendations can still be opened from the card or from the recipe detail modal.
