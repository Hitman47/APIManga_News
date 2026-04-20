# Manga News Private API

API privée, légère et auto-hébergeable, conçue pour servir d'interface stable entre Manga News et un autre projet. Elle met en cache les réponses dans SQLite, supporte une authentification Bearer optionnelle, expose une doc OpenAPI via FastAPI et fournit un contrat JSON suffisamment stable pour être consommé par un autre service ou une autre IA.

## Fonctionnalités disponibles

- recherche de séries et de volumes ;
- résolution directe du meilleur match via `/search/resolve` ;
- récupération d'une fiche série ;
- récupération d'une fiche volume ;
- récupération des news globales via RSS ;
- récupération des news d'une série ;
- récupération des news d'un volume ;
- récupération du planning manga VF et manga VO ;
- filtres locaux sur le planning : éditeur, plage de dates, recherche textuelle, tri ;
- cache SQLite persistant avec fallback sur cache périmé si l'upstream casse temporairement ;
- support `ETag` / `If-None-Match` / `304 Not Modified` ;
- docs OpenAPI natives de FastAPI sur `/docs` et `/redoc`.

## Ce que cette version ne fait pas encore

- provider anime séparé ;
- enrichissement cross-source ;
- pagination multi-pages automatisée côté upstream ;
- webhooks ;
- endpoints admin de cache.

## Variables d'environnement principales

Consulte `.env.example`.

Les plus importantes :

- `API_TOKEN` : si vide, pas d'auth ; si défini, il faut envoyer `Authorization: Bearer <token>` ;
- `DB_PATH` : chemin du cache SQLite ;
- `CACHE_TTL_*` : TTL par type de ressource ;
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

L'API sera alors disponible sur `http://localhost:8017`.

## Documentation

- Swagger UI : `http://localhost:8017/docs`
- ReDoc : `http://localhost:8017/redoc`
- Guide d'intégration détaillé : [`docs/API_INTEGRATION.md`](docs/API_INTEGRATION.md)

## Contrat de réponse global

Tous les endpoints métier renvoient une enveloppe JSON de ce type :

```json
{
  "ok": true,
  "found": true,
  "source": "manga_news",
  "source_url": "https://www.manga-news.com/...",
  "cached": true,
  "fetched_at": "2026-04-20T12:00:00+00:00",
  "cache_expires_at": "2026-04-21T12:00:00+00:00",
  "partial": false,
  "warnings": [],
  "schema_version": "1.0",
  "fingerprint": "<sha256>",
  "data": {}
}
```

### Sens des champs transverses

- `ok` : succès logique ;
- `found` : vrai si la ressource ou la liste a produit un résultat exploitable ;
- `source` : toujours `manga_news` actuellement ;
- `source_url` : URL Manga News utilisée ;
- `cached` : réponse issue du cache SQLite ;
- `fetched_at` : date de récupération/source cache ;
- `cache_expires_at` : fin de fraîcheur du cache ;
- `partial` : vrai si un cache périmé a été servi après échec upstream ;
- `warnings` : messages non bloquants ;
- `schema_version` : version de contrat de l'enveloppe ;
- `fingerprint` : hash stable du contenu `data`, réutilisé pour les ETag ;
- `data` : charge utile spécifique à l'endpoint.

## ETag / 304

Les endpoints métier renvoient :

- `ETag: "<fingerprint>"`
- `X-Data-Fingerprint: <fingerprint>`

Si le client renvoie ensuite :

```http
If-None-Match: "<fingerprint>"
```

et que les données n'ont pas changé, l'API répond :

- `304 Not Modified`
- sans corps JSON

C'est utile pour éviter de retraiter une même fiche côté autre projet.

## Endpoints principaux

### Health

```bash
curl http://localhost:8017/health
```

### Recherche simple

```bash
curl "http://localhost:8017/search?q=one%20piece&kind=series&mode=all&limit=5"
```

### Résolution directe du meilleur match

```bash
curl "http://localhost:8017/search/resolve?q=one%20piece&kind=series"
```

### Fiche série via slug

```bash
curl "http://localhost:8017/series/One-piece-Edition-originale"
```

### Fiche série via URL

```bash
curl --get "http://localhost:8017/series/by-url" \
  --data-urlencode "url=https://www.manga-news.com/index.php/serie/One-piece-Edition-originale"
```

### Fiche volume via slug

```bash
curl "http://localhost:8017/volume/One-Piece/vol-110"
```

### Fiche volume via URL

```bash
curl --get "http://localhost:8017/volume/by-url" \
  --data-urlencode "url=https://www.manga-news.com/index.php/manga/One-Piece/vol-110"
```

### News globales

```bash
curl "http://localhost:8017/news/global?limit=10"
```

### News d'une série

```bash
curl "http://localhost:8017/news/series/One-piece-Edition-originale?limit=10"
```

### News d'un volume

```bash
curl "http://localhost:8017/news/volume/One-Piece/vol-110?limit=10"
```

### Planning manga VF

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

### Avec Bearer token

```bash
curl -H "Authorization: Bearer MON_TOKEN" "http://localhost:8017/search?q=one%20piece"
```

## Notes d'intégration

- depuis la machine hôte : `http://localhost:8017`
- depuis un autre conteneur Docker sur le même réseau : `http://manga-news-api:8000`
- si `API_TOKEN` est défini, tous les appels doivent inclure `Authorization: Bearer <token>`
- pour une intégration pilotée par un autre service, préfère en général :
  1. `/search/resolve`
  2. puis `/series/{slug}` ou `/volume/{series_slug}/{volume_slug}`
- pour économiser du traitement côté client, exploite `ETag` et `If-None-Match`.

## GitHub / GHCR

Fichiers utiles :

- `.github/workflows/ci.yml` : lance les tests ;
- `.github/workflows/publish-ghcr.yml` : build multi-arch `linux/amd64` + `linux/arm64` et push vers GHCR ;
- `.github/workflows/manifest.yml` : inspecte le manifest publié ;
- `.dockerignore` : évite d'envoyer les fichiers inutiles au build Docker ;
- `.gitignore` : ignore l'environnement local, le cache et la base SQLite.

Image publiée par défaut : `ghcr.io/<owner>/<repo>` en minuscules.

### Secrets et permissions

Pour publier vers GHCR depuis GitHub Actions, le workflow utilise `GITHUB_TOKEN`.

Pour pull une image privée depuis Portainer, Docker Compose ou une autre machine, prévois un PAT GitHub classic avec au minimum `read:packages`.
