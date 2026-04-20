# OpenAPI et usage par une IA

Cette API est utilisable par un humain, mais elle est aussi pensée pour être consommée proprement par une autre IA. Ce document explique comment éviter les erreurs classiques.

## 1. Sources de vérité à lire dans le bon ordre

Ordre recommandé :
1. `README.md`
2. `docs/API_INTEGRATION.md`
3. `/openapi.json`
4. `docs/examples/`
5. appels réels

Règle simple :
- si la doc narrative et l'OpenAPI semblent diverger, **crois l'OpenAPI et le code**, pas un souvenir de doc.

## 2. Ce qu'une IA ne doit pas inventer

Une IA consommatrice ne doit pas inventer :
- de préfixe `/v1` ;
- des routes admin ;
- une pagination normalisée absente ;
- des champs non décrits dans les modèles ;
- une recherche dédiée par `title_vo=` ou `translated_title=` ;
- une séparation publique `API_TOKEN` / `ADMIN_TOKEN` qui n'existe pas côté routes.

## 3. Ce qu'une IA peut supposer sans trop de risque

Elle peut supposer que :
- les routes publiques décrites dans `/openapi.json` existent ;
- la plupart des réponses métier utilisent une enveloppe stable ;
- `title_vo` et `translated_title` peuvent apparaître dans les recherches **et** les fiches détaillées ;
- les champs peuvent être absents ou `null` ;
- `ETag` et `X-Data-Fingerprint` sont présents sur les réponses enveloppées avec fingerprint.

## 4. Mode opératoire conseillé pour une IA

### Cas A — trouver une série
1. `GET /search/resolve?q=<titre>&kind=series`
2. lire `data.best.slug`
3. `GET /series/{slug}`

### Cas B — trouver un volume
1. `GET /search/resolve?q=<titre>&kind=volume`
2. lire `series_slug` et `volume_slug`
3. `GET /volume/{series_slug}/{volume_slug}`

### Cas C — interface légère
- utiliser `fields=` ou `blocks=` sur les routes détail ;
- ne demander le payload complet qu'en second temps.

## 5. Exemples de prompts à donner à une autre IA

### Exemple 1 — consommer l'API sans halluciner

> Tu consommes une API Manga News privée. Ne suppose jamais de `/v1`. Commence par lire `/openapi.json`, puis choisis parmi les routes réellement exposées. Tous les champs métier peuvent être absents ou null. Pour trouver une série ou un volume, privilégie `/search/resolve` avant `/search`.

### Exemple 2 — produire une UI compacte

> Quand tu appelles `/series/{slug}` ou `/volume/{...}`, utilise `fields=` ou `blocks=` pour limiter le payload à ce qui est affiché. Réutilise l'ETag si disponible pour éviter les requêtes inutiles.

### Exemple 3 — traiter les erreurs proprement

> Si tu reçois `RESOURCE_NOT_FOUND`, traite la ressource comme absente. Si tu reçois `UPSTREAM_PARSE_ERROR`, considère que le HTML a peut-être changé. Si la réponse métier a `partial=true`, ne la présente pas comme fraîche.

## 6. Swagger / ReDoc / OpenAPI

### Swagger UI
- `/docs`

### ReDoc
- `/redoc`

### Schéma brut
- `/openapi.json`

Utilisation conseillée :
- Swagger pour tester vite à la main ;
- OpenAPI brut pour générer un client ou guider un agent ;
- `docs/examples/` pour montrer des payloads réalistes sans devoir lancer l'API.

## 7. Exemples JSON recommandés pour une IA

Les plus utiles sont :
- [`examples/search_response_one_piece.json`](examples/search_response_one_piece.json)
- [`examples/resolve_response_one_piece.json`](examples/resolve_response_one_piece.json)
- [`examples/series_one_piece.json`](examples/series_one_piece.json)
- [`examples/volume_one_piece_110.json`](examples/volume_one_piece_110.json)
- [`examples/planning_example.json`](examples/planning_example.json)
- [`examples/error_upstream_parse.json`](examples/error_upstream_parse.json)

## 8. Validation locale du contrat documentaire

Commande :

```bash
python scripts/validate_contract_and_docs.py
```

Cette validation vérifie :
- que l'OpenAPI se génère ;
- que les routes clés existent ;
- que les liens Markdown locaux sont valides ;
- que les exemples JSON canoniques correspondent aux modèles Pydantic.
