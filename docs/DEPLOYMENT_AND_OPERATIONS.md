# Deployment and Operations

## Variables principales

Voir `.env.example` pour la liste complète.

### Variables réellement utiles au runtime actuel
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
- `ENABLE_DOCS`
- `DEBUG_CAPTURE_HTML_ON_ERROR`
- `DEBUG_HTML_DUMP_DIR`
- `NEGATIVE_CACHE_ENABLED`
- `NEGATIVE_CACHE_TTL_SECONDS`

### Variables présentes mais non branchées sur des routes publiques aujourd'hui
- `ADMIN_TOKEN`
- `RATE_LIMIT_ENABLED`
- `RATE_LIMIT_REQUESTS`
- `RATE_LIMIT_WINDOW_SECONDS`
- `RATE_LIMIT_SCOPE`
- `RATE_LIMIT_INCLUDE_ADMIN`
- `RATE_LIMIT_EXEMPT_PATHS`

Elles existent dans la configuration et certains modules internes, mais ne correspondent pas à des routes/headers publics actifs dans cette version.

## Déploiement Docker

```bash
docker compose up -d --build
```

## Déploiement local Python

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8017
```

## Vérifications utiles

```bash
curl http://localhost:8017/health
curl http://localhost:8017/openapi.json
curl http://localhost:8017/docs
curl http://localhost:8017/redoc
```

## Cache

Le cache principal est SQLite.

### Réglages utiles
- `DB_PATH`
- `CACHE_TTL_*`
- `CACHE_STALE_GRACE_SECONDS`

### Comportement
- `search` : TTL court à moyen
- `series` : TTL journalier
- `volume` : TTL plus long
- `news` : TTL court
- `planning` : TTL intermédiaire

## Cache négatif

Le cache négatif est utile pour éviter de refrapper une ressource absente ou cassée juste après un premier échec.

Réglages :
- `NEGATIVE_CACHE_ENABLED=true|false`
- `NEGATIVE_CACHE_TTL_SECONDS=<seconds>`

## Dump HTML debug

Quand `DEBUG_CAPTURE_HTML_ON_ERROR=true`, le service peut sauver le HTML brut d'une page qui casse le parsing.

Réglages :
- `DEBUG_CAPTURE_HTML_ON_ERROR`
- `DEBUG_HTML_DUMP_DIR`

Exemple :

```env
DEBUG_CAPTURE_HTML_ON_ERROR=true
DEBUG_HTML_DUMP_DIR=/tmp/manga-news-debug-html
```

## Logs

`LOG_LEVEL` et `LOG_FORMAT` existent dans la configuration.
Le format actuel de l'application reste principalement piloté par `logging.basicConfig(...)` dans `app/main.py`.

## Diagnostic rapide par symptôme

### 1. `/docs` ou `/redoc` indisponible
Vérifie `ENABLE_DOCS=true`.

### 2. `401 Unauthorized`
Le plus souvent : `API_TOKEN` défini mais header Bearer absent ou incorrect.

### 3. `502 UPSTREAM_FETCH_ERROR`
Manga-News a pu répondre lentement, avec un code de panne, ou refuser temporairement.

Actions :
- augmenter `REQUEST_TIMEOUT_SECONDS` ;
- vérifier le réseau sortant ;
- relancer plus tard ;
- regarder les logs.

### 4. `502 UPSTREAM_PARSE_ERROR`
Le HTML source a probablement changé ou la page n'a pas la structure attendue.

Actions :
- activer `DEBUG_CAPTURE_HTML_ON_ERROR=true` ;
- inspecter le dump HTML ;
- écrire ou corriger un test de parser.

### 5. Résultats de recherche trop permissifs ou trop stricts
Ajuster `SEARCH_SCORE_THRESHOLD`.

## Validation doc/contrat

```bash
python scripts/validate_contract_and_docs.py
pytest -q
```
