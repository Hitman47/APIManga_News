## 2026-04-22 — optimisation phase 4, cache HTML brut et méta série légère

- Les pages HTML série / volume sont maintenant mises en cache séparément du payload JSON final, ce qui permet de réutiliser un même téléchargement entre plusieurs parseurs sans nouveau fetch réseau.
- Ajout d'un cache léger `series-search-meta` pour les chemins qui ont seulement besoin de `title`, `title_vo`, `translated_title`, `vf` et `vo`.
- `/search`, `/search/resolve`, `/volume?...include_parent_editions=true` et `/series/{slug}/editions` réutilisent ce chemin léger au lieu de dépendre systématiquement du parseur série complet.
- Conséquence importante : un `/search` qui hydrate les compteurs `vf` / `vo` peut maintenant être suivi d'un `/series/{slug}` sans refetch réseau supplémentaire de la même page série tant que le HTML brut est encore chaud.

## 2026-04-22 — optimisation phase 2, cache source de recherche et éditions réutilisables

- Les pages sources de `/search` sont désormais mises en cache séparément des réponses finales. Changer `mode`, `limit` ou `enrich` ne refetch donc plus automatiquement les pages de recherche Manga-News si les candidats bruts sont déjà chauds.
- `/series/{slug}/editions` réutilise maintenant la fiche série cachée et met en cache séparément les blocs `vf` et `vo`, ce qui évite de relire inutilement les mêmes pages entre `edition=vf`, `edition=vo` et `edition=all`.
- Les chargements d'éditions `vf` et `vo` peuvent maintenant être exécutés en parallèle lors d'un cache froid.
- Ajout de logs `search_source_perf` et `series_editions_perf` pour distinguer le coût des pages sources du coût de l'enrichissement applicatif.

## 2026-04-22 — correction de régression sur les compteurs VF/VO en recherche

- `/search` et `/search/resolve` conservent à nouveau par défaut les compteurs `vf` / `vo`, même quand `enrich=false`.
- Nouveau paramètre `include_editions` sur `/search` et `/search/resolve` : `true` par défaut pour préserver les compteurs, `false` pour couper aussi cette hydratation et viser la latence minimale.
- `enrich=true` redevient strictement l’opt-in pour les titres alternatifs (`title_vo`, `translated_title`) et la normalisation volume, sans forcer les intégrateurs à perdre les compteurs d’éditions.

## 2026-04-22 — optimisation phase 1, search plus léger et volume opt-in

- `/search` et `/search/resolve` restent désormais légers par défaut ; l'enrichissement détaillé devient opt-in via `enrich=true`.
- Les enrichissements de recherche sont dédupliqués par `series_slug` et `volume_slug`, puis exécutés avec concurrence bornée.
- Les fetchs concurrents pour une même clé de cache sont désormais mutualisés via single-flight, ce qui évite les rafales identiques sous charge.
- Le cache SQLite passe en WAL avec `busy_timeout`, conserve une connexion persistante, et ajoute un cache mémoire L1.
- Les fiches volume ne relisent plus automatiquement la série parente ; `vf` / `vo` deviennent opt-in via `include_parent_editions=true` ou une projection explicite.
- Le runtime branche enfin `REQUEST_MAX_RETRIES`, `REQUEST_BACKOFF_SECONDS` et `LOG_FORMAT` sur le fetcher HTTP.
- Ajout de logs de perf `search_perf` et `volume_perf` pour rendre les coûts visibles dans les logs applicatifs.

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
