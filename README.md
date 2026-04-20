# Manga News Private API

API non officielle, légère et auto-hébergeable pour exposer en JSON des données publiques de Manga News avec :
- cache SQLite persistant ;
- authentification Bearer optionnelle ;
- réponses normalisées pour l'automatisation ;
- support ETag / `If-None-Match` ;
- aliases versionnées sous `/v1` ;
- endpoints d'administration du cache ;
- observabilité minimale (request id, logs structurés, retries upstream).

## Périmètre actuel

### Fonctionnalités disponibles
- recherche de séries et de volumes ;
- résolution “best match” via `/search/resolve` ;
- fiches série et volume normalisées ;
- éditions d'une série (`vf` / `vo`) ;
- liens liés d'une série ;
- news globales, news d'une série, news d'un volume ;
- planning manga VF / manga VO ;
- projection partielle via `blocks`, `fields`, `include_raw_sections` ;
- fallback sur cache périmé si l'upstream est temporairement indisponible.

### Ce que l'API ne fait pas encore
- provider anime séparé ;
- agrégation multi-sources ;
- pagination automatique multi-pages côté upstream ;
- métriques métier avancées (Prometheus, traces distribuées, etc.).

## Variables d'environnement principales

Consulte `.env.example`.

Les plus importantes :
- `API_TOKEN` : si vide, pas d'auth ; si défini, il faut envoyer `Authorization: Bearer <token>` ;
- `DB_PATH` : chemin du cache SQLite ;
- `CACHE_TTL_*` : TTL par type de ressource ;
- `REQUEST_MAX_RETRIES` / `REQUEST_BACKOFF_SECONDS` : retries exponentiels côté upstream ;
- `CACHE_STALE_GRACE_SECONDS` : durée de réutilisation du cache périmé en secours ;
- `SEARCH_SCORE_THRESHOLD` : seuil minimal de matching ;
- `ENABLE_DOCS` : active `/docs` et `/redoc`.

## Lancer localement

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Lancer avec Docker Compose

```bash
docker compose up -d --build
```

API disponible sur `http://localhost:8017`.

## Versionnement

Les endpoints historiques sans préfixe restent disponibles pour compatibilité.

Pour toute nouvelle intégration, utilise la version explicite :
- `/v1/search`
- `/v1/series/{slug}`
- `/v1/volume/{series_slug}/{volume_slug}`
- etc.

## Endpoints principaux

### Santé

```bash
curl http://localhost:8017/health
```

### Recherche

```bash
curl "http://localhost:8017/search?q=one%20piece&kind=series&mode=all&limit=5"
```

```bash
curl "http://localhost:8017/search/resolve?q=one%20piece&kind=series"
```

### Série

```bash
curl "http://localhost:8017/series/One-piece-Edition-originale"
```

```bash
curl --get "http://localhost:8017/series/by-url" \
  --data-urlencode "url=https://www.manga-news.com/index.php/serie/One-piece-Edition-originale"
```

```bash
curl "http://localhost:8017/series/One-piece-Edition-originale/related"
```

```bash
curl "http://localhost:8017/series/One-piece-Edition-originale/editions?edition=all"
```

### Volume

```bash
curl "http://localhost:8017/volume/One-Piece/vol-110"
```

```bash
curl --get "http://localhost:8017/volume/by-url" \
  --data-urlencode "url=https://www.manga-news.com/index.php/manga/One-Piece/vol-110"
```

### News

```bash
curl "http://localhost:8017/news/global?limit=10"
```

```bash
curl "http://localhost:8017/news/series/One-piece-Edition-originale?limit=10"
```

```bash
curl "http://localhost:8017/news/volume/One-Piece/vol-110?limit=10"
```

### Planning

```bash
curl --get "http://localhost:8017/planning" \
  --data-urlencode "section=manga-vf" \
  --data-urlencode "year=2026" \
  --data-urlencode "month=4" \
  --data-urlencode "publisher=Glénat" \
  --data-urlencode "date_from=2026-04-01" \
  --data-urlencode "date_to=2026-04-30" \
  --data-urlencode "sort=date_asc"
```

## Projection partielle utile pour l'automatisation

### Série

```bash
curl --get "http://localhost:8017/series/One-piece-Edition-originale" \
  --data-urlencode "blocks=editions,stats" \
  --data-urlencode "fields=title,vf.volumes"
```

### Volume

```bash
curl --get "http://localhost:8017/volume/One-Piece/vol-110" \
  --data-urlencode "blocks=release,scores" \
  --data-urlencode "fields=publication_date,isbn_ean"
```

> `include_raw_sections=true` ajoute les sections textuelles brutes extraites de la page upstream.

## Administration du cache

### Stats

```bash
curl "http://localhost:8017/v1/admin/cache/stats"
```

### Invalidation ciblée

```bash
curl -X POST "http://localhost:8017/v1/admin/cache/invalidate" \
  -H 'Content-Type: application/json' \
  -d '{
    "namespace": "planning",
    "expired_only": true
  }'
```

Tu peux aussi invalider par `cache_key`, `resource_url`, ou tout vider avec `{"all_entries": true}`.

## Cache, ETag et headers utiles

Les réponses normalisées exposent :
- `ETag: "<fingerprint>"`
- `X-Data-Fingerprint: <fingerprint>`
- `X-Cache-Status: MISS|HIT|STALE`
- `Vary: Authorization, If-None-Match`
- `X-Request-ID: <id>`

Exemple de requête conditionnelle :

```bash
curl -i \
  -H 'If-None-Match: "<etag-precedent>"' \
  "http://localhost:8017/series/One-piece-Edition-originale"
```

Si la ressource n'a pas changé, l'API retourne `304 Not Modified` sans body.

## Codes de réponse utiles

- `200` : succès ;
- `304` : ressource inchangée avec `If-None-Match` ;
- `400` : paramètres invalides côté client (bloc inconnu, date invalide, URL invalide, etc.) ;
- `404` : ressource absente sur Manga News ;
- `502` : problème upstream ou parsing non fiable.

## Observabilité et robustesse upstream

- `LOG_FORMAT=json` active des logs structurés JSON réellement exploitables ;
- chaque requête HTTP reçoit un `X-Request-ID` renvoyé au client et injecté dans les logs ;
- l'upstream Manga News est appelé avec retries exponentiels sur erreurs réseau et statuts `429/500/502/503/504`.

## Notes de conception

- L'API s'appuie sur le HTML public et le flux RSS de Manga News.
- Les parsers restent volontairement tolérants pour limiter la casse lors de micro-changements HTML.
- Le cache persistant réduit les appels et sécurise les automatisations en cas de panne temporaire du site.
- La projection partielle optimise surtout le contrat JSON côté client, pas le scraping upstream lui-même.

## Documentation d'intégration

Le guide d'intégration détaillé est dans `docs/API_INTEGRATION.md`.

## GitHub / Docker / GHCR

Fichiers présents pour un dépôt propre :
- `.github/workflows/ci.yml` : lance les tests sur push / pull request ;
- `.github/workflows/publish-ghcr.yml` : build et publication GHCR ;
- `.github/workflows/manifest.yml` : inspection du manifest publié ;
- `.dockerignore` et `.gitignore` : exclusions de build et fichiers locaux.

L'image publiée par défaut suit `ghcr.io/<owner>/<repo>` en minuscules.

Pour pull une image privée depuis une autre machine, prévoir un PAT GitHub classic avec `read:packages`.
