# Manga News Private API

API privée, légère, pensée pour un usage personnel ou auto-hébergé, afin d'interroger Manga News avec cache SQLite, authentification Bearer optionnelle, schéma de réponse stable, ETag, et docs OpenAPI natives.

## Ce que fait la version actuelle

- recherche de séries et volumes ;
- résolution directe d'un titre vers le meilleur slug exploitable ;
- récupération d'une fiche série ;
- récupération d'une fiche volume ;
- récupération des relations d'une série ;
- récupération des éditions VF/VO d'une série ;
- récupération des news globales via RSS ;
- récupération des news d'une série ;
- récupération des news d'un volume ;
- récupération du planning manga VF et manga VO ;
- projections partielles sur les endpoints série/volume via `blocks` et `fields` ;
- cache SQLite persistant avec fallback sur cache périmé si l'upstream casse temporairement ;
- ETag + `X-Data-Fingerprint` + support `If-None-Match` ;
- docs OpenAPI natives de FastAPI sur `/docs` et `/redoc` ;
- corpus de fixtures HTML et golden tests pour verrouiller les parseurs.

## Ce que cette version ne fait pas encore

- provider anime séparé ;
- enrichissement cross-source ;
- pagination multi-pages automatisée côté upstream ;
- endpoints d'admin du cache.

## Contrat de réponse

Toutes les réponses enveloppées exposent maintenant :

- `schema_version`
- `ok`
- `found`
- `source`
- `source_url`
- `cached`
- `fetched_at`
- `cache_expires_at`
- `partial`
- `warnings`
- `fingerprint`
- `data`

Le champ `fingerprint` est aussi renvoyé dans l'en-tête `X-Data-Fingerprint` et sert de base à l'`ETag` HTTP.

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

- `http://localhost:8017/docs`
- `http://localhost:8017/redoc`

## Exemples curl

### Health

```bash
curl http://localhost:8017/health
```

### Recherche simple

```bash
curl "http://localhost:8017/search?q=one%20piece&kind=series&mode=all&limit=5"
```

### Résolution directe du meilleur résultat

```bash
curl "http://localhost:8017/search/resolve?q=one%20piece&kind=series"
```

### Fiche série via slug

```bash
curl "http://localhost:8017/series/One-piece-Edition-originale"
```

### Fiche série avec projection partielle

```bash
curl --get "http://localhost:8017/series/One-piece-Edition-originale" \
  --data-urlencode "fields=title,vf.volumes,next_release_date"
```

### Fiche volume via slug

```bash
curl "http://localhost:8017/volume/One-Piece/vol-110"
```

### News globales

```bash
curl "http://localhost:8017/news/global?limit=10"
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

### Requête conditionnelle avec ETag

Premier appel :

```bash
curl -i "http://localhost:8017/series/One-piece-Edition-originale"
```

Réutilisation de l'ETag retourné :

```bash
curl -i \
  -H 'If-None-Match: "<fingerprint>"' \
  "http://localhost:8017/series/One-piece-Edition-originale"
```

Si rien n'a changé, l'API renvoie `304 Not Modified`.

### Avec Bearer token

```bash
curl -H "Authorization: Bearer MON_TOKEN" "http://localhost:8017/search?q=one%20piece"
```

## GitHub / GHCR

Fichiers présents pour un dépôt GitHub propre et une publication GHCR automatique :

- `.github/workflows/ci.yml` : lance les tests sur push / pull request ;
- `.github/workflows/publish-ghcr.yml` : build multi-arch et push vers GHCR ;
- `.github/workflows/manifest.yml` : inspecte le manifest publié et stocke `manifest.json` en artifact ;
- `.dockerignore` : évite d'envoyer les fichiers inutiles au build Docker ;
- `.gitignore` : ignore l'environnement local, le cache et la base SQLite.

## Notes de conception

- L'API repose sur le HTML public et le flux RSS de Manga News. C'est un usage privé ; ne t'en sers pas pour republier massivement leur contenu.
- Le cache persistant limite les appels et réduit le risque de casser ton automatisation sur une panne temporaire du site.
- Les parseurs sont volontairement tolérants : beaucoup de logique repose sur les libellés textuels visibles plutôt que sur des sélecteurs CSS trop fragiles.
- Les fixtures HTML dans `tests/fixtures/html` et les golden outputs dans `tests/fixtures/golden` servent de garde-fou contre les régressions de parsing.
