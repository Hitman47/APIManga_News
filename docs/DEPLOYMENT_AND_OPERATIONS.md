# Déploiement et exploitation

Ce document couvre le démarrage, la configuration et les points d'attention opérationnels du projet actuel.

## 1. Modes d'exécution

### Local direct

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8017
```

### Docker Compose

```bash
docker compose up -d --build
```

Par défaut :
- conteneur : port `8000` ;
- hôte : port `8017` ;
- cache SQLite : `./data/cache.sqlite3`.

## 2. Variables utiles aujourd'hui

### Accès et source
- `API_TOKEN`
- `MANGA_NEWS_BASE_URL`
- `USER_AGENT`
- `DB_PATH`
- `ENABLE_DOCS`
- `LOG_LEVEL`
- `LOG_FORMAT`

### Réseau et fetch
- `REQUEST_TIMEOUT_SECONDS`
- `REQUEST_MAX_RETRIES`
- `REQUEST_BACKOFF_SECONDS`

### Cache et fraîcheur
- `CACHE_STALE_GRACE_SECONDS`
- `CACHE_TTL_SEARCH_SECONDS`
- `CACHE_TTL_SERIES_SECONDS`
- `CACHE_TTL_VOLUME_SECONDS`
- `CACHE_TTL_NEWS_GLOBAL_SECONDS`
- `CACHE_TTL_NEWS_SERIES_SECONDS`
- `CACHE_TTL_PLANNING_SECONDS`

### Recherche
- `SEARCH_SCORE_THRESHOLD`
- `MAX_LIMIT`

### Debug et robustesse de parsing
- `DEBUG_CAPTURE_HTML_ON_ERROR`
- `DEBUG_HTML_DUMP_DIR`
- `NEGATIVE_CACHE_ENABLED`
- `NEGATIVE_CACHE_TTL_SECONDS`

## 3. Variables présentes mais non utilisées comme contrat public

Ces variables existent dans `Settings`, mais le projet actuel ne les expose pas comme comportement public documenté :
- `ADMIN_TOKEN`
- `DEFAULT_LIMIT`
- `RATE_LIMIT_ENABLED`
- `RATE_LIMIT_REQUESTS`
- `RATE_LIMIT_WINDOW_SECONDS`
- `RATE_LIMIT_SCOPE`
- `RATE_LIMIT_INCLUDE_ADMIN`
- `RATE_LIMIT_EXEMPT_PATHS`

Tu peux les laisser dans `.env.example`, mais ne construis pas ton exploitation publique dessus tant que le code des routes n'en dépend pas explicitement.

## 4. Configurations minimales recommandées

### Instance locale simple

```env
API_TOKEN=
DB_PATH=/data/cache.sqlite3
ENABLE_DOCS=true
SEARCH_SCORE_THRESHOLD=60
MAX_LIMIT=50
```

### Instance protégée par token

```env
API_TOKEN=mon_token_secret
DB_PATH=/data/cache.sqlite3
ENABLE_DOCS=true
```

### Instance de debug parsing

```env
API_TOKEN=mon_token_secret
DEBUG_CAPTURE_HTML_ON_ERROR=true
DEBUG_HTML_DUMP_DIR=/tmp/manga-news-debug-html
NEGATIVE_CACHE_ENABLED=true
NEGATIVE_CACHE_TTL_SECONDS=120
```

## 5. Fichiers persistants

### Cache SQLite
Le cache vit dans `DB_PATH`.

Avec le compose par défaut :
- hôte : `./data/cache.sqlite3`
- conteneur : `/data/cache.sqlite3`

### Dumps HTML de debug
Si activés, ils sont écrits dans `DEBUG_HTML_DUMP_DIR`.

En conteneur, monte un volume si tu veux les conserver ou les analyser hors conteneur.

## 6. Vérifications post-déploiement

### Santé

```bash
curl http://localhost:8017/health
```

### OpenAPI

```bash
curl http://localhost:8017/openapi.json
```

### Recherche simple

```bash
curl --get "http://localhost:8017/search" \
  --data-urlencode "q=one piece" \
  --data-urlencode "kind=series"
```

## 7. Interpréter les réponses

### 200 classique
L'upstream a été lu ou une entrée de cache fraîche a été servie.

### 304
L'`ETag` envoyé dans `If-None-Match` correspond encore au fingerprint courant.

### 404 `RESOURCE_NOT_FOUND`
La ressource ciblée n'existe pas ou n'est plus accessible sur Manga News.

### 502 `UPSTREAM_PARSE_ERROR`
La page a répondu, mais le parser n'a pas réussi à extraire un contrat fiable.

### 502 `UPSTREAM_FETCH_ERROR`
L'upstream a échoué côté réseau, HTTP ou contenu vide.

## 8. Symptômes fréquents

### “J'ai un 401 alors que l'API tourne”
Cause probable : `API_TOKEN` est défini côté serveur mais pas transmis côté client.

### “La réponse est partielle”
`partial=true` signifie qu'une entrée stale a été servie. Lis aussi `warnings`.

### “Je reçois deux fois la même ParseError sans nouveau fetch”
C'est normal si le negative cache est actif et encore frais.

### “Je veux le HTML qui a cassé le parser”
Active `DEBUG_CAPTURE_HTML_ON_ERROR=true` et consulte `DEBUG_HTML_DUMP_DIR`.

### “Je change mes TTL mais je ne vois pas immédiatement l'effet”
Une entrée positive déjà en cache reste valable jusqu'à son expiration, sauf si tu repars d'un cache vide.

## 9. Coût d'une recherche enrichie

Une recherche série peut relire la fiche détaillée du résultat retenu pour enrichir la réponse avec :
- `title_vo` ;
- `translated_title` ;
- `vf` / `vo` avec nombre de tomes et statut.

Conséquence pratique :
- `mode=all` avec beaucoup de résultats peut faire plus de fetchs qu'une simple recherche HTML brute ;
- `mode=best` reste le choix le plus léger quand tu veux juste un meilleur candidat.

## 10. Conseils d'exploitation

- garde l'API derrière ton LAN ou un reverse proxy ;
- active `API_TOKEN` si plusieurs clients l'utilisent ;
- garde `/docs` et `/redoc` en dev ;
- si tu t'appuies fortement sur cette API, surveille surtout les `UPSTREAM_PARSE_ERROR` ;
- documente côté client que le planning n'est pas une API exhaustive, mais le parsing d'une page donnée.

## 11. Validation avant livraison

```bash
python scripts/validate_contract_and_docs.py
pytest
```

Tests manuels prêts à l'emploi : [`ONE_PIECE_API_TESTS.txt`](ONE_PIECE_API_TESTS.txt).
