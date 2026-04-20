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
- docs OpenAPI natives de FastAPI sur `/docs` et `/redoc`
- endpoints de résumé stables pour l’automatisation (`/summary`, `/release-summary`, `/news-summary`) ;
- comparaison de deux fiches série ou de deux fiches volume ;
- projection locale de champs choisis via les endpoints `select`.

## Ce que cette V1 ne fait pas encore

- provider anime séparé ;
- enrichissement cross-source ;
- pagination multi-pages automatisée côté upstream.
- sélection générique par blocs métier complets (seuls les champs ciblés sont exposés pour l’instant).

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

## GitHub / GHCR

Fichiers ajoutés pour un dépôt GitHub propre et une publication GHCR automatique :

- `.github/workflows/ci.yml` : lance les tests sur push / pull request ;
- `.github/workflows/publish.yml` : build multi-arch `linux/amd64` + `linux/arm64` et push vers GHCR ;
- `.github/workflows/manifest.yml` : inspecte le manifest publié et stocke `manifest.json` en artifact ;
- `.dockerignore` : évite d'envoyer les fichiers inutiles au build Docker ;
- `.gitignore` : ignore l'environnement local, le cache et la base SQLite.

Image publiée par défaut : `ghcr.io/<owner>/<repo>` en minuscules.

Tags générés automatiquement par le workflow de publication :

- `latest` sur la branche par défaut ;
- tag de branche ;
- tag Git ;
- semver (`1.2.3`, `1.2`) si le tag Git suit `v1.2.3` ;
- tag SHA court.

### Secrets et permissions

Pour publier vers GHCR depuis GitHub Actions, aucun secret supplémentaire n'est nécessaire tant que le package est publié par le dépôt lui-même : le workflow utilise `GITHUB_TOKEN`.

Pour **pull une image privée depuis Portainer, Docker Compose ou une autre machine**, prévois en revanche un **PAT GitHub classic** avec au minimum `read:packages`.

### Déclenchement conseillé

- push sur `main` : publication continue ;
- tag `vX.Y.Z` : publication versionnée ;
- `workflow_dispatch` : exécution manuelle.


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

### Manifest GHCR

Après publication, le workflow `manifest.yml` peut inspecter l'image publiée et produire un `manifest.json` téléchargeable depuis les artifacts GitHub Actions. C'est utile pour vérifier qu'un manifest multi-arch a bien été généré.


## Endpoints d’automatisation ajoutés

### Résumé série minimal et stable

```bash
curl "http://localhost:8017/series/One-piece-Edition-originale/summary"
```

### Résumé des sorties série

```bash
curl "http://localhost:8017/series/One-piece-Edition-originale/release-summary"
```

### Résumé news série

```bash
curl "http://localhost:8017/series/One-piece-Edition-originale/news-summary?limit=20"
```

### Résumé volume minimal et stable

```bash
curl "http://localhost:8017/volume/One-Piece/vol-110/summary"
```

### Projection ciblée de champs

```bash
curl --get "http://localhost:8017/series/One-piece-Edition-originale/select" \
  --data-urlencode "fields=title,vf.volumes,next_release_date"
```

```bash
curl --get "http://localhost:8017/volume/One-Piece/vol-110/select" \
  --data-urlencode "fields=title,publication_date,isbn_ean"
```

### Comparer deux séries

```bash
curl --get "http://localhost:8017/compare/series" \
  --data-urlencode "left_slug=One-piece-Edition-originale" \
  --data-urlencode "right_slug=One-piece"
```

### Comparer deux volumes

```bash
curl --get "http://localhost:8017/compare/volume" \
  --data-urlencode "left_series_slug=One-Piece" \
  --data-urlencode "left_volume_slug=vol-109" \
  --data-urlencode "right_series_slug=One-Piece" \
  --data-urlencode "right_volume_slug=vol-110"
```

## Avis sur la sélection partielle

Oui, c’est utile. Pas pour économiser massivement le scraping upstream, mais pour rendre l’intégration bien plus propre côté client.

Exemple concret : si ton autre conteneur veut juste `vf.volumes`, un endpoint `summary` ou `select` évite d’avaler toute la fiche série complète. Le gain principal est donc :
- réponse plus petite ;
- parsing plus simple dans le client ;
- contrat JSON plus stable pour l’automatisation.

Le site source reste quand même chargé et parsé côté API privée. Donc ce n’est pas une optimisation miracle du scraping. C’est surtout une optimisation d’interface et de maintenabilité.
