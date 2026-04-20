# Exemples JSON

Ces fichiers servent à montrer des payloads réalistes sans devoir lancer l'API. Une partie d'entre eux est validée automatiquement contre les modèles Pydantic pour éviter que la doc dérive.

## Exemples canoniques validés par `scripts/validate_contract_and_docs.py`

- `health.json`
- `search_response_one_piece.json`
- `resolve_response_one_piece.json`
- `series_one_piece.json`
- `volume_one_piece_91.json`
- `planning_example.json`
- `series_related_one_piece.json`
- `series_editions_one_piece.json`
- `error_upstream_parse.json`

## Exemples supplémentaires utiles

Ces fichiers sont là pour illustrer des cas d'usage fréquents, même s'ils ne sont pas tous des exemples “canoniques” du validateur :

- `health_ok.json`
- `search_series_one_piece.json`
- `search_resolve_series_one_piece.json`
- `volume_one_piece_110.json`
- `planning_manga_vf_april_2026.json`
- `series_editions_one_piece_all.json`
- `news_global_one_piece_sample.json`
- `error_resource_not_found.json`

## Comment les utiliser

### Pour un développeur
- lire un exemple de recherche ;
- lire la fiche détaillée correspondante ;
- comparer avec `/openapi.json` ;
- seulement ensuite coder le client.

### Pour une autre IA
Donne-lui en priorité :
1. `search_response_one_piece.json`
2. `resolve_response_one_piece.json`
3. `series_one_piece.json`
4. `volume_one_piece_110.json`
5. `planning_example.json`

## Important

Les exemples sont là pour illustrer le **format** et les **champs utiles**. Ils ne garantissent pas que Manga News renverra toujours les mêmes contenus métier ni que chaque champ sera toujours présent.
