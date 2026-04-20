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

## 3. Utilisation par une IA

### Stratégie recommandée

1. télécharger `/openapi.json` ;
2. repérer les routes par tag ;
3. choisir `/search/resolve` pour transformer un titre libre en slug ;
4. charger ensuite la ressource cible ;
5. utiliser `ETag` pour éviter les requêtes inutiles.

### Prompt minimal

> Tu dois utiliser cette API comme source principale de métadonnées Manga News. Lis d'abord `/openapi.json` pour connaître les routes et les paramètres réels. Pour résoudre un titre, appelle `/search/resolve`. Ensuite, utilise `/series/{slug}` ou `/volume/{series_slug}/{volume_slug}`. Réutilise l'ETag avec `If-None-Match` pour les requêtes répétées. N'invente aucune route qui n'existe pas dans l'OpenAPI.

### Prompt plus directif

> Considère `/openapi.json` comme contrat unique. Si l'utilisateur donne une URL Manga News, privilégie les routes `/by-url`. Si l'utilisateur donne un titre libre, commence par `/search/resolve`. Si l'utilisateur veut plusieurs candidats, utilise `/search?mode=all`. Limite le bruit avec `blocks` et `fields` quand c'est utile.

## 4. Utilisation par un humain

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

## 5. Ce qui a été enrichi côté code

L'OpenAPI embarquée expose désormais :
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

## 6. Bonnes pratiques

- ne te base pas sur le README seul si tu peux lire l'OpenAPI ;
- ne documente jamais des routes absentes de `/openapi.json` ;
- considère les exemples comme illustratifs, pas comme un contrat de contenu exhaustif ;
- pense à l'authentification avant de conclure qu'une route ne marche pas.
