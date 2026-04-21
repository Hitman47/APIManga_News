# Manga News Private API

API non officielle, auto-hébergeable, qui transforme des pages publiques de Manga News en JSON exploitable par un service, une UI ou une autre IA.

Cette documentation est volontairement stricte : elle décrit **uniquement** le contrat réellement exposé par le code actuel. Si tu vois un écart entre un guide narratif et `/openapi.json`, considère que `/openapi.json` et le code ont priorité.

## Ce que l'API fait aujourd'hui

- recherche floue de séries et de volumes via Manga News ;
- résolution du meilleur candidat avec score et niveau de confiance ;
- enrichissement des résultats de recherche série avec le nombre de tomes VF et VO quand Manga News les expose sur la fiche série ;
- fiches détaillées de séries et de volumes ;
- extraction des liens liés à une série ;
- extraction des éditions VF / VO d'une série ;
- news globales, news de série et news de volume ;
- planning VF / VO avec filtres locaux ;
- cache SQLite persistant ;
- `ETag` et `X-Data-Fingerprint` sur les réponses enveloppées ;
- negative cache court pour éviter de refrapper immédiatement une page absente ou cassée ;
- dump HTML optionnel quand un parse échoue ;
- documentation Swagger / ReDoc / OpenAPI ;
- exemples JSON validés et script de validation doc/contrat.

## Ce que l'API **ne** fait **pas** aujourd'hui

Le projet contient quelques briques internes ou variables de config qui ne constituent **pas** encore un contrat public actif.

Ne suppose pas l'existence de :
- préfixe `/v1` ;
- routes admin (`/admin/...`) ;
- endpoint `lookup/volume` ;
- pagination normalisée commune sur tous les endpoints ;
- recherche dédiée par `title_vo=` ou `translated_title=` ;
- rate limiting effectivement branché sur les routes publiques.

## Contrat public réel

Le contrat public actuel est **non versionné**. Les routes à utiliser sont exactement celles de `/openapi.json`.

Routes publiques actuellement exposées :
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

## Lecture recommandée

Pour démarrer proprement :
1. ce `README.md` ;
2. [`docs/API_INTEGRATION.md`](docs/API_INTEGRATION.md) ;
3. [`docs/OPENAPI_AND_AI_USAGE.md`](docs/OPENAPI_AND_AI_USAGE.md) ;
4. `/openapi.json` ;
5. [`docs/examples/`](docs/examples/README.md).

## Installation locale

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8017
```

API disponible sur `http://localhost:8017`.

Documentation interactive :
- Swagger UI : `http://localhost:8017/docs`
- ReDoc : `http://localhost:8017/redoc`
- OpenAPI brut : `http://localhost:8017/openapi.json`

## Lancement avec Docker Compose

```bash
docker compose up -d --build
```

Par défaut :
- port hôte : `8017`
- port conteneur : `8000`
- base SQLite persistée dans `./data`

## Variables d'environnement utiles

Voir [`.env.example`](.env.example) pour la liste complète.

Variables qui ont un effet concret sur les routes publiques actuelles :
- `API_TOKEN`
- `MANGA_NEWS_BASE_URL`
- `USER_AGENT`
- `DB_PATH`
- `REQUEST_TIMEOUT_SECONDS`
- `CACHE_STALE_GRACE_SECONDS`
- `CACHE_TTL_SEARCH_SECONDS`
- `CACHE_TTL_SERIES_SECONDS`
- `CACHE_TTL_VOLUME_SECONDS`
- `CACHE_TTL_NEWS_GLOBAL_SECONDS`
- `CACHE_TTL_NEWS_SERIES_SECONDS`
- `CACHE_TTL_PLANNING_SECONDS`
- `SEARCH_SCORE_THRESHOLD`
- `MAX_LIMIT`
- `ENABLE_DOCS`
- `DEBUG_CAPTURE_HTML_ON_ERROR`
- `DEBUG_HTML_DUMP_DIR`
- `NEGATIVE_CACHE_ENABLED`
- `NEGATIVE_CACHE_TTL_SECONDS`

Variables présentes dans `Settings` mais non exposées comme contrat public au niveau des routes aujourd'hui :
- `ADMIN_TOKEN`
- `DEFAULT_LIMIT`
- `RATE_LIMIT_*`

## Authentification

Si `API_TOKEN` est vide, l'API publique est accessible sans Bearer token.

Si `API_TOKEN` est défini, toutes les routes publiques attendent :

```http
Authorization: Bearer <api-token>
```

Réponse en cas d'absence ou d'erreur de token :

```json
{
  "code": "AUTH_REQUIRED",
  "detail": "Missing or invalid bearer token."
}
```

## Enveloppe commune

Toutes les routes métier renvoient une enveloppe stable du même type général.

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
  "fingerprint": "fp-example",
  "data": {}
}
```

### Champs clés de recherche

Sur `/search` et `/search/resolve`, les résultats exposent maintenant, selon le type de ressource et les données relues depuis la fiche détaillée :
- `title` ;
- `title_vo` ;
- `translated_title` ;
- `score` ;
- `slug`, `series_slug`, `volume_slug` ;
- `vf` et `vo` **pour les résultats de type `series`**, avec le nombre de tomes et le statut (`En cours`, `Terminé`, `En pause`, etc.) quand Manga News l'affiche sur la fiche série.

Exemple : une recherche sur `Dogs - Bullets & Carnage` peut renvoyer le titre Manga News `Dogs: Bullets & Carnage` avec un `score` élevé, plus `vf` / `vo` si la fiche série expose ces compteurs.

### Sens des champs d'enveloppe

- `schema_version` : version du format d'enveloppe ;
- `ok` : `true` si la requête a produit une réponse métier ;
- `found` : `false` si aucune ressource ou aucun candidat n'a été trouvé ;
- `source` : source logique, ici `manga_news` ;
- `source_url` : URL source utilisée côté Manga News ;
- `cached` : `true` si la réponse vient du cache ;
- `fetched_at` : date/heure de création ou de récupération de l'entrée ;
- `cache_expires_at` : date/heure d'expiration du cache positif ;
- `partial` : `true` si une entrée stale a été servie en fallback ;
- `warnings` : avertissements textuels, par exemple en cas de stale fallback ;
- `fingerprint` : condensat du payload utile pour les `ETag` ;
- `data` : payload métier.

## Headers utiles

Headers réellement exposés aujourd'hui sur les réponses enveloppées :
- `ETag`
- `X-Data-Fingerprint`

### Requête conditionnelle

```http
If-None-Match: "<fingerprint>"
```

Si le fingerprint n'a pas changé, l'API renvoie `304 Not Modified`.

## Erreurs stables

Les erreurs applicatives utilisent un format simple et stable :

```json
{
  "code": "UPSTREAM_PARSE_ERROR",
  "detail": "Unable to parse the requested Manga News page."
}
```

Codes à gérer côté client :
- `AUTH_REQUIRED`
- `RESOURCE_NOT_FOUND`
- `UPSTREAM_FETCH_ERROR`
- `UPSTREAM_PARSE_ERROR`

## Matching tolérant des titres

La recherche n'est pas un `contains` brut. Avant comparaison, l'API normalise les titres et calcule un score de similarité.

Normalisation actuelle :
- accents retirés ;
- casse ignorée ;
- ponctuation remplacée par des espaces ;
- espaces normalisés ;
- `&` remplacé par `and` ;
- certains bruits éditoriaux réduits (`collector`, `édition originale`, `vol.`, `tome`, etc.).

Exemple :
- chez toi : `Dogs - Bullets & Carnage`
- sur Manga News : `Dogs: Bullets & Carnage`

Ces deux formes convergent vers une forme normalisée proche de :

```text
dogs bullets and carnage
```

Le champ `score` des résultats de recherche est déjà le signal de similarité exploitable côté client.

## Exemples d'appels rapides

### Santé

```bash
curl http://localhost:8017/health
```

### Recherche série

```bash
curl --get "http://localhost:8017/search" \
  --data-urlencode "q=one piece" \
  --data-urlencode "kind=series" \
  --data-urlencode "mode=all" \
  --data-urlencode "limit=5"
```

### Résolution du meilleur candidat

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

### Planning filtré

```bash
curl --get "http://localhost:8017/planning" \
  --data-urlencode "section=manga-vf" \
  --data-urlencode "year=2026" \
  --data-urlencode "month=4" \
  --data-urlencode "publisher=Glénat" \
  --data-urlencode "q=one piece" \
  --data-urlencode "sort=date_asc" \
  --data-urlencode "limit=25"
```

## Champs métier à connaître

### Recherche

Chaque résultat de recherche peut contenir :
- `title`
- `url`
- `kind`
- `score`
- `slug`
- `series_slug`
- `volume_slug`
- `title_vo`
- `translated_title`

### Volume détaillé

Les volumes exposent notamment :
- `number`
- `number_int`
- `edition_label`
- `is_special`
- `is_one_shot`
- `title_vo`
- `translated_title`
- `publication_date`
- `isbn_ean`

### Planning

Les items de planning exposent aussi la normalisation volume quand elle peut être inférée :
- `number`
- `number_int`
- `edition_label`
- `is_special`
- `is_one_shot`

## Projections légères

Les routes détail `series` et `volume` supportent :
- `blocks=` pour demander des blocs métier ;
- `fields=` pour demander des chemins précis ;
- `include_raw_sections=true` pour inclure les sections brutes parsées.

Exemples :

```bash
curl --get "http://localhost:8017/series/One-piece-Edition-originale" \
  --data-urlencode "blocks=identity,editions" \
  --data-urlencode "fields=stats.likes"
```

```bash
curl --get "http://localhost:8017/volume/One-Piece/vol-91" \
  --data-urlencode "blocks=identity,release" \
  --data-urlencode "fields=cover_image"
```

## Debug de parsing

Si une page Manga News change et qu'un parser casse, tu peux activer :

```env
DEBUG_CAPTURE_HTML_ON_ERROR=true
DEBUG_HTML_DUMP_DIR=/tmp/manga-news-debug-html
```

Quand un `ParseError` survient sur une route cacheable, le message peut alors inclure :

```text
Debug HTML saved to /tmp/manga-news-debug-html/...
```

## Validation de la doc et du contrat

Validation rapide :

```bash
python scripts/validate_contract_and_docs.py
pytest
```

Les exemples JSON canoniques sont dans [`docs/examples/`](docs/examples/README.md).

## Documents complémentaires

- [Guide d’intégration](docs/API_INTEGRATION.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Déploiement et exploitation](docs/DEPLOYMENT_AND_OPERATIONS.md)
- [OpenAPI et usage par une IA](docs/OPENAPI_AND_AI_USAGE.md)
- [Cas d’usage et recettes](docs/USE_CASES_AND_RECIPES.md)
- [Scénario de tests One Piece](docs/ONE_PIECE_API_TESTS.txt)
- [Changelog du contrat](docs/API_CHANGELOG.md)
