# Déploiement et exploitation

Ce document couvre la partie opérateur : lancement, configuration, cache, retries, diagnostic et validation locale.

## 1. Modes de lancement

### 1.1 Local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8017 --reload
```

### 1.2 Docker Compose

```bash
cp .env.example .env
docker compose up -d --build
```

Arrêt :

```bash
docker compose down
```

Rebuild complet :

```bash
docker compose down
docker compose up -d --build
```

## 2. Variables d'environnement utiles aujourd'hui

Toutes les variables déclarées vivent dans `.env.example`, mais toutes n'ont pas la même importance opérationnelle.

### 2.1 Réglages réellement actifs et utiles

- `APP_NAME`
- `APP_ENV`
- `LOG_LEVEL`
- `LOG_FORMAT`
- `MANGA_NEWS_BASE_URL`
- `USER_AGENT`
- `API_TOKEN`
- `DB_PATH`
- `REQUEST_TIMEOUT_SECONDS`
- `REQUEST_MAX_RETRIES`
- `REQUEST_BACKOFF_SECONDS`
- `CACHE_STALE_GRACE_SECONDS`
- `CACHE_TTL_SEARCH_SECONDS`
- `CACHE_TTL_SERIES_SECONDS`
- `CACHE_TTL_VOLUME_SECONDS`
- `CACHE_TTL_NEWS_GLOBAL_SECONDS`
- `CACHE_TTL_NEWS_SERIES_SECONDS`
- `CACHE_TTL_PLANNING_SECONDS`
- `SEARCH_SCORE_THRESHOLD`
- `DEFAULT_LIMIT`
- `MAX_LIMIT`
- `ENABLE_DOCS`

### 2.2 Réglages présents dans la config mais non exposés comme feature publique aujourd'hui

- `ADMIN_TOKEN`
- `ENABLE_LEGACY_ROUTES`
- `DEBUG_CAPTURE_HTML_ON_ERROR`
- `DEBUG_HTML_DUMP_DIR`
- `NEGATIVE_CACHE_ENABLED`
- `NEGATIVE_CACHE_TTL_SECONDS`
- `RATE_LIMIT_ENABLED`
- `RATE_LIMIT_REQUESTS`
- `RATE_LIMIT_WINDOW_SECONDS`
- `RATE_LIMIT_SCOPE`
- `RATE_LIMIT_INCLUDE_ADMIN`
- `RATE_LIMIT_EXEMPT_PATHS`

Tu peux les voir dans la config, mais ils ne correspondent pas aujourd'hui à des routes admin publiques ou à un middleware activé dans `app.main`.

## 3. Recommandations simples

### 3.1 Profil local simple

```env
API_TOKEN=
ENABLE_DOCS=true
LOG_LEVEL=INFO
```

### 3.2 Profil serveur privé raisonnable

```env
API_TOKEN=replace-me
ENABLE_DOCS=true
LOG_LEVEL=INFO
REQUEST_TIMEOUT_SECONDS=20
REQUEST_MAX_RETRIES=2
REQUEST_BACKOFF_SECONDS=0.5
CACHE_TTL_SEARCH_SECONDS=86400
CACHE_TTL_SERIES_SECONDS=86400
CACHE_TTL_VOLUME_SECONDS=604800
CACHE_TTL_NEWS_GLOBAL_SECONDS=21600
CACHE_TTL_NEWS_SERIES_SECONDS=43200
CACHE_TTL_PLANNING_SECONDS=43200
```

## 4. Ce que le cache fait vraiment

Le service utilise un cache SQLite pour éviter de refrapper Manga News à chaque appel.

Répartition utile :
- `search` et `series` : TTL d'environ 24h par défaut ;
- `volume` : TTL plus long, environ 7 jours ;
- `news` et `planning` : TTL plus court ;
- `CACHE_STALE_GRACE_SECONDS` : combien de temps un cache expiré peut encore servir de fallback si l'upstream casse.

## 5. Retries et tolérance réseau

Réglages utiles :
- `REQUEST_TIMEOUT_SECONDS` : temps max d'attente par requête amont ;
- `REQUEST_MAX_RETRIES` : nombre de retries amont ;
- `REQUEST_BACKOFF_SECONDS` : base du backoff entre retries.

Recommandation réaliste :
- ne mets pas un timeout énorme ;
- préfère un timeout raisonnable + quelques retries ;
- garde un `USER_AGENT` explicite.

## 6. Docs interactives et contrat machine-readable

Si `ENABLE_DOCS=true` :
- Swagger : `/docs`
- ReDoc : `/redoc`
- OpenAPI : `/openapi.json`

Si `ENABLE_DOCS=false` :
- `/docs` et `/redoc` disparaissent ;
- `/openapi.json` reste le meilleur point d'entrée pour une intégration automatique.

## 7. Smoke tests et validation locale

### 7.1 Script batch

```bash
python scripts/run_api_smoke_tests.py --base-url "http://localhost:8017" --token "$TOKEN"
```

### 7.2 Validation contrat + doc

```bash
python scripts/validate_contract_and_docs.py
```

### 7.3 Tests projet

```bash
pytest
```

## 8. Diagnostic rapide par symptôme

### Symptôme : `401`

Cause probable :
- token absent ;
- mauvais token.

À vérifier :
- header `Authorization` ;
- valeur de `API_TOKEN`.

### Symptôme : `404`

Cause probable :
- slug inconnu ;
- page réellement absente côté Manga News ;
- URL `/by-url` pointant sur une ressource supprimée.

À vérifier :
- l'URL Manga News réelle ;
- le slug résolu par `/search/resolve`.

### Symptôme : `502`

Cause probable :
- incident réseau ;
- timeout amont ;
- HTML amont modifié ;
- parser non adapté à une nouvelle structure.

À faire :
1. vérifier la connectivité sortante ;
2. vérifier `REQUEST_TIMEOUT_SECONDS`, `REQUEST_MAX_RETRIES`, `REQUEST_BACKOFF_SECONDS` ;
3. reproduire le cas avec une requête ciblée ;
4. ajouter ou adapter une fixture de test si le HTML a changé.

### Symptôme : `304`

Cause probable :
- le client renvoie le bon `If-None-Match` ;
- le `fingerprint` n'a pas changé.

Comportement attendu :
- corps vide ;
- réutilisation de la copie locale côté client.

## 9. Ce qu'il faut éviter de supposer

- n'invente pas de namespace `/v1` ;
- n'invente pas de routes admin ;
- ne pars pas du principe que `LOG_FORMAT=json` produit déjà des logs JSON structurés ;
- ne suppose pas que tous les champs métier seront toujours remplis.

## 10. Fichiers utiles pour l'exploitation

- [`../README.md`](../README.md)
- [`API_INTEGRATION.md`](API_INTEGRATION.md)
- [`OPENAPI_AND_AI_USAGE.md`](OPENAPI_AND_AI_USAGE.md)
- [`ONE_PIECE_API_TESTS.txt`](ONE_PIECE_API_TESTS.txt)
- [`examples/README.md`](examples/README.md)
