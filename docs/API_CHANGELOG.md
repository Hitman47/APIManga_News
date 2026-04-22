## 2026-04-22 — optimisation structurelle de la recherche et du cache

- Les pages source de `/search` sont maintenant cachées indépendamment du rendu final, ce qui évite de relire l'upstream quand seul `mode` ou `limit` change.
- Les enrichissements de recherche sont mutualisés : une même fiche série ou volume n'est plus relue plusieurs fois dans la même requête.
- Les fetchs concurrents identiques partagent désormais une même exécution locale au lieu de taper plusieurs fois l'upstream en parallèle.
- Le cache SQLite passe sur une connexion réutilisée avec `journal_mode=WAL` et `busy_timeout`, ce qui réduit le coût I/O et la contention locale.
- `/series/{slug}/editions` réutilise maintenant la fiche série déjà cachée pour le titre, et met en cache séparément les blocs VF / VO.

## 2026-04-21 — robustesse vf/vo, enrichissement volume et cache

- Lecture prioritaire des compteurs `vf` / `vo` dans le bloc HTML `#numberblock` des fiches série Manga-News.
- Enrichissement des résultats de recherche `series` avec `vf` / `vo`.
- Enrichissement des résultats de recherche `volume` avec les champs volume normalisés, puis avec `vf` / `vo` de la série parente.
- Enrichissement des fiches volume avec `vf` / `vo` de la série parente.
- Version interne des clés de cache métier pour éviter la réutilisation silencieuse d'anciens payloads incompatibles après mise à jour.

# Changelog du contrat API

Ce changelog suit le **contrat consommateur** : routes, formes de réponses, champs exposés, doc d'intégration. Il ne cherche pas à lister chaque refactor interne.

## 2026-04-20 — passe de documentation complète

- Reprise complète de la documentation pour la réaligner sur le code réellement présent dans le projet.
- Clarification explicite qu'il n'existe **pas** de préfixe `/v1`.
- Clarification des routes réellement publiques et de leurs limites.
- Clarification des variables réellement actives vs. présentes mais non branchées au runtime public.
- Documentation détaillée de `title_vo` / `translated_title` sur les fiches détaillées et dans les recherches enrichies.
- Documentation détaillée de la normalisation volume : `number`, `number_int`, `edition_label`, `is_special`, `is_one_shot`.
- Nettoyage des exemples JSON pour supprimer les artefacts de doc qui n'appartenaient pas au contrat réel.

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


- 2026-04-21: invalidation automatique des anciennes entrées de cache incompatibles pour `series`, `volume`, `search` et `search/resolve`, afin d'éviter de conserver des payloads sans `vf` / `vo` après une mise à jour du parseur.

## 2026-04-22 - Config de tuning restaurée

- Correction de la régression : `VOLUME_DEFAULT_INCLUDE_PARENT_EDITIONS` repasse à `false` par défaut pour que `/volume` ne refetch pas silencieusement la fiche série parente. L'hydratation `vf` / `vo` reste disponible via `include_parent_editions=true` ou via la variable d'environnement.
- Réintroduction de `SQLITE_BUSY_TIMEOUT_MS`, `CACHE_MEMORY_ENTRIES`, `SEARCH_DEFAULT_ENRICH`, `SEARCH_DEFAULT_INCLUDE_EDITIONS` et `VOLUME_DEFAULT_INCLUDE_PARENT_EDITIONS` dans `Settings` et `.env.example`.
- Ajout d'un vrai cache mémoire L1 paramétrable au-dessus de SQLite.
- Compatibilité conservée pour les anciens noms d'environnement `SEARCH_FETCH_CONCURRENCY` et `SEARCH_ENRICH_CONCURRENCY`.
