# Déploiement et exploitation

Ce document couvre la mise en route, les variables utiles et les points d'attention opérationnels.

## 1. Modes d'exécution

### Local direct

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Docker Compose

```bash
docker compose up -d --build
```

Le compose actuel expose :
- conteneur : port `8000`
- hôte : port `8017`
- cache SQLite persistant : `./data`

## 2. Variables utiles aujourd'hui

Les variables ci-dessous ont un effet concret sur le runtime public actuel.

### Accès et source
- `API_TOKEN`
- `MANGA_NEWS_BASE_URL`
- `USER_AGENT`
- `DB_PATH`
- `ENABLE_DOCS`
- `LOG_LEVEL`

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

## 3. Variables présentes mais non branchées comme feature publique

Ces variables existent dans `Settings`, mais la version actuelle de l'application ne les exploite pas réellement dans les routes publiques :
- `ADMIN_TOKEN`
- `REQUEST_MAX_RETRIES`
- `REQUEST_BACKOFF_SECONDS`
- `DEFAULT_LIMIT`
- `LOG_FORMAT`
- `RATE_LIMIT_ENABLED`
- `RATE_LIMIT_REQUESTS`
- `RATE_LIMIT_WINDOW_SECONDS`
- `RATE_LIMIT_SCOPE`
- `RATE_LIMIT_INCLUDE_ADMIN`
- `RATE_LIMIT_EXEMPT_PATHS`

Conclusion pratique :
- tu peux les laisser dans `.env.example` ;
- mais ne construis pas ton exploitation en supposant qu'elles modifient déjà le comportement public actuel.

## 4. Configuration minimale recommandée

### Instance ouverte en LAN privé

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

### Instance plus robuste pour debug parsing

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

Avec Docker Compose par défaut, il sera sous :
- hôte : `./data/cache.sqlite3`
- conteneur : `/data/cache.sqlite3`

### Dumps HTML de debug
Si activés, ils iront dans `DEBUG_HTML_DUMP_DIR`.

Dans un conteneur, pense à :
- monter un volume si tu veux les conserver ;
- nettoyer périodiquement si le parsing casse souvent.

## 6. Vérifications post-déploiement

### Health

```bash
curl http://localhost:8017/health
```

### OpenAPI

```bash
curl http://localhost:8017/openapi.json
```

### Route métier simple

```bash
curl --get "http://localhost:8017/search" \
  --data-urlencode "q=one piece" \
  --data-urlencode "kind=series"
```

## 7. Interpréter les réponses

### 200 classique
L'upstream a été lu ou une entrée de cache fraîche a été servie.

### 304
Ton `If-None-Match` correspond au fingerprint actuel.

### 404 `RESOURCE_NOT_FOUND`
La ressource Manga News ciblée n'existe pas ou n'est plus accessible.

### 502 `UPSTREAM_PARSE_ERROR`
La page a répondu, mais le parser n'a pas réussi à en extraire un contrat fiable.

### 502 `UPSTREAM_FETCH_ERROR`
L'upstream a échoué côté réseau ou HTTP.

## 8. Symptômes fréquents

### “J'ai un 401 alors que l'API marche en local”
Cause la plus probable : `API_TOKEN` est défini sur le serveur mais pas dans ton client.

### “La réponse est partielle”
`partial=true` signifie qu'un cache stale a été utilisé parce que l'upstream a échoué. Lis `warnings`.

### “J'obtiens deux fois la même ParseError sans nouveau fetch”
C'est normal si le negative cache est actif et encore frais.

### “Je veux le HTML qui a cassé le parser”
Active `DEBUG_CAPTURE_HTML_ON_ERROR=true` et regarde `DEBUG_HTML_DUMP_DIR`.

### “Mes TTL ne semblent pas changer la recherche immédiatement”
Vérifie d'abord que la réponse ne vient pas d'une entrée existante déjà stockée.

## 9. Commandes de validation avant livraison

```bash
python scripts/validate_contract_and_docs.py
pytest
```

Tu peux aussi lancer le smoke test manuel décrit dans [`ONE_PIECE_API_TESTS.txt`](ONE_PIECE_API_TESTS.txt).

## 10. Conseils honnêtes d'exploitation

- garde l'API derrière ton reverse proxy ou ton LAN, pas en exposition publique brute ;
- active `API_TOKEN` si plusieurs clients l'utilisent ;
- conserve les docs Swagger en dev, mais désactive-les si tu préfères limiter la surface visible ;
- n'essaie pas de piloter une politique d'ops à partir des variables `RATE_LIMIT_*` tant qu'elles ne sont pas branchées ;
- si tu t'appuies fortement sur cette API, surveille surtout les `UPSTREAM_PARSE_ERROR` : c'est le vrai point de fragilité quand Manga News change son HTML.

## 7. Cache et mises à jour de parseur

Quand un parseur change (par exemple pour mieux lire `#numberblock`), il faut redémarrer l'API.
Les clés de cache métier intègrent une version interne afin d'éviter la réutilisation silencieuse d'anciens payloads incompatibles.

En cas de doute lors d'un déploiement, tu peux aussi supprimer le fichier SQLite de cache pour repartir d'un état vierge.
