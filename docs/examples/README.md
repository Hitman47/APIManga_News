# Exemples JSON

Ce dossier contient des exemples JSON **canoniques** et **validés** contre les modèles Pydantic du projet.

Ils servent à :
- comprendre rapidement la forme réelle des réponses ;
- amorcer un client ou un prompt d'IA ;
- écrire des tests d'intégration ;
- vérifier qu'un changement de contrat n'a pas cassé les payloads documentés.

## Exemples actuellement fournis

### Santé
- `health.json`

### Recherche
- `search_response_one_piece.json`
- `resolve_response_one_piece.json`

### Série
- `series_one_piece.json`
- `series_related_one_piece.json`
- `series_editions_one_piece.json`

### Volume
- `volume_one_piece_91.json`
- `volume_one_piece_110.json`

### Planning
- `planning_example.json`
- `planning_manga_vf_april_2026.json`

### News
- `news_global_one_piece_sample.json`

### Erreurs
- `error_resource_not_found.json`
- `error_upstream_parse.json`

## Comment les utiliser

### Pour un développeur
- lire l'exemple avant d'écrire le mapping client ;
- vérifier la présence de `null` et des champs optionnels ;
- comparer ensuite à `/openapi.json`.

### Pour une IA
- charger d'abord `README.md` et `docs/API_INTEGRATION.md` ;
- utiliser ces JSON comme exemples réalistes ;
- ne pas inventer de champs absents de ces exemples et de l'OpenAPI.

## Validation

Commande :

```bash
python scripts/validate_contract_and_docs.py
```

Cette validation vérifie que les exemples canoniques restent compatibles avec les modèles du projet.
