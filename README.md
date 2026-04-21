# Manga News Private API

API non officielle, auto-hébergeable, qui convertit des pages publiques de Manga-News en JSON proprement exploitable.

Cette documentation est écrite pour être suffisante à elle seule pour :
- démarrer l'API ;
- comprendre le contrat HTTP réel ;
- intégrer l'API dans un autre service, un script ou un agent IA ;
- tester rapidement les endpoints principaux ;
- éviter les erreurs classiques de contrat.

## Ce que l'API expose réellement

Routes publiques disponibles aujourd'hui :
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

Points importants :
- il n'y a **pas** de préfixe `/v1` ;
- il n'y a **pas** de routes admin publiques dans cette version ;
- il n'y a **pas** de pagination top-level normalisée sur les listes ;
- l'authentification Bearer est **optionnelle** et dépend seulement de `API_TOKEN`.

## Ce que l'API fait bien

- recherche tolérante aux variations de ponctuation, casse, accents et espaces ;
- résolution d'un meilleur candidat avec `score` et `confidence` ;
- parsing détaillé des fiches série et volume ;
- remontée des titres alternatifs : `title_vo`, `translated_title` ;
- remontée des compteurs d'édition `vf` / `vo` sur :
  - les fiches série ;
  - les fiches volume ;
  - les résultats de recherche enrichis quand l'information parentale a pu être lue ;
- projection partielle des fiches série/volume via `blocks` et `fields` ;
- cache SQLite persistant ;
- cache négatif court ;
- support ETag / `If-None-Match`.

## Installation rapide

### Local Python

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8017
```

### Docker Compose

```bash
docker compose up -d --build
```

Accès local ensuite :
- Swagger UI : `http://localhost:8017/docs`
- ReDoc : `http://localhost:8017/redoc`
- OpenAPI brut : `http://localhost:8017/openapi.json`

## Authentification

Si `API_TOKEN` est vide, l'API est ouverte sur le réseau où elle tourne.

Si `API_TOKEN` est défini, toutes les routes publiques attendent :

```http
Authorization: Bearer <API_TOKEN>
```

L'état actuel du code n'expose pas de routes admin séparées. `ADMIN_TOKEN` existe encore dans la configuration comme réserve de conception, mais n'est pas utilisé par les routes HTTP publiques actuelles.

## Réponses : enveloppe commune

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

Exceptions :
- `/health` renvoie simplement `{ "ok": true }`.

## Headers utiles

Headers réellement émis aujourd'hui :
- `ETag: "<fingerprint>"`
- `X-Data-Fingerprint: <fingerprint>`

Utilisation recommandée :
1. stocker l'`ETag` reçu ;
2. renvoyer ensuite `If-None-Match: "<fingerprint>"` ;
3. si la ressource n'a pas changé, l'API répond `304 Not Modified`.

## Endpoints : démarrage recommandé

### Vérifier l'API

```bash
curl http://localhost:8017/health
```

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

## Matching tolérant des titres

L'API ne compare pas naïvement les titres bruts.

Avant scoring, les titres sont normalisés :
- accents retirés ;
- casse ignorée ;
- ponctuation remplacée par des espaces ;
- espaces normalisés ;
- `&` remplacé par `and`.

Exemple important :
- Manga-News : `Dogs: Bullets & Carnage`
- côté client : `Dogs - Bullets & Carnage`

Le résultat peut quand même sortir avec un `score` très élevé, parce que les deux formes convergent vers une version normalisée très proche.

Ce comportement est implémenté dans :
- `app/utils.py` → `normalize_text(...)`
- `app/utils.py` → `score_match(...)`
- `app/manga_news/parsers.py` → `parse_search_page(...)`

## Champs métier importants

### Dans les résultats de recherche

Les résultats `/search` et `/search/resolve` peuvent contenir :
- `title`
- `url`
- `kind`
- `score`
- `slug`
- `series_slug`
- `volume_slug`
- `number`
- `number_int`
- `edition_label`
- `is_special`
- `is_one_shot`
- `title_vo`
- `translated_title`
- `vf`
- `vo`

`vf` et `vo` sont surtout utiles quand le résultat peut être rattaché à une fiche série détaillée.

### Dans les fiches série

Une fiche série contient notamment :
- `title`
- `title_vo`
- `translated_title`
- `summary`
- `authors_story`
- `authors_art`
- `publisher_fr`
- `publisher_vo`
- `genres`
- `vf`
- `vo`
- `last_release_date`
- `next_release_date`
- `stats`
- `related`

### Dans les fiches volume

Une fiche volume contient notamment :
- `title`
- `series_title`
- `number`
- `number_int`
- `edition_label`
- `is_special`
- `is_one_shot`
- `title_vo`
- `translated_title`
- `publication_date`
- `isbn_ean`
- `price_code`
- `editorial_score`
- `reader_score`
- `vf`
- `vo`

`vf` / `vo` sur un volume ne viennent pas de la page volume elle-même, mais de la fiche série parente quand elle a pu être relue.

## Documentation détaillée

- [Guide d'intégration API](docs/API_INTEGRATION.md)
- [Architecture et flux internes](docs/ARCHITECTURE.md)
- [Déploiement et exploitation](docs/DEPLOYMENT_AND_OPERATIONS.md)
- [OpenAPI, Swagger, ReDoc et usage IA](docs/OPENAPI_AND_AI_USAGE.md)
- [Cas d'usage et recettes](docs/USE_CASES_AND_RECIPES.md)
- [Scénario de test One Piece](docs/ONE_PIECE_API_TESTS.txt)
- [Changelog de contrat API](docs/API_CHANGELOG.md)
- [Exemples JSON validés](docs/examples/README.md)

## Validation avant livraison

```bash
python scripts/validate_contract_and_docs.py
pytest -q
```

Ces commandes vérifient :
- le schéma OpenAPI ;
- les liens markdown ;
- l'absence de références documentaires à des routes inexistantes ;
- la validité des exemples JSON ;
- les tests unitaires et d'intégration du projet.
