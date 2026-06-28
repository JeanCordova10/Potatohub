# PotatoHub

Plataforma NoSQL de recetas de papa. En su estado actual, el proyecto esta centrado en un ETL que scrapea recetas desde Cookpad PE, las guarda en MongoDB y luego puede enriquecer cada receta con ingredientes e instrucciones.

## Estado actual

- La fuente activa de scraping es solo Cookpad.
- El ETL guarda resultados en MongoDB de forma idempotente.
- Hay un segundo paso opcional para entrar a cada receta y extraer detalle.
- La API existe, pero por ahora solo expone `GET /health`.
- `redis` y `neo4j` siguen declarados en `docker-compose.yml`, pero no participan en el scraper actual.

## Flujo del proyecto

El flujo real hoy es este:

1. `etl/run_etl.py` busca recetas en las paginas de resultados de Cookpad.
2. `etl/scraper.py` extrae `title` y `source_url` de cada receta encontrada.
3. `etl/transformer.py` normaliza cada resultado a un documento comun.
4. `etl/mongo_loader.py` inserta solo recetas nuevas en MongoDB.
5. `etl/enrich_recipes.py` entra a cada receta ya guardada y extrae ingredientes e instrucciones.

## Estructura importante

- `etl/config.py`: terminos de busqueda, headers HTTP, rate limit y categorias.
- `etl/scraper.py`: scraper de listados de Cookpad.
- `etl/transformer.py`: limpieza y normalizacion de datos.
- `etl/mongo_loader.py`: insercion idempotente en MongoDB.
- `etl/enrich_recipes.py`: scraping de detalle por receta.
- `etl/debug_scraper.py`: utilidades para inspeccionar selectores de Cookpad.
- `etl/check_db.py`: chequeo rapido de lo que se guardo en Mongo.
- `app/main.py`: API minima.

## Requisitos

- Docker y Docker Compose
- Python 3.11
- Dependencias de `requirements.txt`

## Variables de entorno

El repo ya usa estas variables en `.env`:

```env
MONGO_URI=mongodb://mongo1:27017,mongo2:27017,mongo3:27017/?replicaSet=potatohubRS
MONGO_DB=potatohub
REDIS_URL=redis://redis:6379
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=potatohub123
MONGO_URI_LOCAL=mongodb://localhost:27017/?directConnection=true
```

`run_etl.py` y `enrich_recipes.py` usan `MONGO_URI_LOCAL`, porque estan pensados para ejecutarse desde tu maquina local y conectarse a Mongo por `localhost:27017`.

## Como levantar el entorno

Si solo quieres correr el ETL, lo importante es MongoDB.

Levantar Mongo con Docker:

```powershell
docker compose up -d mongo1 mongo2 mongo3 mongo-init
```

Si quieres levantar todo lo declarado en el compose:

```powershell
docker compose up -d
```

## Como instalar dependencias

Si no tienes entorno virtual creado:

```powershell
python -m venv venv
```

Activar entorno virtual en PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
```

Instalar dependencias:

```powershell
pip install -r requirements.txt
```

## Como ejecutar el ETL

Con el entorno virtual activado:

```powershell
python -m etl.run_etl
```

O directamente con el Python del entorno virtual:

```powershell
.\venv\Scripts\python.exe -m etl.run_etl
```

Este paso:

- recorre los terminos definidos en `COOKPAD_TERMS`
- visita las paginas de busqueda de Cookpad
- extrae recetas del listado
- transforma cada item
- inserta solo las nuevas

## Como enriquecer recetas con detalle

Despues del ETL base, puedes extraer ingredientes y pasos:

```powershell
python -m etl.enrich_recipes
```

Ese script:

- busca recetas de `cookpad_pe` que aun tienen `ingredients = []`
- entra a la URL de cada receta
- extrae ingredientes con el selector `[id^="ingredient_"]`
- extrae pasos con el selector `[id^="step_"]`
- actualiza el documento en Mongo

## Como revisar la base de datos

```powershell
python etl\check_db.py
```

Sirve para ver:

- total de recetas
- recetas por fuente
- recetas por categoria
- ejemplos guardados
- cuantas ya tienen ingredientes

## Como funciona el scraper

### 1. Scraping de listado

El scraper de listado esta en `etl/scraper.py` y sigue este patron:

1. Construye la URL de busqueda.
2. Hace el request con headers de navegador normal.
3. Parsea el HTML con BeautifulSoup.
4. Busca todos los links que parezcan recetas.
5. Filtra solo los links validos.
6. Convierte cada resultado en un diccionario simple.
7. Espera unos segundos antes de pasar a la siguiente pagina.

En este proyecto, la URL se arma asi:

```python
url = f"https://cookpad.com/pe/buscar/{term}?page={page}"
```

Luego el codigo busca anchors que contengan `/recetas/`:

```python
todos_links = soup.select('a[href*="/recetas/"]')
```

Y filtra solo rutas con ID numerico:

```python
re.search(r"/recetas/\d+", href)
```

Eso evita meter links que no son recetas reales.

### 2. Estructura minima de cada resultado

Cada item crudo sale asi:

```python
{
    "title": "...",
    "source_url": "...",
    "source": "cookpad_pe",
    "search_term": term,
    "lang": "es",
    "country": "PE",
}
```

La idea es separar bien:

- lo que el scraper encuentra
- lo que el transformador normaliza
- lo que Mongo inserta

## Como funciona la transformacion

`etl/transformer.py` toma cada item crudo y:

- genera `_id = md5(source_url)` para evitar duplicados
- clasifica la receta segun palabras clave
- crea campos vacios para enriquecer despues
- agrega timestamps

Esto permite que el scraper de listado sea simple y que el documento final mantenga una estructura estable.

## Como funciona la insercion en Mongo

`etl/mongo_loader.py` usa `UpdateOne(..., upsert=True)` con `$setOnInsert`.

Eso significa:

- si la receta no existe, la inserta
- si la receta ya existe, no la pisa

La deduplicacion depende de `_id`, que se calcula a partir de la URL. Si la URL no cambia, no se duplica.

## Como funciona el scraping de detalle

`etl/enrich_recipes.py` hace una segunda pasada, porque las paginas de listado no traen toda la informacion.

El patron es:

1. Leer de Mongo recetas incompletas.
2. Entrar a la URL individual de cada receta.
3. Buscar selectores mas estables del detalle.
4. Actualizar solo los campos enriquecidos.

En Cookpad se usan estos selectores:

- ingredientes: `[id^="ingredient_"]`
- pasos: `[id^="step_"]`

Esto es mejor que intentar sacar todo desde el listado, porque:

- el listado casi nunca trae ingredientes completos
- el HTML de detalle suele tener selectores mas claros
- puedes reintentar solo el enriquecimiento sin repetir todo el ETL

## Como adaptar este scraper a otra web

Si tu o tu amigo quieren hacer lo mismo en otra pagina, el proceso recomendado es este:

1. Identificar la URL de listado o busqueda.
2. Revisar la paginacion.
3. Encontrar un selector estable para los links de receta.
4. Extraer primero solo `title` y `source_url`.
5. Guardar resultados crudos con una estructura minima comun.
6. Crear un segundo scraper para el detalle.
7. Insertar con deduplicacion por URL.
8. Agregar rate limit y condiciones de corte.

Regla practica:

- listado = descubrir recetas
- detalle = enriquecer recetas

No mezcles ambas cosas al inicio. Separarlas hace que el scraper sea mas facil de depurar y mantener.

## Buenas practicas que ya usa este proyecto

- Headers HTTP parecidos a un navegador real.
- `timeout` y `follow_redirects=True`.
- `time.sleep()` entre requests.
- Corte temprano si una pagina no responde o ya no trae recetas.
- Dedupe por URL.
- Scraper de listado separado del scraper de detalle.
- Debug aislado en `etl/debug_scraper.py`.

## Consejos para explicarselo a otra persona

Si tienes que explicarselo a tu amigo, la version corta es esta:

1. El scraper primero busca recetas en paginas de resultados.
2. De cada resultado saca titulo y URL.
3. Guarda eso en Mongo sin duplicar.
4. Luego entra a cada receta para sacar ingredientes y pasos.
5. Separar listado y detalle hace que el scraper sea mas estable.

## Limitaciones actuales

- El proyecto depende de que Cookpad no cambie su HTML.
- El enriquecimiento usa selectores especificos de Cookpad.
- La API todavia no expone consultas reales de recetas.
- Redis y Neo4j aun no estan integrados al flujo actual.
