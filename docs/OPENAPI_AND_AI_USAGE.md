# OpenAPI, Swagger, ReDoc and AI Usage

## Endpoints de documentation

- `/openapi.json`
- `/docs`
- `/redoc`

## Ce que montre correctement l'OpenAPI actuel

- les routes réellement exposées ;
- les schémas Pydantic du contrat ;
- les summaries et descriptions principales ;
- les exemples de réponses sur les routes clés.

## Ce que l'OpenAPI ne doit pas te faire inventer

La doc générée et ce guide insistent sur quatre points :
- pas de `/v1` ;
- pas de routes admin HTTP ;
- pas de `lookup/volume` ;
- pas de pagination top-level commune aux endpoints de liste.

## Mode d'emploi pour une autre IA

Règles de consommation sûres :
1. Commencer par lire `/openapi.json`.
2. Utiliser seulement les routes présentes dans `paths`.
3. Ne pas supposer que tous les champs sont toujours présents.
4. Utiliser `/search/resolve` pour obtenir un meilleur candidat.
5. Utiliser `score` comme indice de similarité, pas comme vérité absolue.
6. Réutiliser `ETag` et `If-None-Match`.

### Prompt système conseillé pour un agent consommateur

> Tu consommes une API Manga-News privée. Lis d'abord `/openapi.json`, puis n'utilise que les routes réellement présentes. N'invente pas de `/v1`, pas de routes admin, pas de `lookup/volume`. Pour trouver une ressource, privilégie `/search/resolve`. Tous les champs métier peuvent être absents ou null selon la page source.

## ReDoc

ReDoc est particulièrement utile pour :
- parcourir les schémas ;
- voir les champs `vf`, `vo`, `title_vo`, `translated_title` ;
- vérifier les paramètres `blocks`, `fields`, `include_raw_sections` ;
- relire les exemples de réponses sans ouvrir la doc markdown.
