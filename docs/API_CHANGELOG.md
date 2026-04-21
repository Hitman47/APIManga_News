# Changelog du contrat API

## Non versionné

### Ajout — recherche enrichie avec compteurs VF / VO de série
- `/search` et `/search/resolve` peuvent désormais exposer `vf` et `vo` sur les résultats de type `series`.
- Ces champs reprennent le nombre de tomes et le statut (`En cours`, `Terminé`, `En pause`, etc.) quand la fiche série Manga News les expose.
- Aucun changement de route ; extension additive du payload uniquement.

suit le **contrat consommateur** : routes, formes de réponses, champs exposés et documentation d'intégration. Il ne cherche pas à lister chaque refactor interne.

## 2026-04-21 — réalignement complet doc + ReDoc + OpenAPI

- Reprise complète de la documentation narrative pour la réaligner sur le code réellement présent dans le projet.
- Nettoyage de la grosse régression documentaire : suppression des références erronées à `/v1`, `lookup/volume`, routes admin et pagination commune inexistante.
- ReDoc enrichi : titres de section, résumés, descriptions détaillées, tags métier et exemples de réponses sur les routes publiques.
- Clarification du périmètre exact du contrat public et des éléments internes non encore exposés comme API publique.
- Ajout d'une validation documentaire qui signale désormais aussi les routes API documentées mais absentes du schéma OpenAPI.

## 2026-04-20 — enrichissement recherche et volume

- Les résultats de recherche et de résolution exposent `title_vo` et `translated_title` quand l'enrichissement de fiche détaillée réussit.
- Le contrat volume détaillé expose `number`, `number_int`, `edition_label`, `is_special` et `is_one_shot`.
- Le negative cache évite de refetch immédiatement une page cassée ou absente sur les routes cacheables.
- Les `UPSTREAM_PARSE_ERROR` peuvent inclure le chemin du dump HTML quand `DEBUG_CAPTURE_HTML_ON_ERROR=true`.

## 2026-04-20 — outillage de contrat

- Ajout d'exemples JSON validés dans `docs/examples/`.
- Ajout de `app/contract_validation.py`.
- Ajout de `scripts/validate_contract_and_docs.py`.
- Ajout de tests de cohérence doc/contrat.

## Note de compatibilité

Le contrat public actuel est **non versionné**.

Recommandation pour les consommateurs :
- ne jamais inventer `/v1` ;
- repartir de `/openapi.json` pour les routes ;
- utiliser ce changelog pour repérer les changements documentaires ou contractuels visibles.
