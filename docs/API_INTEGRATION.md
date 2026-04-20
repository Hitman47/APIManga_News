# Guide d’intégration API

Ce document est la référence pour un développeur, un autre backend, un script d’automatisation ou une IA qui doit consommer l’API proprement.

Il ne parle pas du déploiement en détail. Pour ça, voir `docs/DEPLOYMENT_AND_OPERATIONS.md`.

## 1. Principes de base

### Base URL

Le contrat canonique est :

- Docker : `http://manga-news-api:8000/v1`
- machine hôte : `http://localhost:8017/v1`
- LAN : `http://<host-ip>:8017/v1`

Ne t’appuie pas sur les routes non versionnées. Elles sont désactivées par défaut.

### Auth

#### Endpoints publics

Si `API_TOKEN` est défini :

```http
Authorization: Bearer <api-token>
```

#### Endpoints admin

Si `ADMIN_TOKEN` est défini, les routes `/v1/admin/...` attendent :

```http
Authorization: Bearer <admin-token>
```

Si `ADMIN_TOKEN` est vide, fallback sur `API_TOKEN`.

### Content type

- réponses : `application/json`
- invalidation cache : `POST` JSON

## 2. Enveloppe standard

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

### Sens des champs importants

- `ok` : la requête HTTP et le traitement métier ont réussi
- `found` : il existe un résultat exploitable
- `source_url` : URL Manga-News utilisée comme source canonique
- `cached` : la donnée vient du cache
- `partial` : la réponse peut venir d’un stale cache ou d’un fallback partiel
- `warnings` : liste d’avertissements non bloquants
- `fingerprint` : hash stable du contenu JSON métier
- `pagination` : métadonnées de liste, quand applicable

## 3. Erreurs stables

Format :

```json
{
  "ok": false,
  "code": "INVALID_REQUEST",
  "detail": "Unknown volume field path: bogus"
}
```

Codes à gérer côté client :

- `INVALID_REQUEST` : paramètres invalides, bloc inconnu, champ inconnu, etc.
- `AUTH_REQUIRED` : token absent ou invalide
- `RESOURCE_NOT_FOUND` : la ressource n’existe pas ou n’a pas pu être résolue
- `UPSTREAM_FETCH_ERROR` : problème réseau/HTTP vers Manga-News
- `UPSTREAM_PARSE_ERROR` : la page a été récupérée mais le parseur n’a pas réussi à l’exploiter
- `RATE_LIMITED` : quota dépassé
- `ENDPOINT_NOT_FOUND` : route désactivée ou inexistante, notamment legacy routes off

### Politique conseillée côté client

- `400` / `INVALID_REQUEST` : corriger le client, ne pas retenter en boucle
- `401` / `AUTH_REQUIRED` : corriger le token
- `404` / `RESOURCE_NOT_FOUND` : considérer l’absence comme métier
- `429` / `RATE_LIMITED` : respecter `Retry-After`
- `502` / `UPSTREAM_FETCH_ERROR` ou `UPSTREAM_PARSE_ERROR` : traiter comme incident temporaire ou changement upstream

## 4. Headers utiles

L’API peut renvoyer :

- `ETag`
- `X-Data-Fingerprint`
- `X-Cache-Status`
- `X-Request-ID`
- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Reset`
- `Retry-After`

### Requêtes conditionnelles avec ETag

Envoi initial :

```bash
curl -i -H "Authorization: Bearer $API_TOKEN" \
  "$BASE_URL/series/One-piece-Edition-originale"
```

Tu récupères un header `ETag`, puis tu peux rejouer :

```bash
curl -i -H "Authorization: Bearer $API_TOKEN" \
  -H 'If-None-Match: "<etag-precedent>"' \
  "$BASE_URL/series/One-piece-Edition-originale"
```

Si rien n’a changé : `304 Not Modified`.

## 5. Catalogue des endpoints

## 5.1 Santé

### `GET /health`

Usage : vérifier que l’API répond.

Exemple :

```bash
curl -H "Authorization: Bearer $API_TOKEN" "$BASE_URL/health"
```

Réponse :

```json
{"ok": true}
```

## 5.2 Recherche

### `GET /search`

Recherche libre, avec plusieurs résultats.

Paramètres :

- `q` : texte de recherche, obligatoire
- `kind` : `series`, `volume`, `all`
- `mode` : `best`, `all`
- `limit` : `1..50`

Exemple :

```bash
curl -H "Authorization: Bearer $API_TOKEN" \
  "$BASE_URL/search?q=one%20piece%20tome%2091&kind=volume&mode=all&limit=10"
```

Cas d’usage :

- proposer plusieurs candidats à un utilisateur
- faire une résolution semi-automatique avec confirmation humaine

### `GET /search/resolve`

Même logique, mais oriente la réponse autour du meilleur match.

Paramètres :

- `q` : obligatoire
- `kind` : `series`, `volume`, `all`
- `limit` : `1..50`

Exemple :

```bash
curl -H "Authorization: Bearer $API_TOKEN" \
  "$BASE_URL/search/resolve?q=one%20piece%20tome%2091&kind=volume&limit=10"
```

À utiliser quand tu veux un candidat principal et quelques alternatives.

## 5.3 Série

### `GET /series/{slug}`

Charge une fiche série canonique.

Paramètres utiles :

- `blocks` : filtre par blocs logiques
- `fields` : filtre par chemins précis
- `include_raw_sections` : inclut les sections brutes extraites

Exemple complet :

```bash
curl -H "Authorization: Bearer $API_TOKEN" \
  "$BASE_URL/series/One-piece-Edition-originale?blocks=editions,stats&fields=title,vf.volumes&include_raw_sections=false"
```

### `GET /series/by-url`

Même réponse, mais à partir d’une URL Manga-News existante.

```bash
curl -G -H "Authorization: Bearer $API_TOKEN" \
  "$BASE_URL/series/by-url" \
  --data-urlencode "url=https://www.manga-news.com/index.php/serie/One-piece-Edition-originale"
```

### `GET /series/{slug}/related`

Récupère les liens liés : séries, volumes, anime, drama, dossiers, univers, externes.

### `GET /series/by-url/related`

Même logique mais par URL.

### `GET /series/{slug}/editions`

Récupère les blocs d’éditions VF/VO.

Paramètres :

- `edition=all|vf|vo`

### `GET /series/by-url/editions`

Même logique mais par URL.

## 5.4 Volume

### `GET /lookup/volume`

Route recommandée si tu connais déjà la série et le numéro.

Paramètres :

- `series` : titre de série
- `number` : numéro voulu
- `limit` : profondeur de recherche côté résolution

Exemple :

```bash
curl -H "Authorization: Bearer $API_TOKEN" \
  "$BASE_URL/lookup/volume?series=One%20Piece&number=91&limit=10"
```

Cette route :

1. construit une recherche `"<series> tome <number>"`
2. résout le bon volume
3. renvoie la fiche volume complète
4. expose aussi les candidats utilisés pour la résolution

### `GET /volume/{series_slug}/{volume_slug}`

Récupère la fiche volume canonique.

Paramètres utiles :

- `blocks`
- `fields`
- `include_raw_sections`

Exemple :

```bash
curl -H "Authorization: Bearer $API_TOKEN" \
  "$BASE_URL/volume/One-Piece/vol-91?blocks=release,scores&fields=title,number_int,isbn_ean"
```

### `GET /volume/by-url`

Même logique, mais à partir d’une URL Manga-News.

## 5.5 News

### `GET /news/global`

News globales Manga-News.

### `GET /news/series/{slug}`

News associées à une série.

### `GET /news/volume/{series_slug}/{volume_slug}`

News associées à un volume.

### `GET /news/volume/by-url`

Même logique à partir d’une URL volume.

Exemple :

```bash
curl -H "Authorization: Bearer $API_TOKEN" \
  "$BASE_URL/news/series/One-piece-Edition-originale?limit=10"
```

## 5.6 Planning

### `GET /planning`

Paramètres principaux :

- `section=manga-vf|manga-vo`
- `year`
- `month`
- `page`
- `publisher`
- `q`
- `date_from`
- `date_to`
- `sort=date_asc|date_desc|title_asc|title_desc`
- `limit`

Exemple :

```bash
curl -G -H "Authorization: Bearer $API_TOKEN" \
  "$BASE_URL/planning" \
  --data-urlencode "section=manga-vf" \
  --data-urlencode "publisher=Glénat" \
  --data-urlencode "q=one piece" \
  --data-urlencode "date_from=2026-01-01" \
  --data-urlencode "date_to=2026-12-31" \
  --data-urlencode "sort=date_desc" \
  --data-urlencode "limit=10"
```

## 5.7 Admin

### `GET /admin/cache/stats`

Expose les stats du cache principal, du cache négatif, et des snapshots internes.

### `POST /admin/cache/invalidate`

Invalide le cache.

Payload possible :

```json
{
  "cache_key": null,
  "namespace": "series",
  "resource_url": null,
  "expired_only": false,
  "all_entries": false
}
```

Exemples utiles :

Invalider une série par URL :

```bash
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  "$BASE_URL/admin/cache/invalidate" \
  -d '{"resource_url":"https://www.manga-news.com/index.php/serie/One-piece-Edition-originale"}'
```

Invalider tout un namespace :

```bash
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  "$BASE_URL/admin/cache/invalidate" \
  -d '{"namespace":"series"}'
```

Invalider tout :

```bash
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  "$BASE_URL/admin/cache/invalidate" \
  -d '{"all_entries":true}'
```

### `GET /admin/metrics`

Expose des compteurs et ratios simples d’exploitation.

## 6. Projection de champs et blocs

Les endpoints `/series/...` et `/volume/...` supportent une projection partielle.

### Série — blocs valides

- `identity`
- `staff`
- `publishing`
- `presentation`
- `editions`
- `stats`
- `related`
- `raw`
- `raw_sections`

### Volume — blocs valides

- `identity`
- `staff`
- `publishing`
- `presentation`
- `release`
- `scores`
- `related`
- `raw`
- `raw_sections`

### Exemples `fields`

Série :

- `title`
- `vf.volumes`
- `stats.reader_score`
- `related.anime`

Volume :

- `title`
- `publication_date`
- `isbn_ean`
- `editorial_score`

Si un bloc ou champ est inconnu, l’API renvoie `400 / INVALID_REQUEST`.

## 7. Pagination

Pagination structurée appliquée à :

- `/search`
- `/search/resolve`
- `/news/*`
- `/planning`
- `/lookup/volume`

Exemple :

```json
"pagination": {
  "page": 1,
  "limit": 10,
  "returned": 10,
  "total": 34,
  "has_more": true
}
```

Le client ne doit pas supposer qu’une réponse courte signifie forcément “il n’y a pas plus de résultats” sans lire `has_more`.

## 8. Normalisation volume

Les volumes exposent :

- `number` : version texte, ex. `"91"`
- `number_int` : version entière si elle existe, ex. `91`
- `edition_label` : ex. `edition_originale`
- `is_special` : volume spécial détecté
- `is_one_shot` : booléen si détectable, sinon `null`

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

## 9. Flux d’intégration recommandés

### Flux A — Trouver puis charger une série

1. `GET /search/resolve?q=<titre>&kind=series`
2. lire `data.best.slug`
3. `GET /series/{slug}`
4. stocker l’`ETag`
5. réutiliser `If-None-Match`

### Flux B — Trouver puis charger un volume par texte libre

1. `GET /search/resolve?q=<titre>&kind=volume`
2. lire `data.best.series_slug` et `data.best.volume_slug`
3. `GET /volume/{series_slug}/{volume_slug}`

### Flux C — Charger un volume si tu connais déjà série + numéro

1. `GET /lookup/volume?series=...&number=...`
2. consommer directement `data.volume`
3. éventuellement conserver `data.resolved.*` pour journaliser la résolution

### Flux D — Construire un planning exploitable

1. `GET /planning?section=...&month=...&year=...`
2. filtrer côté client seulement si nécessaire
3. exploiter `pagination`
4. stocker `ETag` si le même planning est consulté régulièrement

## 10. Conseils pour une IA ou un agent

Si une IA consomme cette API, elle doit suivre ces règles :

- utiliser uniquement la base URL `/v1`
- toujours envoyer le bon token selon endpoint public/admin
- préférer `/lookup/volume` quand elle connaît déjà le numéro du tome
- utiliser `/search/resolve` si l’entrée est floue
- respecter `429` et `Retry-After`
- ne pas confondre `UPSTREAM_PARSE_ERROR` avec “la ressource n’existe pas”
- exploiter `ETag` et `If-None-Match` pour les relectures fréquentes
- ne pas appeler les endpoints admin sans besoin réel

Exemple de consigne à donner à une autre IA :

> Tu consommes une API Manga News sous `<BASE_URL>`, déjà suffixée par `/v1`. Utilise `Authorization: Bearer <API_TOKEN>` pour les endpoints publics et `Authorization: Bearer <ADMIN_TOKEN>` pour `/admin`. Si tu connais la série et le numéro, utilise `/lookup/volume`. Si l’entrée est floue, utilise `/search/resolve`. Gère explicitement `429`, `401`, `404`, `502`, ainsi que `ETag`/`If-None-Match`.

## 11. Tests et validation

### Smoke test HTTP

```bash
python scripts/run_api_smoke_tests.py --base-url "$BASE_URL" --token "$TOKEN" --admin-token "$ADMIN_TOKEN"
```

### Si le dossier de sortie local n’est pas inscriptible

```bash
python scripts/run_api_smoke_tests.py --output-dir /tmp/api_test_outputs
```

ou sans fichiers de sortie :

```bash
python scripts/run_api_smoke_tests.py --output-dir ""
```

### Suite projet

```bash
pytest
```

Les tests async fonctionnent directement avec `pytest-asyncio`, déjà inclus dans `requirements.txt`.
