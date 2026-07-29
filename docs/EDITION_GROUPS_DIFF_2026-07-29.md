# Diff fonctionnel - groupes d'editions - 2026-07-29

## Ajouts

- `GET /series/{slug}/edition-groups`
- `GET /search/editions`
- `include_volumes=false` par defaut sur les deux nouvelles routes
- `edition_label` facultatif sur `GET /volume/{series_slug}/number/{number}`
- `edition_label` facultatif sur `GET /series/{slug}/release-state`
- compteurs `volume_count`, `total_volumes`, `highest_volume_number` et
  `available_numbers`
- statut qualifie par `status_source`, `status_confidence` et `status_reason`
- parsing limite aux sections `.boxedTitleWrapper` / `.boxedContent`

## Inchange

- aucun endpoint n'est supprime ou renomme ;
- `/search` conserve ses valeurs par defaut et son format de reponse ;
- `include_editions` conserve son sens historique de compteurs globaux VF/VO ;
- `/series/{slug}/editions` conserve son parseur et son format plats ;
- `/volume/{series_slug}/number/{number}` sans `edition_label` conserve sa
  selection historique ;
- `/series/{slug}/release-state` sans `edition_label` conserve son calcul
  historique ;
- le port Docker, le tag GHCR et les routes de documentation ne changent pas.

## Exemple Eden

Avant, `/series/Eden/editions` fournissait une liste plate qui ne permettait pas
d'exprimer proprement le total et le statut de chaque edition.

Avec `/series/Eden/edition-groups`, l'edition originale expose 18 tomes et
l'edition Perfect 9 tomes. Le statut original est explicite; celui de la Perfect
est marque `inferred` avec sa justification, jamais comme une source explicite.

La documentation complete est dans [EDITION_GROUPS.md](EDITION_GROUPS.md).
