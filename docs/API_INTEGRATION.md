# API Integration Guide

Guide de consommation de l'API pour un autre service, agent, script ou outil.

## Base URL

Contrat canonique :
- Docker : `http://manga-news-api:8000/v1`
- machine hôte : `http://localhost:8017/v1`
- LAN : `http://<host-ip>:8017/v1`

Ne t'appuie pas sur les routes non versionnées. Elles sont bloquées par défaut.

## Auth

### Endpoints publics

Si `API_TOKEN` est défini :

```http
Authorization: Bearer <api-token>
```

### Endpoints admin

Si `ADMIN_TOKEN` est défini, les routes `/v1/admin/...` attendent :

```http
Authorization: Bearer <admin-token>
```

Si `ADMIN_TOKEN` est vide, fallback sur `API_TOKEN`.

## Enveloppe commune

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
    "returned": 10,
    "total": 34,
    "has_more": true
  },
  "data": {}
}
```

`pagination` est optionnel, mais présent sur les endpoints de liste.

## Erreurs stables

```json
{
  "ok": false,
  "code": "INVALID_REQUEST",
  "detail": "Unknown volume field path: bogus"
}
```

Codes à gérer côté client :
- `INVALID_REQUEST`
- `AUTH_REQUIRED`
- `RESOURCE_NOT_FOUND`
- `UPSTREAM_FETCH_ERROR`
- `UPSTREAM_PARSE_ERROR`
- `RATE_LIMITED`
- `ENDPOINT_NOT_FOUND`

## Headers utiles

- `ETag`
- `X-Data-Fingerprint`
- `X-Cache-Status`
- `X-Request-ID`
- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Reset`
- `Retry-After` si `429`

### Requête conditionnelle

```http
If-None-Match: "<fingerprint>"
```

Si rien n'a changé : `304 Not Modified`.

## Endpoints principaux

### Santé
- `GET /health`

### Recherche
- `GET /search?q=...&kind=series|volume|all&mode=best|all&limit=10`
- `GET /search/resolve?q=...&kind=series|volume|all&limit=10`

### Série
- `GET /series/{slug}`
- `GET /series/by-url?url=...`
- `GET /series/{slug}/related`
- `GET /series/by-url/related?url=...`
- `GET /series/{slug}/editions?edition=all|vf|vo`
- `GET /series/by-url/editions?url=...&edition=all|vf|vo`

### Volume
- `GET /lookup/volume?series=...&number=...&limit=10`
- `GET /volume/{series_slug}/{volume_slug}`
- `GET /volume/by-url?url=...`

### News
- `GET /news/global?limit=10`
- `GET /news/series/{slug}?limit=10`
- `GET /news/volume/{series_slug}/{volume_slug}?limit=10`
- `GET /news/volume/by-url?url=...&limit=10`

### Planning
- `GET /planning?section=manga-vf|manga-vo&year=2026&month=4&page=1&publisher=...&q=...&date_from=...&date_to=...&sort=date_asc|date_desc|title_asc|title_desc&limit=25`

### Admin
- `GET /admin/cache/stats`
- `POST /admin/cache/invalidate`
- `GET /admin/metrics`

## Matching tolérant et score de similarité

La recherche est tolérante aux petites variations de titre. Avant calcul, l'API normalise les chaînes puis applique un fuzzy matching.

Normalisation appliquée :
- accents retirés ;
- casse ignorée ;
- ponctuation remplacée par des espaces ;
- espaces normalisés ;
- `&` remplacé par `and` ;
- bruit éditorial courant réduit (`collector`, `édition originale`, `vol.`, `tome`, etc.).

Exemple réel :
- requête locale : `Dogs - Bullets & Carnage`
- titre Manga News : `Dogs: Bullets & Carnage`

Ces deux formes matchent très haut, parce qu'elles convergent vers une forme normalisée proche de :

```text
dogs bullets and carnage
```

### Où c'est implémenté

- `app/utils.py`
  - `normalize_text(...)`
  - `score_match(...)`
- `app/manga_news/parsers.py`
  - `parse_search_page(...)`

### Ce que le client reçoit

Sur `/search`, chaque résultat expose :
- `title`
- `url`
- `kind`
- `score`
- éventuellement `slug`, `series_slug`, `volume_slug`, `number`, `number_int`, `edition_label`, `is_special`, `is_one_shot`

Le champ `score` est le signal de similarité exploitable côté client, sur 100.

Exemple :

```json
{
  "title": "Dogs: Bullets & Carnage",
  "url": "https://www.manga-news.com/index.php/serie/Dogs-Bullets-Carnage",
  "kind": "series",
  "score": 100,
  "slug": "Dogs-Bullets-Carnage"
}
```

Sur `/search/resolve`, l'API ajoute :
- `confidence`

Interprétation pratique :
- `score` = similarité fine chiffrée ;
- `confidence` = lecture qualitative de ce score pour décider vite.

### Recommandation côté client

- si tu veux choisir parmi plusieurs candidats, utilise `/search` et trie/interprète `score` ;
- si tu veux le meilleur candidat directement, utilise `/search/resolve` et contrôle `confidence` ;
- ne traite pas un `score` élevé comme une preuve absolue si Manga News remonte peu de résultats ou des titres très voisins.

## Flux recommandés

### Charger une série
1. `GET /search/resolve?q=<titre>&kind=series`
2. lire `data.best.slug`
3. `GET /series/{slug}`
4. stocker l'`ETag`
5. réutiliser `If-None-Match`

### Charger un volume à partir du titre de série et du numéro
1. `GET /lookup/volume?series=One%20Piece&number=91`
2. lire `data.resolved.series_slug` et `data.resolved.volume_slug`
3. consommer directement `data.volume`

C'est la route la plus propre si tu connais déjà la série et le numéro.

### Charger un volume déjà résolu
1. `GET /volume/{series_slug}/{volume_slug}`
2. stocker l'`ETag`
3. réutiliser `If-None-Match`

## Pagination

Appliquée à :
- `/search`
- `/search/resolve`
- `/news/*`
- `/planning`
- `/lookup/volume`

Le client ne doit plus deviner la taille logique de la réponse.

## Champs volume normalisés

Les payloads volume exposent :
- `number`
- `number_int`
- `edition_label`
- `is_special`
- `is_one_shot`

Exemple :

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

Le cache négatif évite de re-solliciter trop vite Manga-News quand une ressource est :
- absente (`RESOURCE_NOT_FOUND`)
- temporairement indisponible (`UPSTREAM_FETCH_ERROR`)
- cassée côté parsing (`UPSTREAM_PARSE_ERROR`)

Ce cache doit rester court. Son but n'est pas de masquer les erreurs, juste d'éviter les rafales inutiles.

Variables utiles :
- `NEGATIVE_CACHE_ENABLED`
- `NEGATIVE_CACHE_TTL_SECONDS`

## Dump HTML de debug

Quand `DEBUG_CAPTURE_HTML_ON_ERROR=true`, l'API sauvegarde le HTML brut et un JSON compagnon sur erreur de parsing.

Variables utiles :
- `DEBUG_CAPTURE_HTML_ON_ERROR`
- `DEBUG_HTML_DUMP_DIR`

Usage conseillé :
- active-le uniquement pour diagnostiquer un parseur cassé ;
- récupère le dump ;
- corrige le parseur ;
- désactive ensuite.

## Métriques admin

`GET /admin/metrics` expose des compteurs simples, utiles pour un opérateur :
- réponses HTTP par classe
- cache hits / misses / stale fallbacks
- hits de cache négatif
- erreurs de parsing
- erreurs upstream
- retries upstream
- nombre de `429`
- ratios dérivés (`cache_hit_ratio`, `negative_cache_hit_ratio`, `upstream_error_ratio`)

## Cache stats admin

`GET /admin/cache/stats` expose :
- stats du cache principal
- stats du cache négatif
- stats des snapshots watch

`POST /admin/cache/invalidate` permet d'invalider :
- par `cache_key`
- par `namespace`
- par `resource_url`
- seulement les expirés
- ou tout le cache

## Rate limiting

Variables utiles :
- `RATE_LIMIT_ENABLED`
- `RATE_LIMIT_REQUESTS`
- `RATE_LIMIT_WINDOW_SECONDS`
- `RATE_LIMIT_SCOPE`
- `RATE_LIMIT_INCLUDE_ADMIN`
- `RATE_LIMIT_EXEMPT_PATHS`

Le client doit :
- respecter `429`
- lire `Retry-After`
- éviter les boucles agressives sur les endpoints admin

## Tests et validation

### Smoke tests HTTP

```bash
python scripts/run_api_smoke_tests.py --base-url "$BASE_URL" --token "$TOKEN" --admin-token "$ADMIN_TOKEN"
```

### Si le dossier de sortie n'est pas inscriptible

```bash
python scripts/run_api_smoke_tests.py --output-dir /tmp/api_test_outputs
```

ou

```bash
python scripts/run_api_smoke_tests.py --output-dir ""
```

### Suite projet

```bash
Note: les tests asynchrones sont pris en charge directement via `pytest-asyncio`, déjà inclus dans `requirements.txt`. Aucun plugin supplémentaire n’est à installer si tu fais `pip install -r requirements.txt`.

pytest
```

## Recommandations de client

- consomme uniquement `/v1`
- conserve et rejoue les `ETag`
- gère explicitement `429`, `401`, `404`, `502`
- exploite `lookup/volume` au lieu de reconstruire des recherches floues
- ne traite pas `UPSTREAM_PARSE_ERROR` comme une absence définitive de donnée
- si l'API est critique, surveille `/v1/admin/metrics`
- si la similarité de titre compte, exploite `score` sur `/v1/search` et `confidence` sur `/v1/search/resolve`
