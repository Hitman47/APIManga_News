# Manga News Private API

API privée, légère, prévue pour un usage personnel ou auto-hébergé, afin d'interroger Manga News avec un cache SQLite et une authentification Bearer optionnelle.

## Ce que fait cette V1

- recherche de séries et volumes ;
- récupération d'une fiche série ;
- récupération d'une fiche volume ;
- récupération des news globales via RSS ;
- récupération des news d'une série ;
- récupération des news d'un volume ;
- récupération du planning manga VF et manga VO ;
- filtres locaux sur le planning : éditeur, plage de dates, recherche textuelle, tri ;
- cache SQLite persistant avec fallback sur cache périmé si l'upstream casse temporairement ;
- docs OpenAPI natives de FastAPI sur `/docs` et `/redoc`.

## Ce que cette V1 ne fait pas encore

- provider anime séparé ;
- enrichissement cross-source ;
- pagination multi-pages automatisée côté upstream.

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

## Exemples curl

### Health

```bash
curl http://localhost:8017/health
```

### Recherche simple

```bash
curl "http://localhost:8017/search?q=one%20piece&kind=series&mode=all&limit=5"
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

### News globales

```bash
curl "http://localhost:8017/news/global?limit=10"
```

### News d'une série

```bash
curl "http://localhost:8017/news/series/One-piece-Edition-originale?limit=10"
```

### Avec Bearer token

```bash
curl -H "Authorization: Bearer MON_TOKEN" "http://localhost:8017/search?q=one%20piece"
```

## Notes de conception

- L'API repose sur le HTML public et le flux RSS de Manga News. C'est un usage privé ; ne t'en sers pas pour republier massivement leur contenu.
- Le cache persistant limite les appels et réduit le risque de casser ton automatisation sur une panne temporaire du site.
- Les parsers sont volontairement tolérants : beaucoup de logique est basée sur les libellés textuels visibles plutôt que sur des sélecteurs CSS trop fragiles.


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
