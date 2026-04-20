# Manga News Private API

API privée, légère et auto-hébergeable pour interroger Manga News, normaliser les données utiles, et les servir en JSON avec cache SQLite, ETag et authentification Bearer optionnelle.

## Fonctionnalités réellement disponibles

- recherche de séries et de volumes via `/search` ;
- résolution directe du meilleur résultat via `/search/resolve` ;
- fiches série via slug ou URL ;
- fiches volume via slug ou URL ;
- liens liés d'une série ;
- liste des éditions VF / VO d'une série ;
- news globales, news de série, news de volume ;
- planning manga VF / VO avec filtres locaux (éditeur, texte, dates, tri) ;
- cache SQLite persistant avec fallback sur cache périmé ;
- ETag / `If-None-Match` / `304 Not Modified` ;
- documentation OpenAPI native (`/docs`, `/redoc`) ;
- exemples JSON figés et validés dans `docs/examples/`.

## Ce que cette API ne fait pas

- pagination multi-pages automatique côté upstream ;
- watch métier exposé comme endpoint public ;
- provider multi-sources au-delà de Manga News.

## Variables d'environnement principales

Voir `.env.example`. Les plus importantes :

- `API_TOKEN` : si vide, l'API est ouverte ; sinon chaque requête doit envoyer `Authorization: Bearer <token>` ;
- `DB_PATH` : chemin du cache SQLite ;
- `CACHE_TTL_*` : TTL par type de ressource ;
- `SEARCH_SCORE_THRESHOLD` : seuil de matching ;
- `ENABLE_DOCS` : active ou non `/docs` et `/redoc`.

## Démarrage local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

API disponible ensuite sur `http://localhost:8000` en local direct, ou `http://localhost:8017` via Docker Compose.

## Docker Compose

```bash
docker compose up -d --build
```

## Premiers appels utiles

### Health

```bash
curl http://localhost:8017/health
```

### Recherche série

```bash
curl "http://localhost:8017/search?q=one%20piece&kind=series&mode=all&limit=5"
```

### Résolution directe

```bash
curl "http://localhost:8017/search/resolve?q=one%20piece%20tome%2091&kind=volume&limit=10"
```

### Fiche série

```bash
curl "http://localhost:8017/series/One-piece-Edition-originale"
```

### Fiche volume

```bash
curl "http://localhost:8017/volume/One-Piece/vol-91"
```

### Planning manga VF

```bash
curl --get "http://localhost:8017/planning" \
  --data-urlencode "section=manga-vf" \
  --data-urlencode "year=2026" \
  --data-urlencode "month=4" \
  --data-urlencode "publisher=Glénat"
```

### Avec Bearer token

```bash
curl -H "Authorization: Bearer MON_TOKEN" "http://localhost:8017/search?q=one%20piece"
```

## Contrat HTTP

La plupart des endpoints renvoient une enveloppe commune :

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

Les réponses détaillées série / volume contiennent `title_vo` et `translated_title`.
Les résultats de recherche et de résolution exposent aussi ces champs quand ils sont disponibles.

## Caching côté client

Les réponses incluent :

- `ETag: "<fingerprint>"`
- `X-Data-Fingerprint: <fingerprint>`

Tu peux renvoyer :

```http
If-None-Match: "<fingerprint>"
```

Si rien n'a changé, l'API répond `304 Not Modified`.

## Documentation fournie

- `docs/API_INTEGRATION.md` : guide d'intégration pour développeur ou IA ;
- `docs/API_CHANGELOG.md` : changelog du contrat ;
- `docs/examples/` : exemples JSON validés ;
- `scripts/validate_contract_and_docs.py` : vérification locale doc + contrat ;
- `/openapi.json` : schéma généré automatiquement.

## Vérification locale

```bash
python scripts/validate_contract_and_docs.py
pytest
```

## Notes de conception

- L'API repose sur le HTML public et le flux RSS de Manga News. Usage privé recommandé.
- Le cache réduit les appels réseau et protège les automatisations contre les pannes temporaires.
- Les parsers sont volontairement basés en priorité sur les libellés textuels visibles, pour rester plus robustes que des sélecteurs CSS très fragiles.
