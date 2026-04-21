# Manga News Private API

API privée non officielle pour lire et normaliser des pages Manga-News.

Cette base expose **uniquement** les routes réellement présentes dans `/openapi.json` :

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

## Ce que fait réellement l'API

- parsing détaillé des fiches série et volume ;
- recherche floue tolérante à la ponctuation et aux variantes proches ;
- remontée des titres alternatifs `title_vo` et `translated_title` ;
- remontée des compteurs d'édition `vf` / `vo` quand Manga-News les expose ;
- projection partielle des fiches via `blocks` et `fields` ;
- cache SQLite persistant ;
- cache négatif court ;
- version interne de clé de cache pour éviter de relire d'anciens payloads incompatibles après un changement de parseur ou d'enrichissement ;
- `ETag` et `X-Data-Fingerprint` pour les clients qui veulent éviter des relectures inutiles.

## Ce que cette version **ne** fait pas

- pas de préfixe `/v1` ;
- pas de route admin publique ;
- pas de route `lookup/volume` ;
- pas d'écriture sur Manga-News ;
- pas de garantie que le HTML de Manga-News restera stable dans le temps.

## Installation rapide

### Local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8017
```

### Docker

```bash
docker compose up -d --build
```

## Authentification

Si `API_TOKEN` est défini, toutes les routes métier attendent :

```http
Authorization: Bearer <API_TOKEN>
```

Si `API_TOKEN` est vide, l'API est lisible sans authentification.

## Enveloppe de réponse

Toutes les routes métier renvoient une enveloppe de ce type :

```json
{
  "schema_version": "1.0",
  "ok": true,
  "found": true,
  "source": "manga_news",
  "source_url": "https://www.manga-news.com/...",
  "cached": false,
  "fetched_at": "2026-04-21T10:10:10+00:00",
  "cache_expires_at": "2026-04-22T10:10:10+00:00",
  "partial": false,
  "warnings": [],
  "fingerprint": "...",
  "data": {}
}
```

## Headers utiles

- `ETag` : dérivé du `fingerprint` de `data` ;
- `X-Data-Fingerprint` : même information, plus simple à lire ;
- `304 Not Modified` si `If-None-Match` correspond à l'`ETag` courant.

## Cas d'usage recommandés

### Trouver une série

```bash
curl --get "http://localhost:8017/search/resolve" \
  --data-urlencode "q=one piece" \
  --data-urlencode "kind=series"
```

### Lire la fiche série

```bash
curl "http://localhost:8017/series/One-piece-Edition-originale"
```

### Trouver un volume

```bash
curl --get "http://localhost:8017/search/resolve" \
  --data-urlencode "q=one piece tome 91" \
  --data-urlencode "kind=volume"
```

### Lire la fiche volume

```bash
curl "http://localhost:8017/volume/One-Piece/vol-91"
```

### Lire le planning VF

```bash
curl --get "http://localhost:8017/planning" \
  --data-urlencode "section=manga-vf" \
  --data-urlencode "year=2026" \
  --data-urlencode "month=4" \
  --data-urlencode "publisher=Glénat"
```

## Matching tolérant des titres

Le projet normalise les chaînes avant comparaison (`app/utils.py`) :

- accents supprimés ;
- casse ignorée ;
- ponctuation remplacée ;
- espaces normalisés ;
- `&` converti en `and`.

Exemple :

- Manga-News : `Dogs: Bullets & Carnage`
- côté client : `Dogs - Bullets & Carnage`

Ces deux formes convergent vers une forme normalisée équivalente. Le résultat est visible dans :

- `score` sur `/search` ;
- `score` et `confidence` sur `/search/resolve`.

## Où trouver les compteurs VF / VO

Les compteurs `vf` / `vo` viennent du bloc HTML `#numberblock` côté Manga-News.

Ils sont utiles :

- sur les résultats `series`, directement depuis la fiche série ;
- sur les résultats `volume`, via la fiche volume puis la série parente ;
- sur `/search/resolve`, puisque cette route réutilise les résultats enrichis de `/search` ;
- sur les fiches détaillées `/series/{slug}` et `/volume/{series_slug}/{volume_slug}`.

### Important

Sur un volume, `vf` / `vo` ne viennent pas de la page volume elle-même :
- la page volume fournit l'identité du tome ;
- la série parente fournit les compteurs globaux.

## Dépannage rapide : compteurs VF/VO à `null`

Si tu vois encore `vf` / `vo` à `null` alors que la page Manga-News les affiche clairement :

- vérifie d'abord si la réponse est `cached: true` ;
- redémarre l'application avec le code le plus récent ;
- au besoin supprime le fichier SQLite de cache (`DB_PATH`) pour forcer une régénération immédiate ;
- vérifie enfin la page source : l'API lit ces compteurs dans le bloc HTML `#numberblock`.

## Fichiers de doc à lire ensuite

- [API_INTEGRATION.md](docs/API_INTEGRATION.md)
- [ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [DEPLOYMENT_AND_OPERATIONS.md](docs/DEPLOYMENT_AND_OPERATIONS.md)
- [OPENAPI_AND_AI_USAGE.md](docs/OPENAPI_AND_AI_USAGE.md)
- [USE_CASES_AND_RECIPES.md](docs/USE_CASES_AND_RECIPES.md)
- [ONE_PIECE_API_TESTS.txt](docs/ONE_PIECE_API_TESTS.txt)
- [API_CHANGELOG.md](docs/API_CHANGELOG.md)
- [docs/examples/README.md](docs/examples/README.md)

## Validation avant livraison

```bash
python scripts/validate_contract_and_docs.py
pytest
```

Le script de smoke test vérifie le contrat HTTP. `pytest` vérifie le projet.
