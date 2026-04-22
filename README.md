# Manga News Private API

API privée et auto-hébergeable pour interroger **Manga News**, normaliser les réponses utiles, puis les exposer en JSON avec cache SQLite et ETag.

Le projet est pensé pour deux usages :
- **un outil personnel** qui a besoin d'une source JSON stable au-dessus du HTML de Manga News ;
- **une autre IA ou un autre développeur** qui doit pouvoir démarrer rapidement sans relire tout le code.

## Ce que l'API fait réellement

Routes publiques actuellement disponibles :
- `GET /health`
- `GET /search`
- `GET /search/resolve`
- `GET /series/{slug}`
- `GET /series/by-url`
- `GET /series/{slug}/related`
- `GET /series/by-url/related`
- `GET /series/{slug}/editions`
- `GET /series/by-url/editions`
- `GET /volume/{series_slug}/{volume_slug}`
- `GET /volume/by-url`
- `GET /news/global`
- `GET /news/series/{slug}`
- `GET /news/volume/{series_slug}/{volume_slug}`
- `GET /news/volume/by-url`
- `GET /planning`

Fonctions utiles déjà en place :
- recherche série / volume ;
- résolution du meilleur match ;
- fiches détaillées série et volume ;
- titres alternatifs `title_vo` et `translated_title` sur les fiches détaillées **et** dans les résultats de recherche quand l'enrichissement réussit ;
- compteurs d'éditions `vf` / `vo` sur les fiches série, sur les fiches volume enrichies depuis la série parente, et dans les résultats de recherche enrichis ;
- normalisation volume : `number`, `number_int`, `edition_label`, `is_special`, `is_one_shot` sur les fiches volume, le planning, les éditions de série, et les résultats de recherche enrichis ;
- projections légères via `blocks`, `fields` et `include_raw_sections` sur les routes détail série / volume ;
- cache SQLite persistant avec stale cache, negative cache, connexion réutilisée, mode WAL et `busy_timeout` ;
- anti-stampede local (`single-flight`) pour éviter plusieurs fetchs identiques en parallèle sur une même clé ;
- cache source des pages de recherche, réutilisé entre `mode=best` / `mode=all` et entre plusieurs limites pour une même requête ;
- ETag / `If-None-Match` / `304 Not Modified` ;
- documentation OpenAPI native via `/docs`, `/redoc`, `/openapi.json` ;
- exemples JSON versionnés dans `docs/examples/`.

## Points performance déjà actifs

Les optimisations suivantes sont maintenant réellement branchées dans le runtime :
- retries HTTP et backoff via `REQUEST_MAX_RETRIES` et `REQUEST_BACKOFF_SECONDS` ;
- logs texte **ou JSON** via `LOG_FORMAT=text|json` ;
- cache SQLite réutilisant la même connexion, en mode WAL ;
- déduplication des fetchs concurrents identiques côté service ;
- enrichissement de recherche mutualisé : une même série parente n'est pas refetchée plusieurs fois dans la même recherche ;
- pages de recherche source cachées indépendamment du rendu final, pour éviter de relire l'upstream quand seul `mode` ou `limit` change.

Deux variables règlent la concurrence sur les parties les plus coûteuses :
- `SEARCH_SOURCE_CONCURRENCY`
- `SEARCH_ENRICHMENT_CONCURRENCY`

## Ce que l'API ne fait pas

Important pour éviter les mauvaises hypothèses :
- **pas** de préfixe `/v1` ;
- **pas** d'endpoint public de watch / monitoring métier ;
- **pas** de multi-provider : la source métier est Manga News ;
- **pas** de pagination métier normalisée dans les réponses ;
- **pas** d'admin API publique aujourd'hui ;
- **pas** de recherche dédiée du type `title_vo=...` ou `translated_title=...` : les titres alternatifs sont exposés, pas recherchés séparément.

## Lecture recommandée de la doc

Pour un humain ou une IA, l'ordre utile est :
1. ce `README.md` ;
2. [`docs/API_INTEGRATION.md`](docs/API_INTEGRATION.md) ;
3. [`docs/OPENAPI_AND_AI_USAGE.md`](docs/OPENAPI_AND_AI_USAGE.md) ;
4. [`docs/examples/README.md`](docs/examples/README.md) et quelques JSON réels ;
5. [`docs/USE_CASES_AND_RECIPES.md`](docs/USE_CASES_AND_RECIPES.md) ;
6. [`docs/DEPLOYMENT_AND_OPERATIONS.md`](docs/DEPLOYMENT_AND_OPERATIONS.md) si tu déploies ;
7. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) si tu veux comprendre les choix internes.

## Démarrage rapide

### Local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Par défaut, Uvicorn servira l'API sur `http://localhost:8000`.

### Docker Compose

```bash
docker compose up -d --build
```

Le `docker-compose.yml` expose le conteneur sur `http://localhost:8017`.

## Authentification

Si `API_TOKEN` est vide, l'API est ouverte.

Si `API_TOKEN` est défini, toutes les routes publiques attendent :

```http
Authorization: Bearer <token>
```

En cas d'échec, la réponse actuelle est :

```json
{
  "detail": {
    "code": "AUTH_REQUIRED",
    "detail": "Missing or invalid bearer token."
  }
}
```

Oui, ce format 401 n'est pas identique aux 404/502. La doc le documente tel qu'il est aujourd'hui, sans prétendre qu'il est plus propre qu'il ne l'est.

## Premiers appels utiles

### Health

```bash
curl http://localhost:8017/health
```

### Recherche de série

```bash
curl --get "http://localhost:8017/search" \
  --data-urlencode "q=one piece" \
  --data-urlencode "kind=series" \
  --data-urlencode "mode=all" \
  --data-urlencode "limit=5"
```

### Résolution directe du meilleur résultat

```bash
curl --get "http://localhost:8017/search/resolve" \
  --data-urlencode "q=one piece tome 91" \
  --data-urlencode "kind=volume" \
  --data-urlencode "limit=10"
```

### Fiche série

```bash
curl "http://localhost:8017/series/One-piece-Edition-originale"
```

### Fiche volume

```bash
curl "http://localhost:8017/volume/One-Piece/vol-91"
```

### Planning VF filtré

```bash
curl --get "http://localhost:8017/planning" \
  --data-urlencode "section=manga-vf" \
  --data-urlencode "year=2026" \
  --data-urlencode "month=4" \
  --data-urlencode "publisher=Glénat" \
  --data-urlencode "sort=date_asc" \
  --data-urlencode "limit=25"
```

### Même appel avec token

```bash
curl -H "Authorization: Bearer MON_TOKEN" \
  "http://localhost:8017/search?q=one%20piece"
```

## Contrat HTTP commun

La plupart des routes renvoient une enveloppe comme celle-ci :

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
  "data": {}
}
```

Les champs importants :
- `cached`: la réponse vient du cache local ;
- `partial`: l'API a servi une entrée stale car l'upstream a échoué ;
- `warnings`: détails utiles quand `partial=true` ;
- `fingerprint`: hash métier utilisé pour l'ETag ;
- `source_url`: page Manga News réellement utilisée.

### Headers utiles

Sur les routes enveloppées, l'API peut renvoyer :
- `ETag: "<fingerprint>"`
- `X-Data-Fingerprint: <fingerprint>`

Tu peux ensuite rejouer la requête avec :

```http
If-None-Match: "<fingerprint>"
```

Si rien n'a changé, la réponse sera `304 Not Modified`.

## Projections série / volume

Les routes détail série et volume acceptent :
- `blocks` : blocs métier prédéfinis ;
- `fields` : chemins ciblés ;
- `include_raw_sections=true` : inclut `raw_sections`.

Exemple minimal sur une série :

```bash
curl --get "http://localhost:8017/series/One-piece-Edition-originale" \
  --data-urlencode "fields=title,vf.volumes,next_release_date"
```

Exemple sur un volume :

```bash
curl --get "http://localhost:8017/volume/One-Piece/vol-110" \
  --data-urlencode "blocks=identity,release" \
  --data-urlencode "fields=cover_image"
```

## Exemples JSON fournis

Voir [`docs/examples/README.md`](docs/examples/README.md).

Les exemples les plus utiles pour démarrer sont :
- [`docs/examples/search_response_one_piece.json`](docs/examples/search_response_one_piece.json)
- [`docs/examples/resolve_response_one_piece.json`](docs/examples/resolve_response_one_piece.json)
- [`docs/examples/series_one_piece.json`](docs/examples/series_one_piece.json)
- [`docs/examples/volume_one_piece_110.json`](docs/examples/volume_one_piece_110.json)
- [`docs/examples/planning_example.json`](docs/examples/planning_example.json)
- [`docs/examples/error_upstream_parse.json`](docs/examples/error_upstream_parse.json)

## Validation locale

Avant de livrer ou consommer l'API :

```bash
python scripts/validate_contract_and_docs.py
pytest
```

## Notes honnêtes sur l'état actuel

Quelques variables existent dans la config mais **ne pilotent pas encore les routes publiques actuelles** :
- `ADMIN_TOKEN`
- `REQUEST_MAX_RETRIES`
- `REQUEST_BACKOFF_SECONDS`
- `DEFAULT_LIMIT`
- `LOG_FORMAT`
- `RATE_LIMIT_*`

Elles sont présentes parce que le projet a déjà préparé ces concepts, mais la doc n'en fait pas des features actives tant qu'elles ne sont pas réellement branchées au runtime.

## Note importante sur `vf` / `vo`

Les compteurs `vf` / `vo` proviennent en priorité du bloc HTML `#numberblock` des fiches série Manga-News.
Quand un résultat de recherche cible un **volume**, l'API relit aussi la fiche **série parente** pour injecter ces compteurs dans le résultat.

Après un changement de parseur, il faut redémarrer l'API. Les clés de cache métier intègrent désormais une version interne, ce qui évite de relire un ancien payload incompatible après mise à jour.


## Note de cache importante

Les réponses `series`, `volume`, `search` et `search/resolve` dépendent d'un cache SQLite local. Quand le parseur évolue (par exemple pour mieux remonter `vf` / `vo`), l'application ignore automatiquement les anciennes entrées de cache incompatibles grâce à une version interne de schéma de cache. Après déploiement, un simple redémarrage de l'API suffit normalement à voir les nouvelles données. Supprimer le fichier SQLite de cache reste la méthode la plus radicale si vous voulez repartir d'un cache totalement vierge.

## Réglages de configuration restaurés

La configuration `.env.example` réexpose maintenant les réglages de tuning qui avaient disparu :

- `SQLITE_BUSY_TIMEOUT_MS` : pilote le `PRAGMA busy_timeout` réellement appliqué à SQLite ;
- `CACHE_MEMORY_ENTRIES` : pilote le cache mémoire L1 au-dessus de SQLite ;
- `SEARCH_DEFAULT_ENRICH` : valeur par défaut de `enrich` sur `/search` et `/search/resolve` ;
- `SEARCH_DEFAULT_INCLUDE_EDITIONS` : valeur par défaut de `include_editions` sur `/search` et `/search/resolve` ;
- `VOLUME_DEFAULT_INCLUDE_PARENT_EDITIONS` : valeur par défaut de `include_parent_editions` sur `/volume` ; la valeur recommandée est `false` pour éviter un refetch série implicite sur chaque lecture volume.

Compatibilité conservée :

- `SEARCH_FETCH_CONCURRENCY` reste accepté comme alias de `SEARCH_SOURCE_CONCURRENCY` ;
- `SEARCH_ENRICH_CONCURRENCY` reste accepté comme alias de `SEARCH_ENRICHMENT_CONCURRENCY`.
