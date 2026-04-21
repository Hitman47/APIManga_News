# OpenAPI, Swagger, ReDoc et usage par une IA

Ce document explique comment utiliser correctement la doc générée et comment guider une autre IA pour qu'elle consomme l'API sans halluciner de routes ou de champs.

## 1. Sources de vérité dans le bon ordre

Ordre recommandé :
1. `README.md`
2. `docs/API_INTEGRATION.md`
3. `/openapi.json`
4. `/docs` ou `/redoc`
5. `docs/examples/`
6. appels réels

Règle simple : si la prose et l'OpenAPI semblent diverger, crois d'abord l'OpenAPI et le code.

## 2. Ce qu'une IA ne doit pas inventer

Une IA consommatrice ne doit pas inventer :
- de préfixe `/v1` ;
- des routes admin ;
- un endpoint `lookup/volume` ;
- une pagination normalisée absente ;
- des filtres dédiés `title_vo=` ou `translated_title=` ;
- des headers publics qui n'existent pas vraiment.

## 3. Ce qu'une IA peut supposer avec un risque faible

Elle peut supposer que :
- les routes présentes dans `/openapi.json` existent ;
- la plupart des réponses métier utilisent une enveloppe commune ;
- `title_vo` et `translated_title` peuvent apparaître dans les recherches **et** dans les fiches détaillées ;
- les champs métier peuvent être absents ou `null` ;
- `ETag` et `X-Data-Fingerprint` sont disponibles sur les réponses enveloppées dotées d'un fingerprint.

## 4. Swagger / ReDoc / OpenAPI

### Swagger UI
- `/docs`

Utile pour :
- tester rapidement à la main ;
- visualiser les paramètres ;
- copier une requête type.

### ReDoc
- `/redoc`

Utile pour :
- lire le contrat plus confortablement ;
- parcourir les schémas ;
- comprendre l'intention de chaque route.

### Schéma brut
- `/openapi.json`

Utile pour :
- générer un client ;
- piloter un agent ;
- comparer la doc au code réel.

## 5. Mode opératoire conseillé pour une autre IA

### Cas A — trouver une série
1. `GET /search/resolve?q=<titre>&kind=series`
2. lire `data.best.slug`
3. `GET /series/{slug}`

### Cas B — trouver un volume
1. `GET /search/resolve?q=<titre>&kind=volume`
2. lire `data.best.series_slug` et `data.best.volume_slug`
3. `GET /volume/{series_slug}/{volume_slug}`

### Cas C — interface légère
- utiliser `blocks=` et `fields=` sur les routes détail ;
- ne charger le payload complet qu'en second temps.

## 6. Prompts utiles à donner à une autre IA

### Prompt 1 — consommer sans halluciner

> Tu consommes une API Manga News privée. Ne suppose jamais de `/v1`. Commence par lire `/openapi.json`, puis utilise uniquement les routes réellement exposées. Tous les champs métier peuvent être absents ou `null`. Pour trouver une série ou un volume, privilégie `/search/resolve` avant `/search`.

### Prompt 2 — produire une UI compacte

> Quand tu appelles `/series/{slug}` ou `/volume/{...}`, utilise `fields=` ou `blocks=` pour limiter le payload à ce qui est affiché. Réutilise l'ETag si disponible pour éviter les requêtes inutiles.

### Prompt 3 — gérer les erreurs proprement

> Si tu reçois `RESOURCE_NOT_FOUND`, traite la ressource comme absente. Si tu reçois `UPSTREAM_PARSE_ERROR`, considère qu'un changement de HTML Manga News est probable. Si `partial=true`, ne présente pas la réponse comme fraîche.

## 7. Place des exemples JSON

Les exemples du dossier [`docs/examples/`](examples/README.md) ne remplacent pas `/openapi.json`, mais ils servent à :
- montrer une forme de réponse réaliste ;
- bootstrapper un prompt d'IA ;
- écrire une UI ou des tests d'intégration plus vite.

Exemples particulièrement utiles :
- [`examples/search_response_one_piece.json`](examples/search_response_one_piece.json)
- [`examples/resolve_response_one_piece.json`](examples/resolve_response_one_piece.json)
- [`examples/series_one_piece.json`](examples/series_one_piece.json)
- [`examples/volume_one_piece_91.json`](examples/volume_one_piece_91.json)
- [`examples/planning_example.json`](examples/planning_example.json)
- [`examples/error_upstream_parse.json`](examples/error_upstream_parse.json)

## 8. Validation locale du contrat documentaire

```bash
python scripts/validate_contract_and_docs.py
```

Cette validation vérifie actuellement :
- que l'OpenAPI se génère ;
- que les routes clés existent ;
- que les liens Markdown locaux sont valides ;
- que les exemples JSON canoniques correspondent aux modèles ;
- que les docs ne référencent pas des routes API inexistantes.
