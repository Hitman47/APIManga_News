# Manga News Private API

API non officielle, légère et auto-hébergeable pour exposer en JSON des données publiques de Manga News.

## Ce que l’API fait maintenant

- contrat canonique versionné sous `/v1`
- anciennes routes sans préfixe désactivées par défaut, réactivables uniquement pour compatibilité
- cache SQLite persistant
- auth Bearer lecture et admin séparables (`API_TOKEN`, `ADMIN_TOKEN`)
- réponses normalisées avec `ETag`, `X-Data-Fingerprint`, `X-Cache-Status`, `X-Request-ID`
- erreurs structurées avec code stable (`INVALID_REQUEST`, `RESOURCE_NOT_FOUND`, `UPSTREAM_PARSE_ERROR`, etc.)
- retries exponentiels côté upstream
- rate limiting configurable par variables d’environnement
- pagination structurée sur les endpoints liste
- normalisation enrichie des volumes : `number`, `number_int`, `edition_label`, `is_special`, `is_one_shot`
- exemples OpenAPI intégrés pour One Piece / tome 91

## Pourquoi il y avait des doublons `/v1` et non versionnés

Les anciennes routes non versionnées et les routes `/v1` sont fonctionnellement identiques.
Leur seule utilité réelle est la compatibilité avec un ancien client.

Donc, par défaut :
- **on utilise seulement `/v1`** ;
- **les routes legacy sont coupées** ;
- on peut les réactiver temporairement avec `ENABLE_LEGACY_ROUTES=true` si un vieux client doit survivre.

## Variables d’environnement principales

Consulte `.env.example`.

Les plus utiles :

- `API_TOKEN` : token lecture ; vide = API ouverte
- `ADMIN_TOKEN` : token admin ; si vide, fallback sur `API_TOKEN`
- `ENABLE_LEGACY_ROUTES` : réactive temporairement les anciennes routes non versionnées
- `REQUEST_MAX_RETRIES` / `REQUEST_BACKOFF_SECONDS` : robustesse réseau vers Manga-News
- `RATE_LIMIT_ENABLED` : active la limitation de débit
- `RATE_LIMIT_MAX_REQUESTS` / `RATE_LIMIT_WINDOW_SECONDS` : paramètres du rate limit
- `RATE_LIMIT_SCOPE` : `ip`, `token`, `ip_or_token`
- `RATE_LIMIT_INCLUDE_ADMIN` : applique aussi le rate limit aux endpoints admin
- `TRUST_X_FORWARDED_FOR` : utile derrière reverse proxy

## Lancer localement

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8017
```

## Lancer avec Docker Compose

```bash
docker compose up -d --build
```

API disponible sur `http://localhost:8017`.

## Contrat à utiliser

Pour toute nouvelle intégration, utilise **uniquement** les routes `/v1/...`.

Exemples :

```bash
curl http://localhost:8017/v1/health
curl "http://localhost:8017/v1/search?q=one%20piece&kind=series&mode=all&limit=5&page=1"
curl "http://localhost:8017/v1/search/resolve?q=one%20piece%20tome%2091&kind=volume"
curl "http://localhost:8017/v1/lookup/volume?series=One%20Piece&number=91"
curl "http://localhost:8017/v1/series/One-piece-Edition-originale"
curl "http://localhost:8017/v1/volume/One-Piece/vol-91"
```

## Pagination

Les endpoints liste renvoient maintenant un bloc `pagination` :

```json
{
  "pagination": {
    "page": 2,
    "limit": 10,
    "returned": 10,
    "total": 17,
    "has_more": false,
    "next_page": null,
    "prev_page": 1
  }
}
```

Endpoints concernés :

- `/v1/search`
- `/v1/news/global`
- `/v1/news/series/{slug}`
- `/v1/news/volume/{series_slug}/{volume_slug}`
- `/v1/news/volume/by-url`
- `/v1/planning`

## Erreurs structurées

Exemple :

```json
{
  "ok": false,
  "code": "INVALID_REQUEST",
  "detail": "Unknown volume field path: bogus",
  "request_id": "..."
}
```

Codes principaux :

- `INVALID_REQUEST`
- `UNAUTHORIZED`
- `RESOURCE_NOT_FOUND`
- `UPSTREAM_FETCH_ERROR`
- `UPSTREAM_PARSE_ERROR`
- `RATE_LIMITED`

## Administration du cache

Stats :

```bash
curl -H "Authorization: Bearer <admin_token>"   http://localhost:8017/v1/admin/cache/stats
```

Invalidation :

```bash
curl -X POST http://localhost:8017/v1/admin/cache/invalidate   -H "Authorization: Bearer <admin_token>"   -H "Content-Type: application/json"   -d '{"namespace":"planning","expired_only":true}'
```

## Lancer les tests API soi-même

Le fichier texte d’exemples manuels est ici :
- `docs/ONE_PIECE_API_TESTS.txt`

Le script batch est ici :
- `scripts/run_api_smoke_tests.py`

### Smoke tests One Piece

Linux / macOS :

```bash
export BASE_URL="http://localhost:8017/v1"
export API_TOKEN="ton_token_lecture"
export ADMIN_TOKEN="ton_token_admin"   # optionnel si identique au token lecture
python scripts/run_api_smoke_tests.py --base-url "$BASE_URL" --token "$API_TOKEN" --admin-token "$ADMIN_TOKEN"
```

Windows PowerShell :

```powershell
$env:BASE_URL = "http://localhost:8017/v1"
$env:API_TOKEN = "ton_token_lecture"
$env:ADMIN_TOKEN = "ton_token_admin"
python .\scriptsun_api_smoke_tests.py --base-url $env:BASE_URL --token $env:API_TOKEN --admin-token $env:ADMIN_TOKEN
```

Résultats :

- sorties JSON dans `api_test_outputs/`
- code retour `0` si tout passe
- code retour `1` s’il y a au moins un échec

### Tests Python

```bash
pytest
```

## Documentation d’intégration

Guide détaillé : `docs/API_INTEGRATION.md`
