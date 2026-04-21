# OpenAPI and AI Usage

## Règle de base

Ne consomme que ce que `/openapi.json` expose réellement.

Cette version n'expose pas :
- de préfixe `/v1` ;
- de routes admin ;
- de `lookup/volume`.

## Stratégie pour une IA

1. Lire `/openapi.json`.
2. Pour trouver une ressource : commencer par `/search/resolve`.
3. Si un slug est nécessaire : réutiliser `best.slug`, `best.series_slug` ou `best.volume_slug`.
4. Lire ensuite `/series/{slug}` ou `/volume/{series_slug}/{volume_slug}`.
5. Réutiliser `ETag` quand possible.

## Champs utiles

Pour les recherches et résolutions :
- `score`
- `confidence`
- `title_vo`
- `translated_title`
- `vf`
- `vo`
- `number`
- `number_int`

Pour une IA ou un client automatisé :
- les compteurs `vf` / `vo` peuvent provenir soit directement de la fiche série, soit d'un enrichissement de la série parente pour une fiche volume ;
- ils sont attendus sur les résultats de recherche enrichis, sur `search/resolve`, sur `series/{slug}` et sur `volume/{series_slug}/{volume_slug}` ;
- tous les champs métier peuvent être absents ou `null` selon la page source.
