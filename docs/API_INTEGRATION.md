# Guide d’intégration API Manga News

Ce guide décrit le contrat utile pour un client externe, sans avoir à relire tout le code.

## Contrat à utiliser

Utilise **uniquement** les routes `/v1/...`.

Les anciennes routes sans préfixe existent seulement en **mode compatibilité** et sont **désactivées par défaut**.
Elles ne doivent plus être utilisées pour une nouvelle intégration.

Base URL typiques :
- même réseau Docker : `http://manga-news-api:8000/v1`
- machine hôte : `http://localhost:8017/v1`
- LAN : `http://<ip-hote>:8017/v1`

## Authentification

### Lecture
Si `API_TOKEN` est défini :

```http
Authorization: Bearer <api_token>
```

### Administration
Les endpoints admin utilisent `ADMIN_TOKEN`.
Si `ADMIN_TOKEN` est vide, l’API retombe sur `API_TOKEN`.

```http
Authorization: Bearer <admin_token>
```

## Enveloppe de réponse standard

La plupart des endpoints renvoient :

```json
{
  "schema_version": "1.0",
  "ok": true,
  "found": true,
  "source": "manga_news",
  "source_url": "https://www.manga-news.com/...",
  "cached": false,
  "fetched_at": "2026-04-20T12:00:00+00:00",
  "cache_expires_at": "2026-04-20T18:00:00+00:00",
  "partial": false,
  "warnings": [],
  "fingerprint": "...",
  "pagination": null,
  "data": {}
}
```

## Headers utiles

Les réponses peuvent inclure :
- `ETag: "<fingerprint>"`
- `X-Data-Fingerprint: <fingerprint>`
- `X-Cache-Status: MISS|HIT|STALE`
- `X-Request-ID: <request-id>`
- `Vary: Authorization, If-None-Match`

### Revalidation conditionnelle

Réutilise l’ETag :

```http
If-None-Match: "<fingerprint>"
```

Si rien n’a changé, l’API renvoie `304 Not Modified`.
Les weak ETag sont aussi acceptés.

## Pagination structurée

Les endpoints liste renvoient un bloc `pagination` :

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
- `GET /search`
- `GET /news/global`
- `GET /news/series/{slug}`
- `GET /news/volume/{series_slug}/{volume_slug}`
- `GET /news/volume/by-url`
- `GET /planning`

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

Codes stables actuellement exposés :
- `INVALID_REQUEST`
- `UNAUTHORIZED`
- `RESOURCE_NOT_FOUND`
- `UPSTREAM_FETCH_ERROR`
- `UPSTREAM_PARSE_ERROR`
- `RATE_LIMITED`

Mapping HTTP principal :
- `400` : paramètres invalides
- `401` : token manquant ou invalide
- `404` : ressource absente
- `429` : limite de débit atteinte
- `502` : échec réseau upstream ou parsing upstream non fiable
- `304` : ressource inchangée avec `If-None-Match`

## Endpoints principaux

### Search
- `GET /search?q=...&kind=series|volume|all&mode=best|all&limit=10&page=1`
- `GET /search/resolve?q=...&kind=series|volume|all&limit=10`

### Lookup volume direct
- `GET /lookup/volume?series=One%20Piece&number=91&limit=10`

Ce endpoint est le plus simple quand le client connaît déjà un titre de série et un numéro de tome.

### Series
- `GET /series/{slug}`
- `GET /series/by-url?url=...`
- `GET /series/{slug}/related`
- `GET /series/by-url/related?url=...`
- `GET /series/{slug}/editions?edition=all|vf|vo`
- `GET /series/by-url/editions?url=...&edition=all|vf|vo`

Projection sur les fiches série :
- `blocks=editions,stats`
- `fields=title,vf.volumes`
- `include_raw_sections=true`

### Volume
- `GET /volume/{series_slug}/{volume_slug}`
- `GET /volume/by-url?url=...`

Projection sur les fiches volume :
- `blocks=release,scores`
- `fields=number,number_int,publication_date,isbn_ean`
- `include_raw_sections=true`

### News
- `GET /news/global?limit=10&page=1`
- `GET /news/series/{slug}?limit=10&page=1`
- `GET /news/volume/{series_slug}/{volume_slug}?limit=10&page=1`
- `GET /news/volume/by-url?url=...&limit=10&page=1`

### Planning
- `GET /planning?section=manga-vf|manga-vo&year=2026&month=4&page=1&publisher=...&q=...&date_from=...&date_to=...&sort=date_asc|date_desc|title_asc|title_desc&limit=25`

### Admin cache
- `GET /admin/cache/stats`
- `POST /admin/cache/invalidate`

Payload d’invalidation :

```json
{
  "cache_key": null,
  "namespace": "planning",
  "resource_url": null,
  "expired_only": true,
  "all_entries": false
}
```

## Normalisation volume utile côté client

Les volumes exposent désormais plusieurs champs normalisés :
- `number` : représentation texte simple du numéro, ex. `"91"`
- `number_int` : entier normalisé, ex. `91`
- `edition_label` : libellé d’édition détecté, ex. `"Collector"`
- `is_special` : booléen pour artbook, guidebook, databook, coffret, etc.
- `is_one_shot` : booléen pour one-shot détecté

Ça évite au client de reparser le titre lui-même.

## Rate limiting

Le rate limit se configure par variables d’environnement, pas seulement via Compose :
- `RATE_LIMIT_ENABLED=true|false`
- `RATE_LIMIT_MAX_REQUESTS=60`
- `RATE_LIMIT_WINDOW_SECONDS=60`
- `RATE_LIMIT_SCOPE=ip|token|ip_or_token`
- `RATE_LIMIT_INCLUDE_ADMIN=true|false`
- `TRUST_X_FORWARDED_FOR=true|false`

Quand il s’active, l’API renvoie aussi :
- `Retry-After`
- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Window`

## Routes legacy

Par défaut, les routes non versionnées sont coupées.

Pour les réactiver temporairement :

```env
ENABLE_LEGACY_ROUTES=true
```

Utilité réelle : **uniquement** ne pas casser un vieux client.
Fonctionnellement, elles sont identiques aux routes `/v1`.

## Flux recommandé

### Trouver une série
1. `GET /search/resolve?q=<titre>&kind=series`
2. lire `data.best.slug`
3. `GET /series/{slug}`
4. stocker l’`ETag`

### Trouver un tome
1. `GET /lookup/volume?series=<titre>&number=<n>`
2. lire `data.resolved.series_slug` et `data.resolved.volume_slug`
3. consommer `data.volume`

### Suivre des nouveautés / planning
1. appeler un endpoint liste
2. stocker `ETag` ou `fingerprint`
3. refaire la requête avec `If-None-Match`

## Tests manuels et batch

Exemples manuels : `docs/ONE_PIECE_API_TESTS.txt`

Batch :

```bash
python scripts/run_api_smoke_tests.py --base-url http://localhost:8017/v1 --token <api_token> --admin-token <admin_token>
```

Le script écrit une réponse JSON par requête dans `api_test_outputs/` par défaut.

Tests projet :

```bash
pytest
```
