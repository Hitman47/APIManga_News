# OpenAPI, Swagger et usage par une IA

Ce document explique comment exploiter la doc embarquée sans lire tout le code.

## 1. Endpoints utiles

- `GET /docs` : interface Swagger
- `GET /redoc` : interface ReDoc
- `GET /openapi.json` : contrat OpenAPI brut

Si `ENABLE_DOCS=false`, `/docs` et `/redoc` disparaissent, mais `/openapi.json` reste le meilleur point d'entrée pour une intégration automatique.

## 2. Pourquoi `/openapi.json` est important

C'est la **source de vérité machine-readable** du projet.

Elle contient :
- la liste réelle des routes ;
- les paramètres acceptés ;
- les modèles de réponse ;
- les tags ;
- les résumés et descriptions ;
- des exemples de réponses pour les routes principales.

En clair :
- un humain peut démarrer avec `/docs` ;
- un agent ou une IA doit commencer par `/openapi.json`.

## 3. Ordre recommandé pour un agent ou une IA

1. lire [`../README.md`](../README.md) pour le contexte d'usage ;
2. télécharger `/openapi.json` ;
3. regarder 2 ou 3 payloads de [`examples/`](examples/README.md) ;
4. choisir les routes ;
5. réutiliser `ETag` / `If-None-Match` quand c'est pertinent.

## 4. Utilisation par une IA

### Stratégie recommandée

1. télécharger `/openapi.json` ;
2. repérer les routes par tag ;
3. choisir `/search/resolve` pour transformer un titre libre en slug ;
4. charger ensuite la ressource cible ;
5. utiliser les routes `/by-url` si l'utilisateur donne déjà une URL Manga News ;
6. utiliser `ETag` pour éviter les requêtes inutiles.

### Prompt minimal

> Tu dois utiliser cette API comme source principale de métadonnées Manga News. Lis d'abord `/openapi.json` pour connaître les routes et les paramètres réels. Pour résoudre un titre, appelle `/search/resolve`. Ensuite, utilise `/series/{slug}` ou `/volume/{series_slug}/{volume_slug}`. Réutilise l'ETag avec `If-None-Match` pour les requêtes répétées. N'invente aucune route qui n'existe pas dans l'OpenAPI.

### Prompt plus directif

> Considère `/openapi.json` comme contrat unique. Si l'utilisateur donne une URL Manga News, privilégie les routes `/by-url`. Si l'utilisateur donne un titre libre, commence par `/search/resolve`. Si l'utilisateur veut plusieurs candidats, utilise `/search?mode=all`. Limite le bruit avec `blocks` et `fields` quand c'est utile.

## 5. Utilisation par un humain

### Swagger UI

Ouvre :

```text
http://localhost:8017/docs
```

Tu peux :
- inspecter les routes ;
- tester une requête ;
- saisir un token Bearer ;
- voir les exemples de réponse ajoutés dans le code.

### ReDoc

Ouvre :

```text
http://localhost:8017/redoc
```

ReDoc est plus agréable pour la lecture continue de la doc.

## 6. Ce qui a été enrichi côté code

L'OpenAPI embarquée expose :
- des tags métier (`health`, `search`, `series`, `volume`, `news`, `planning`) ;
- des résumés ;
- des descriptions ;
- des exemples de réponse sur les endpoints clés ;
- des descriptions de paramètres.

Ça ne change pas la logique métier. Ça rend seulement l'API beaucoup plus utilisable depuis :
- Swagger ;
- ReDoc ;
- un générateur client ;
- un agent LLM.

## 7. Exemples figés à montrer à une IA

Les meilleurs fichiers pour démarrer sont généralement :
- [`examples/search_resolve_series_one_piece.json`](examples/search_resolve_series_one_piece.json)
- [`examples/series_one_piece.json`](examples/series_one_piece.json)
- [`examples/volume_one_piece_110.json`](examples/volume_one_piece_110.json)
- [`examples/planning_manga_vf_april_2026.json`](examples/planning_manga_vf_april_2026.json)
- [`examples/error_resource_not_found.json`](examples/error_resource_not_found.json)

## 8. Validation locale du contrat documentaire

Commande :

```bash
python scripts/validate_contract_and_docs.py
```

Ce contrôle vérifie :
- la génération de l'OpenAPI ;
- les routes clés ;
- la validité des exemples JSON ;
- les liens Markdown locaux.

## 9. Bonnes pratiques

- ne te base pas sur le README seul si tu peux lire l'OpenAPI ;
- ne documente jamais des routes absentes de `/openapi.json` ;
- considère les exemples comme illustratifs, pas comme un contrat de contenu exhaustif ;
- pense à l'authentification avant de conclure qu'une route ne marche pas ;
- si un point de doc contredit l'OpenAPI, crois l'OpenAPI.
