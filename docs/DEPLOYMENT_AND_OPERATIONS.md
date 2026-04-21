# Deployment and Operations

## Variables utiles

Référence : `.env.example`.

Variables importantes :
- `API_TOKEN`
- `DB_PATH`
- `REQUEST_TIMEOUT_SECONDS`
- `REQUEST_MAX_RETRIES`
- `REQUEST_BACKOFF_SECONDS`
- `CACHE_TTL_SEARCH_SECONDS`
- `CACHE_TTL_SERIES_SECONDS`
- `CACHE_TTL_VOLUME_SECONDS`
- `CACHE_TTL_NEWS_GLOBAL_SECONDS`
- `CACHE_TTL_NEWS_SERIES_SECONDS`
- `CACHE_TTL_PLANNING_SECONDS`
- `NEGATIVE_CACHE_ENABLED`
- `NEGATIVE_CACHE_TTL_SECONDS`
- `DEBUG_CAPTURE_HTML_ON_ERROR`
- `DEBUG_HTML_DUMP_DIR`

## Cache

Le cache principal est SQLite.

Règles pratiques :
- `search` : TTL moyen ;
- `series` : TTL moyen ;
- `volume` : TTL plus long ;
- `news` et `planning` : TTL plus courts.

Le cache négatif évite de refrapper immédiatement une ressource absente ou cassée.

## Quand purger le cache manuellement

En théorie, les routes `series`, `volume`, `search` et `search/resolve` utilisent une version interne de clé de cache. Après une évolution de schéma ou d'enrichissement, les anciennes entrées ne sont donc plus relues.

Tu peux quand même purger manuellement le cache SQLite si :
- tu veux voir immédiatement les nouvelles données sans attendre la prochaine requête non cachée ;
- tu soupçonnes un cache généré par un vieux build ;
- tu fais un audit reproductible endpoint par endpoint.

Dans ce cas, arrête l'application, supprime `DB_PATH`, puis redémarre.

## Dumps HTML de debug

Si `DEBUG_CAPTURE_HTML_ON_ERROR=true`, une `ParseError` peut inclure le chemin du dump HTML enregistré. C'est utile quand Manga-News change son HTML.

## Validation avant livraison

```bash
python scripts/validate_contract_and_docs.py
pytest
```
