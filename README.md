# Manga News Private API

API non officielle, auto-hébergeable, qui expose en JSON des données publiques de Manga-News.

Le projet est pensé pour un usage concret : scripts perso, dashboard, bot, outil de suivi, agent IA, ou backend intermédiaire. La source amont reste du HTML public, donc l’API sert surtout à fournir un contrat JSON stable, cacheable et exploitable.

## Ce que l’API fournit

- contrat canonique sous `/v1/...`
- routes legacy non versionnées désactivées par défaut
- auth séparée : `API_TOKEN` pour le public, `ADMIN_TOKEN` pour l’admin
- cache SQLite persistant
- cache négatif court pour éviter de refrapper en boucle une ressource absente/cassée
- `ETag` + `If-None-Match` + `304`
- erreurs machine-readable avec `code` stable
- pagination structurée sur les endpoints de liste
- normalisation volume : `number`, `number_int`, `edition_label`, `is_special`, `is_one_shot`
- rate limiting configurable par `.env`, variables d’environnement ou compose
- endpoint admin de métriques
- dump HTML optionnel en cas d’échec de parsing
- smoke tests prêts à lancer
- OpenAPI / Swagger activables

## À qui sert cette doc

Cette documentation doit suffire pour :

- lancer l’API localement ou en Docker
- comprendre le contrat HTTP
- consommer l’API depuis un script, un autre service ou une IA
- faire un premier diagnostic si quelque chose casse
- tester rapidement l’API avec le cas One Piece

## Parcours recommandé

Selon ton besoin, lis dans cet ordre :

1. **Ce README** pour la vue d’ensemble et le démarrage rapide.
2. **`docs/API_INTEGRATION.md`** pour consommer l’API proprement.
3. **`docs/DEPLOYMENT_AND_OPERATIONS.md`** pour déployer, configurer et exploiter l’API.
4. **`docs/USE_CASES_AND_RECIPES.md`** pour des scénarios concrets, humains ou IA.
5. **`docs/ONE_PIECE_API_TESTS.txt`** pour les tests manuels et le smoke test de bout en bout.

## Démarrage rapide en 5 minutes

### 1) Installer les dépendances

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Sous Windows PowerShell :

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2) Préparer la config

Copie `.env.example` vers `.env`, puis ajuste au minimum :

```env
API_TOKEN=change-me
ADMIN_TOKEN=change-me-admin
ENABLE_DOCS=true
```

Pour un usage local sans auth, laisse les tokens vides. Pour un service exposé, ne fais pas ça.

### 3) Lancer l’API

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8017
```

L’API sera disponible sur :

- `http://localhost:8017/v1`
- docs Swagger : `http://localhost:8017/docs`
- OpenAPI JSON : `http://localhost:8017/openapi.json`

### 4) Vérifier que ça répond

Sans auth :

```bash
curl http://localhost:8017/v1/health
```

Avec auth :

```bash
curl -H "Authorization: Bearer $API_TOKEN" http://localhost:8017/v1/health
```

### 5) Faire une vraie requête utile

```bash
curl -H "Authorization: Bearer $API_TOKEN" \
  "http://localhost:8017/v1/lookup/volume?series=One%20Piece&number=91"
```

## Démarrage rapide avec Docker Compose

```bash
docker compose up -d --build
```

Par défaut, le port hôte est `8017`.

### Variables importantes exposées dans le compose

Les réglages d’exploitation utiles sont pilotables sans modifier le code :

- `API_TOKEN`
- `ADMIN_TOKEN`
- `ENABLE_DOCS`
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
- `REQUEST_MAX_RETRIES`
- `REQUEST_BACKOFF_SECONDS`

Le détail d’exploitation est documenté dans `docs/DEPLOYMENT_AND_OPERATIONS.md`.

## Contrat HTTP : ce qu’il faut retenir

### Base URL

Utilise **uniquement** les routes `/v1/...`.

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

Il n’y avait pas de différence métier. Les routes non versionnées servaient uniquement à la rétrocompatibilité. Elles sont maintenant désactivées par défaut.

Pour les réactiver explicitement :

```env
ENABLE_LEGACY_ROUTES=true
```

Pour un nouveau client, il n’y a aucune bonne raison d’utiliser autre chose que `/v1`.

### Enveloppe standard

La majorité des endpoints renvoient une enveloppe commune :

```json
{
  "schema_version": "1.0",
  "ok": true,
  "found": true,
  "source": "manga_news",
  "source_url": "https://www.manga-news.com/...",
  "cached": false,
  "fetched_at": "2026-04-20T12:00:00+00:00",
  "cache_expires_at": "2026-04-21T12:00:00+00:00",
  "partial": false,
  "warnings": [],
  "fingerprint": "...",
  "pagination": {
    "page": 1,
    "limit": 10,
    "returned": 1,
    "total": 1,
    "has_more": false
  },
  "data": {}
}
```

`pagination` est présent sur les endpoints de liste.

### Headers utiles

Les réponses peuvent exposer :

- `ETag: "<fingerprint>"`
- `X-Data-Fingerprint: <fingerprint>`
- `X-Cache-Status: MISS|HIT|STALE`
- `X-Request-ID: <id>`
- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Reset`
- `Retry-After` si `429`

### Format d’erreur

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

## Endpoints principaux

### Santé

```bash
curl -H "Authorization: Bearer $API_TOKEN" http://localhost:8017/v1/health
```

### Recherche libre

```bash
curl -H "Authorization: Bearer $API_TOKEN" \
  "http://localhost:8017/v1/search?q=one%20piece&kind=series&mode=all&limit=10"
```

### Résolution directe d’un volume par série + numéro

```bash
curl -H "Authorization: Bearer $API_TOKEN" \
  "http://localhost:8017/v1/lookup/volume?series=One%20Piece&number=91"
```

### Fiche série

```bash
curl -H "Authorization: Bearer $API_TOKEN" \
  "http://localhost:8017/v1/series/One-piece-Edition-originale"
```

### Fiche volume

```bash
curl -H "Authorization: Bearer $API_TOKEN" \
  "http://localhost:8017/v1/volume/One-Piece/vol-91"
```

### News globales

```bash
curl -H "Authorization: Bearer $API_TOKEN" \
  "http://localhost:8017/v1/news/global?limit=10"
```

### Planning filtré

```bash
curl -G -H "Authorization: Bearer $API_TOKEN" \
  "http://localhost:8017/v1/planning" \
  --data-urlencode "section=manga-vf" \
  --data-urlencode "q=one piece" \
  --data-urlencode "sort=date_desc" \
  --data-urlencode "limit=10"
```

## Use cases fréquents

### Cas 1 — Je connais déjà la série et le numéro

Utilise `/v1/lookup/volume`.

C’est le chemin le plus propre. Tu évites un `search/resolve` manuel côté client.

### Cas 2 — Je n’ai qu’un titre flou

1. `GET /v1/search` ou `GET /v1/search/resolve`
2. récupère `slug`, `series_slug` ou `volume_slug`
3. recharge la ressource canonique avec `/series/...` ou `/volume/...`

### Cas 3 — Je veux seulement quelques champs

Les endpoints `/series/...` et `/volume/...` acceptent `blocks`, `fields` et `include_raw_sections`.

Exemple série :

```bash
curl -H "Authorization: Bearer $API_TOKEN" \
  "http://localhost:8017/v1/series/One-piece-Edition-originale?blocks=editions,stats&fields=title,vf.volumes"
```

Exemple volume :

```bash
curl -H "Authorization: Bearer $API_TOKEN" \
  "http://localhost:8017/v1/volume/One-Piece/vol-91?blocks=release,scores&fields=title,number_int"
```

### Cas 4 — Je veux éviter les transferts inutiles

Stocke l’`ETag` puis renvoie `If-None-Match`.

```bash
curl -i -H "Authorization: Bearer $API_TOKEN" \
  "http://localhost:8017/v1/series/One-piece-Edition-originale"
```

Puis :

```bash
curl -i -H "Authorization: Bearer $API_TOKEN" \
  -H 'If-None-Match: "<etag-precedent>"' \
  "http://localhost:8017/v1/series/One-piece-Edition-originale"
```

## Smoke tests et validation

### Tests HTTP batch

```bash
python scripts/run_api_smoke_tests.py --base-url "$BASE_URL" --token "$TOKEN" --admin-token "$ADMIN_TOKEN"
```

### Si le dossier de sortie n’est pas inscriptible

```bash
python scripts/run_api_smoke_tests.py --output-dir /tmp/api_test_outputs
```

ou sans fichier de sortie :

```bash
python scripts/run_api_smoke_tests.py --output-dir ""
```

### Suite projet complète

```bash
pytest
```

Les tests async sont pris en charge par `pytest-asyncio`, déjà inclus dans `requirements.txt`.

## Si tu veux donner la doc à quelqu’un ou à une IA

Commence par fournir :

- ce `README.md`
- `docs/API_INTEGRATION.md`
- `docs/DEPLOYMENT_AND_OPERATIONS.md`
- `docs/USE_CASES_AND_RECIPES.md`

C’est suffisant pour :

- comprendre les endpoints
- savoir comment s’authentifier
- intégrer le cache et les ETag
- gérer les erreurs proprement
- exploiter les endpoints admin
- diagnostiquer un problème de parsing ou de quota

## Limite importante à garder en tête

L’API fournit un contrat JSON stable, mais la source amont reste du HTML public. Si Manga-News change fortement son HTML, les parseurs peuvent devoir être ajustés. Les mécanismes utiles pour diagnostiquer ça existent déjà :

- métriques admin
- cache négatif court
- dump HTML sur erreur de parsing
- tests de fixtures
