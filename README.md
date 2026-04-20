# Manga News Private API

API privée, légère, prévue pour un usage personnel ou auto-hébergé, afin d'interroger Manga News avec un cache SQLite persistant, une authentification Bearer optionnelle, des logs structurés, et des endpoints pensés pour l'automatisation.

## Ce que fait cette version

- recherche de séries et volumes ;
- récupération d'une fiche série ;
- récupération d'une fiche volume ;
- récupération des news globales via RSS ;
- récupération des news d'une série ;
- récupération des news d'un volume ;
- récupération du planning manga VF et manga VO ;
- endpoint `planning/watch` avec fingerprint et diff facultatif via snapshot serveur ;
- stats et invalidation du cache via endpoints d'admin ;
- cache SQLite persistant avec fallback sur cache périmé si l'upstream casse temporairement ;
- enveloppes JSON plus explicites : `schema_version`, `fingerprint`, `cache_state`, `parse_status`, `missing_fields` ;
- erreurs structurées : `not_found`, `parse_error`, `upstream_error` ;
- docs OpenAPI natives de FastAPI sur `/docs` et `/redoc`.

## Ce que cette version ne fait pas encore

- provider anime séparé ;
- enrichissement cross-source ;
- pagination multi-pages automatisée côté upstream ;
- diff historique multi-snapshots : pour l'instant, `planning/watch` compare l'état courant au dernier snapshot du même `watch_id`.

## Variables d'environnement principales

Consulte `.env.example`.

Les plus importantes :

- `API_TOKEN` : si vide, pas d'auth ; si défini, il faut envoyer `Authorization: Bearer <token>` ;
- `DB_PATH` : chemin du cache SQLite ;
- `CACHE_TTL_*` : TTL par type de ressource ;
- `SEARCH_SCORE_THRESHOLD` : seuil minimal de matching ;
- `ENABLE_DOCS` : active `/docs` et `/redoc` ;
- `LOG_FORMAT` : `text` ou `json`.

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

## GitHub / GHCR

Fichiers ajoutés pour un dépôt GitHub propre et une publication GHCR automatique :

- `.github/workflows/ci.yml` : lance les tests sur push / pull request ;
- `.github/workflows/publish-ghcr.yml` : build multi-arch `linux/amd64` + `linux/arm64` et push vers GHCR ;
- `.github/workflows/manifest.yml` : inspecte le manifest publié et stocke `manifest.json` en artifact ;
- `.dockerignore` : évite d'envoyer les fichiers inutiles au build Docker ;
- `.gitignore` : ignore l'environnement local, le cache et la base SQLite.

Image publiée par défaut : `ghcr.io/<owner>/<repo>` en minuscules.

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

### Fiche volume via slug

```bash
curl "http://localhost:8017/volume/One-Piece/vol-110"
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

### Watch du planning par éditeur

```bash
curl --get "http://localhost:8017/planning/watch" \
  --data-urlencode "section=manga-vf" \
  --data-urlencode "publisher=Kana" \
  --data-urlencode "watch_id=kana-watch" \
  --data-urlencode "preview_limit=5"
```

### Stats du cache

```bash
curl "http://localhost:8017/admin/cache/stats"
```

### Invalidation du cache planning

```bash
curl -X POST "http://localhost:8017/admin/cache/invalidate?namespace=planning"
```

### Avec Bearer token

```bash
curl -H "Authorization: Bearer MON_TOKEN" "http://localhost:8017/search?q=one%20piece"
```

## Contrat de réponse

### Enveloppe standard

```json
{
  "schema_version": "1.1",
  "ok": true,
  "found": true,
  "source": "manga_news",
  "source_url": "https://www.manga-news.com/...",
  "cached": true,
  "cache_state": "fresh_hit",
  "fetched_at": "2026-04-20T12:00:00+00:00",
  "cache_expires_at": "2026-04-20T18:00:00+00:00",
  "partial": false,
  "parse_status": "complete",
  "missing_fields": [],
  "fingerprint": "...",
  "warnings": [],
  "data": {}
}
```

### Erreur structurée

```json
{
  "schema_version": "1.1",
  "ok": false,
  "error_code": "parse_error",
  "detail": "date_from must be a valid date.",
  "source": "manga_news"
}
```

## Notes de conception

- L'API repose sur le HTML public et le flux RSS de Manga News. C'est un usage privé ; ne t'en sers pas pour republier massivement leur contenu.
- Le cache persistant limite les appels et réduit le risque de casser ton automatisation sur une panne temporaire du site.
- Les parsers sont volontairement tolérants : beaucoup de logique est basée sur les libellés textuels visibles plutôt que sur des sélecteurs CSS trop fragiles.
- `partial=true` signifie qu'un cache périmé a pu être utilisé ou que des champs importants manquent ; un champ facultatif simplement absent n'entraîne pas forcément un `partial`.
- `planning/watch` est utile pour des cron jobs, n8n ou un autre conteneur ; avec un `watch_id`, l'API garde un snapshot courant et calcule les ajouts/suppressions au prochain appel.
