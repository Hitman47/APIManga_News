# API changelog

Ce fichier suit les changements **du contrat HTTP public** : routes, paramètres, payloads, comportements documentés et exemples.

Il ne sert pas à tracer chaque refactor interne. Il sert à répondre à une seule question :

> "Qu'est-ce qui a changé pour un client qui consomme l'API ?"

## Format recommandé pour les prochaines entrées

Pour chaque version :
- **Added** : nouvelles routes, nouveaux champs, nouvelles capacités ;
- **Changed** : comportement ou payload modifié ;
- **Deprecated** : encore disponible, mais à migrer ;
- **Removed** : supprimé du contrat public ;
- **Docs** : changements de documentation, exemples, guides d'intégration.

---

## 0.2.0

### Added
- Contrat public documenté pour les routes suivantes :
  - `GET /health`
  - `GET /search`
  - `GET /search/resolve`
  - `GET /series/{slug}`
  - `GET /series/by-url`
  - `GET /series/{slug}/related`
  - `GET /series/by-url/related`
  - `GET /series/{slug}/editions`
  - `GET /series/by-url/editions`
  - `GET /volume/{series_slug}/{volume_slug}`
  - `GET /volume/by-url`
  - `GET /news/global`
  - `GET /news/series/{slug}`
  - `GET /news/volume/{series_slug}/{volume_slug}`
  - `GET /news/volume/by-url`
  - `GET /planning`
- Documentation OpenAPI enrichie dans le code : tags, summaries, descriptions et exemples de réponses sur les routes principales.
- Dossier [`docs/examples/`](examples/README.md) avec payloads JSON figés.
- Script [`scripts/validate_contract_and_docs.py`](../scripts/validate_contract_and_docs.py) pour valider l'OpenAPI, les exemples JSON et les liens Markdown locaux.
- Vérification CI explicite du contrat et de la documentation.

### Changed
- La documentation de déploiement et d'intégration a été réalignée sur le **contrat réellement exposé**.
- Le projet documente explicitement qu'il n'existe **pas** de namespace `/v1` aujourd'hui.
- Le projet documente explicitement qu'il n'existe **pas** de routes admin publiques aujourd'hui.

### Deprecated
- Aucune dépréciation publique annoncée à cette version.

### Removed
- Aucune route publique supprimée à cette version.

### Docs
- README réécrit pour servir d'entrée unique fiable.
- Guides d'intégration, d'exploitation et d'usage IA révisés.
- Ajout d'exemples concrets pour One Piece, planning, erreurs et flux d'intégration.
