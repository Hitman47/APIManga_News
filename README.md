# Manga News Private API

API non officielle, auto-hébergeable, qui expose en JSON des données publiques de Manga-News.

## Ce que l'API fait maintenant

- contrat canonique sous `/v1/...`
- routes legacy non versionnées désactivées par défaut
- cache SQLite persistant
- cache négatif court pour éviter de retaper en boucle une ressource cassée ou inexistante
- token public et token admin séparés
- ETag / `If-None-Match`
- erreurs machine-readable avec `code` stable
- pagination structurée sur les endpoints de liste
- normalisation volume renforcée : `number`, `number_int`, `edition_label`, `is_special`, `is_one_shot`
- rate limiting configurable via `.env`, variables d'environnement ou compose
- endpoint admin de métriques
- capture optionnelle du HTML brut lors d'un échec de parsing
- script de smoke tests prêt à lancer

## Contrat d'API

Utilise uniquement les routes `/v1/...`.

Exemples :
- `/v1/health`
- `/v1/search`
- `/v1/search/resolve`
- `/v1/lookup/volume`
- `/v1/series/{slug}`
- `/v1/volume/{series_slug}/{volume_slug}`
- `/v1/news/global`
- `/v1/planning`
- `/v1/admin/cache/stats`
- `/v1/admin/metrics`

### Pourquoi il y avait des doublons `/v1/...` et non versionnés

Il n'y avait pas de différence métier. Les routes non versionnées servaient uniquement de compatibilité ancienne. Elles sont maintenant bloquées par défaut.

Pour les réactiver explicitement :

```env
ENABLE_LEGACY_ROUTES=true
```

En pratique, pour un nouveau client, il n'y a aucune bonne raison d'utiliser autre chose que `/v1`.

## Installation locale

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8017
```

API disponible sur `http://localhost:8017`.

## Docker Compose

```bash
docker compose up -d --build
```

### Changements explicites faits dans le compose

J'ai ajouté ces variables dans `docker-compose.yml` :
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

Pourquoi :
- avant, une partie des comportements utiles était cachée dans le code ;
- maintenant, tout ce qui compte côté exploitation est réglable par stack ou `.env`.

## Variables d'environnement utiles

Voir `.env.example` pour la liste complète.

Les plus importantes :
- `API_TOKEN` : token Bearer des endpoints publics
- `ADMIN_TOKEN` : token Bearer des endpoints admin ; si vide, fallback sur `API_TOKEN`
- `DB_PATH` : chemin du cache SQLite
- `CACHE_TTL_*` : TTL par famille de données
- `CACHE_STALE_GRACE_SECONDS` : durée d'utilisation du stale cache en fallback
- `NEGATIVE_CACHE_ENABLED` : active le cache négatif
- `NEGATIVE_CACHE_TTL_SECONDS` : durée du cache négatif
- `DEBUG_CAPTURE_HTML_ON_ERROR` : sauvegarde le HTML brut lors d'un échec de parsing
- `DEBUG_HTML_DUMP_DIR` : dossier de dump du HTML de debug
- `REQUEST_MAX_RETRIES` et `REQUEST_BACKOFF_SECONDS` : robustesse réseau vers Manga-News
- `ENABLE_LEGACY_ROUTES` : réactive les routes non versionnées
- `RATE_LIMIT_ENABLED` : active le rate limiting
- `RATE_LIMIT_REQUESTS` et `RATE_LIMIT_WINDOW_SECONDS` : quota et fenêtre
- `RATE_LIMIT_SCOPE` : `ip`, `token`, `ip_or_token`
- `RATE_LIMIT_INCLUDE_ADMIN` : inclure ou non les routes admin
- `RATE_LIMIT_EXEMPT_PATHS` : chemins exemptés

## Headers utiles

Les réponses peuvent exposer :
- `ETag: "<fingerprint>"`
- `X-Data-Fingerprint: <fingerprint>`
- `X-Cache-Status: MISS|HIT|STALE`
- `X-Request-ID: <id>`
- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Reset`
- `Retry-After` si `429`

## Format d'erreur

```json
{
  "ok": false,
  "code": "INVALID_REQUEST",
  "detail": "Unknown volume field path: bogus"
}
```

Codes principaux :
- `INVALID_REQUEST`
- `AUTH_REQUIRED`
- `RESOURCE_NOT_FOUND`
- `UPSTREAM_FETCH_ERROR`
- `UPSTREAM_PARSE_ERROR`
- `RATE_LIMITED`
- `ENDPOINT_NOT_FOUND`

## Pagination structurée

Les endpoints de liste renvoient un bloc `pagination`.

```json
{
  "pagination": {
    "page": 1,
    "limit": 10,
    "returned": 10,
    "total": 34,
    "has_more": true
  }
}
```

Appliqué à :
- `/v1/search`
- `/v1/search/resolve`
- `/v1/news/*`
- `/v1/planning`
- `/v1/lookup/volume`

## Normalisation volume

Les payloads volume exposent notamment :

```json
{
  "number": "91",
  "number_int": 91,
  "edition_label": "edition_originale",
  "is_special": false,
  "is_one_shot": null
}
```

## Cache négatif

Le cache négatif évite de re-solliciter immédiatement Manga-News quand une ressource est :
- inexistante
- temporairement cassée
- impossible à parser

C'est volontairement court. Le but n'est pas de masquer durablement un problème, juste d'éviter les rafales inutiles.

Réglage minimal :

```env
NEGATIVE_CACHE_ENABLED=true
NEGATIVE_CACHE_TTL_SECONDS=120
```

## Capture HTML de debug sur erreur de parsing

Quand `DEBUG_CAPTURE_HTML_ON_ERROR=true`, l'API sauvegarde :
- le HTML brut ayant échoué
- un fichier JSON compagnon avec l'URL, le parser et l'erreur

Exemple :

```env
DEBUG_CAPTURE_HTML_ON_ERROR=true
DEBUG_HTML_DUMP_DIR=/tmp/manga-news-debug-html
```

Usage réel :
- tu actives ça seulement quand Manga-News change son HTML ou quand un parser casse ;
- tu regardes le dump ;
- tu corriges le parseur ;
- tu peux ensuite le désactiver.

## Endpoint admin de métriques

Route :
- `GET /v1/admin/metrics`

Cette route expose des compteurs simples, utiles en exploitation :
- réponses HTTP par classe
- hits/misses de cache
- stale fallbacks
- hits de cache négatif
- erreurs de parsing
- erreurs upstream
- nombre de `429`
- ratios dérivés (`cache_hit_ratio`, `negative_cache_hit_ratio`, `upstream_error_ratio`)

## Endpoint admin de cache

Routes :
- `GET /v1/admin/cache/stats`
- `POST /v1/admin/cache/invalidate`

`/v1/admin/cache/stats` expose :
- stats du cache principal
- stats du cache négatif
- stats des snapshots watch

## Requêtes rapides

### Santé

```bash
curl http://localhost:8017/v1/health
```

### Résoudre un volume directement

```bash
curl "http://localhost:8017/v1/lookup/volume?series=One%20Piece&number=91"
```

### Charger une série

```bash
curl "http://localhost:8017/v1/series/One-piece-Edition-originale"
```

### Charger un volume

```bash
curl "http://localhost:8017/v1/volume/One-Piece/vol-91"
```

### Planning filtré

```bash
curl --get "http://localhost:8017/v1/planning" \
  --data-urlencode "section=manga-vf" \
  --data-urlencode "publisher=Glénat" \
  --data-urlencode "q=one piece" \
  --data-urlencode "sort=date_desc" \
  --data-urlencode "limit=10"
```

## Smoke tests One Piece

Fichiers utiles :
- `docs/ONE_PIECE_API_TESTS.txt`
- `scripts/run_api_smoke_tests.py`

### 1) Démarrer l'API

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8017
```

ou :

```bash
docker compose up -d --build
```

### 2) Vérifier que l'API répond

```bash
curl http://localhost:8017/v1/health
```

### 3) Lancer le batch de tests

Linux / macOS :

```bash
export BASE_URL="http://localhost:8017/v1"
export TOKEN="ton_token_public"
export ADMIN_TOKEN="ton_token_admin"
python scripts/run_api_smoke_tests.py --base-url "$BASE_URL" --token "$TOKEN" --admin-token "$ADMIN_TOKEN"
```

Windows PowerShell :

```powershell
$env:BASE_URL = "http://localhost:8017/v1"
$env:TOKEN = "ton_token_public"
$env:ADMIN_TOKEN = "ton_token_admin"
python .\scripts\run_api_smoke_tests.py --base-url $env:BASE_URL --token $env:TOKEN --admin-token $env:ADMIN_TOKEN
```

### 4) Où lire les sorties

Par défaut, le script écrit des fichiers JSON dans `api_test_outputs/`.

S'il n'a pas les droits d'écriture, il tente automatiquement :
- le dossier demandé
- un dossier à côté du script
- le dossier temporaire système

Tu peux aussi forcer le dossier :

```bash
python scripts/run_api_smoke_tests.py --output-dir /tmp/api_test_outputs
```

Ou désactiver complètement l'écriture des sorties :

```bash
python scripts/run_api_smoke_tests.py --output-dir ""
```

### 5) Code retour du script

- `0` : tout passe
- `1` : au moins un test échoue

### 6) Lancer aussi la suite Note: les tests asynchrones sont pris en charge directement via `pytest-asyncio`, déjà inclus dans `requirements.txt`. Aucun plugin supplémentaire n’est à installer si tu fais `pip install -r requirements.txt`.

pytest

```bash
pytest
```

Le script de smoke test vérifie le contrat HTTP. `pytest` vérifie le projet.

## OpenAPI

OpenAPI et `/docs` montrent uniquement les routes `/v1` quand les routes legacy sont désactivées.

## Ce qu'il faut retenir

- utilise `/v1` partout
- sépare `API_TOKEN` et `ADMIN_TOKEN`
- active le rate limit si l'API est exposée à d'autres outils
- garde le cache négatif court
- n'active le dump HTML que pour diagnostiquer un parseur cassé
