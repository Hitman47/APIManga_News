# Exemples JSON figés

Ce dossier contient des **payloads figés** qui illustrent le contrat public de l'API.

Objectifs :
- aider un développeur à démarrer sans lancer immédiatement l'API ;
- aider une IA à comprendre la forme réelle des réponses ;
- servir de référence rapide quand on écrit un client ;
- servir de garde-fou documentaire dans la CI.

## Fichiers disponibles

- [`health_ok.json`](health_ok.json) : réponse minimale de `GET /health`
- [`search_series_one_piece.json`](search_series_one_piece.json) : exemple de `GET /search`
- [`search_resolve_series_one_piece.json`](search_resolve_series_one_piece.json) : exemple de `GET /search/resolve`
- [`series_one_piece.json`](series_one_piece.json) : exemple de fiche série
- [`series_related_one_piece.json`](series_related_one_piece.json) : exemple de contenus liés à une série
- [`series_editions_one_piece_all.json`](series_editions_one_piece_all.json) : exemple de listes VF / VO
- [`volume_one_piece_110.json`](volume_one_piece_110.json) : exemple de fiche volume
- [`news_global_one_piece_sample.json`](news_global_one_piece_sample.json) : exemple de news globales
- [`planning_manga_vf_april_2026.json`](planning_manga_vf_april_2026.json) : exemple de planning filtré
- [`error_resource_not_found.json`](error_resource_not_found.json) : exemple d'erreur 404 logique
- [`error_upstream_parse.json`](error_upstream_parse.json) : exemple d'erreur 502 logique

## Ce que ces fichiers sont, et ne sont pas

Ils sont :
- des **exemples de forme** ;
- des aides à l'intégration ;
- des artefacts validés par la CI.

Ils ne sont pas :
- une garantie que les valeurs métiers exactes seront toujours identiques ;
- une copie exhaustive de tous les cas limites ;
- un remplacement de `/openapi.json`.

## Ordre recommandé pour démarrer

1. Lire [`../README.md`](../../README.md)
2. Lire [`../API_INTEGRATION.md`](../API_INTEGRATION.md)
3. Regarder 2 ou 3 payloads de ce dossier
4. Lire `/openapi.json`
5. Commencer l'intégration réelle
