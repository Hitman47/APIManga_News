# Déploiement et exploitation

Ce document couvre la partie opérateur : lancement, configuration, cache, logs, quota, debug, diagnostics.

## 1. Modes de lancement

## 1.1 Local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8017 --reload
```

## 1.2 Docker Compose

```bash
docker compose up -d --build
```

Arrêt :

```bash
docker compose down
```

Rebuild complet :

```bash
docker compose down
docker compose up -d --build
```

## 2. Variables d’environnement importantes

Toutes les variables sont dans `.env.example`. Ci-dessous, les plus utiles à connaître rapidement.

## 2.1 Identité et docs

- `APP_NAME`
- `APP_ENV`
- `LOG_LEVEL`
- `LOG_FORMAT=text|json`
- `ENABLE_DOCS=true|false`
- `ENABLE_LEGACY_ROUTES=true|false`

## 2.2 Auth

- `API_TOKEN`
- `ADMIN_TOKEN`

Règle :

- endpoints publics -> `API_TOKEN`
- endpoints admin -> `ADMIN_TOKEN`
- si `ADMIN_TOKEN` est vide -> fallback sur `API_TOKEN`

## 2.3 Réseau vers Manga-News

- `MANGA_NEWS_BASE_URL`
- `USER_AGENT`
- `REQUEST_TIMEOUT_SECONDS`
- `REQUEST_MAX_RETRIES`
- `REQUEST_BACKOFF_SECONDS`

Utilité réelle :

- `REQUEST_TIMEOUT_SECONDS` : temps max d’attente d’une requête amont
- `REQUEST_MAX_RETRIES` : nombre de retries sur erreurs réseau/HTTP éligibles
- `REQUEST_BACKOFF_SECONDS` : base du backoff exponentiel

## 2.4 Cache

- `DB_PATH`
- `CACHE_STALE_GRACE_SECONDS`
- `CACHE_TTL_SEARCH_SECONDS`
- `CACHE_TTL_SERIES_SECONDS`
- `CACHE_TTL_VOLUME_SECONDS`
- `CACHE_TTL_NEWS_GLOBAL_SECONDS`
- `CACHE_TTL_NEWS_SERIES_SECONDS`
- `CACHE_TTL_PLANNING_SECONDS`

### Lecture rapide

- `search` et `series` : TTL d’environ 24h par défaut
- `volume` : TTL plus long, environ 7 jours
- `news/planning` : TTL plus court
- `CACHE_STALE_GRACE_SECONDS` : combien de temps un cache expiré peut encore servir de fallback si l’upstream casse

## 2.5 Cache négatif

- `NEGATIVE_CACHE_ENABLED`
- `NEGATIVE_CACHE_TTL_SECONDS`

Utilité : éviter de refrapper immédiatement une ressource absente ou cassée.

À activer presque toujours. TTL court recommandé.

## 2.6 Rate limiting

- `RATE_LIMIT_ENABLED`
- `RATE_LIMIT_REQUESTS`
- `RATE_LIMIT_WINDOW_SECONDS`
- `RATE_LIMIT_SCOPE=ip|token|ip_or_token`
- `RATE_LIMIT_INCLUDE_ADMIN=true|false`
- `RATE_LIMIT_EXEMPT_PATHS=/openapi.json,/docs,...`

### Recommandation simple

Pour un usage perso ou petit outil :

```env
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS=60
RATE_LIMIT_WINDOW_SECONDS=60
RATE_LIMIT_SCOPE=ip_or_token
RATE_LIMIT_INCLUDE_ADMIN=false
```

## 2.7 Debug parsing

- `DEBUG_CAPTURE_HTML_ON_ERROR`
- `DEBUG_HTML_DUMP_DIR`

À activer uniquement si tu suspectes une casse HTML côté Manga-News.

## 3. Exemples de configuration

## 3.1 Profil local simple

```env
API_TOKEN=
ADMIN_TOKEN=
ENABLE_DOCS=true
LOG_FORMAT=text
RATE_LIMIT_ENABLED=false
NEGATIVE_CACHE_ENABLED=true
DEBUG_CAPTURE_HTML_ON_ERROR=false
```

## 3.2 Profil serveur privé raisonnable

```env
API_TOKEN=replace-me-public
ADMIN_TOKEN=replace-me-admin
ENABLE_DOCS=true
LOG_FORMAT=json
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS=60
RATE_LIMIT_WINDOW_SECONDS=60
RATE_LIMIT_SCOPE=ip_or_token
RATE_LIMIT_INCLUDE_ADMIN=false
NEGATIVE_CACHE_ENABLED=true
NEGATIVE_CACHE_TTL_SECONDS=120
DEBUG_CAPTURE_HTML_ON_ERROR=false
```

## 3.3 Profil debug parsing

```env
DEBUG_CAPTURE_HTML_ON_ERROR=true
DEBUG_HTML_DUMP_DIR=/tmp/manga-news-debug-html
LOG_LEVEL=DEBUG
LOG_FORMAT=json
```

Puis désactive-le après diagnostic. Laisser ça allumé en permanence n’a pas beaucoup d’intérêt.

## 4. Logs et observabilité

## 4.1 Logs

`LOG_FORMAT=text` : pratique en local.

`LOG_FORMAT=json` : pratique si tu collectes les logs ou si tu veux les parser automatiquement.

### Événements utiles dans les logs

Selon le chemin d’exécution, tu verras des événements du type :

- `request_started`
- `request_completed`
- `cache_hit`
- `cache_store`
- `cache_stale_fallback`
- `upstream_fetch_started`
- `upstream_fetch_retry`
- `upstream_fetch_completed`

## 4.2 Endpoint admin de métriques

Route :

```text
GET /v1/admin/metrics
```

Cette route expose :

- compteurs HTTP
- hits/misses de cache
- stale fallbacks
- hits de cache négatif
- erreurs de parsing
- erreurs upstream
- retries upstream
- nombre de `429`
- ratios dérivés

C’est l’endpoint à consulter en premier si tu veux savoir si l’API se dégrade.

## 4.3 Endpoint admin de stats cache

Route :

```text
GET /v1/admin/cache/stats
```

Expose :

- nombre d’entrées par namespace
- nombre d’entrées fraîches / expirées
- détail du cache négatif
- métadonnées des snapshots internes

## 5. Invalidation cache

Route :

```text
POST /v1/admin/cache/invalidate
```

### Payload possible

```json
{
  "cache_key": null,
  "namespace": null,
  "resource_url": null,
  "expired_only": false,
  "all_entries": false
}
```

### Exemples utiles

Invalider une ressource précise :

```bash
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  "http://localhost:8017/v1/admin/cache/invalidate" \
  -d '{"resource_url":"https://www.manga-news.com/index.php/manga/One-Piece/vol-91"}'
```

Invalider un namespace :

```bash
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  "http://localhost:8017/v1/admin/cache/invalidate" \
  -d '{"namespace":"series"}'
```

Invalider tout le cache :

```bash
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  "http://localhost:8017/v1/admin/cache/invalidate" \
  -d '{"all_entries":true}'
```

## 6. Smoke tests et validation opérateur

## 6.1 Script batch

```bash
python scripts/run_api_smoke_tests.py --base-url "$BASE_URL" --token "$TOKEN" --admin-token "$ADMIN_TOKEN"
```

Ce script permet de vérifier rapidement que l’API répond sur les routes principales.

## 6.2 Si le dossier de sortie n’est pas inscriptible

```bash
python scripts/run_api_smoke_tests.py --output-dir /tmp/api_test_outputs
```

ou sans fichiers de sortie :

```bash
python scripts/run_api_smoke_tests.py --output-dir ""
```

## 6.3 Tests projet

```bash
pytest
```

## 7. Diagnostic rapide par symptôme

### Symptôme : `401 AUTH_REQUIRED`

Cause probable :

- token absent
- mauvais token
- endpoint admin appelé avec le token public

À vérifier :

- header `Authorization`
- `API_TOKEN`
- `ADMIN_TOKEN`

### Symptôme : `404 ENDPOINT_NOT_FOUND` sur `/health` ou une route non versionnée

Cause probable :

- routes legacy désactivées

Solution :

- utiliser `/v1/...`
- ou activer explicitement `ENABLE_LEGACY_ROUTES=true` si tu dois garder un vieux client

### Symptôme : `429 RATE_LIMITED`

Cause probable :

- quota dépassé

À faire :

- lire `Retry-After`
- ralentir le client
- ajuster `RATE_LIMIT_*` si nécessaire

### Symptôme : `502 UPSTREAM_FETCH_ERROR`

Cause probable :

- incident réseau
- timeout amont
- Manga-News indisponible

À faire :

- vérifier la connectivité sortante
- vérifier `REQUEST_TIMEOUT_SECONDS`
- vérifier les retries configurés
- consulter `/v1/admin/metrics`

### Symptôme : `502 UPSTREAM_PARSE_ERROR`

Cause probable :

- HTML amont modifié
- parseur cassé pour un type de page

À faire :

1. activer `DEBUG_CAPTURE_HTML_ON_ERROR=true`
2. reproduire la requête
3. inspecter `DEBUG_HTML_DUMP_DIR`
4. corriger le parseur
5. ajouter ou adapter un test de fixture

### Symptôme : résultats surprenants ou trop faibles en recherche

Cause probable :

- score de matching trop strict
- mauvaise formulation de la requête

À faire :

- vérifier `SEARCH_SCORE_THRESHOLD`
- comparer `/search` et `/search/resolve`
- tester `/lookup/volume` si tu connais déjà le numéro du tome

## 8. Sauvegarde et persistance

Le cache SQLite est stocké dans `DB_PATH`.

Si tu utilises Docker, assure-toi que ce chemin pointe sur un volume persistant. Sinon tu perdras le cache à chaque reconstruction.

## 9. OpenAPI et docs interactives

Si `ENABLE_DOCS=true` :

- Swagger : `/docs`
- ReDoc : `/redoc`
- OpenAPI : `/openapi.json`

Pour un déploiement privé, c’est utile. Pour un déploiement plus verrouillé, tu peux désactiver la doc générée avec :

```env
ENABLE_DOCS=false
```
