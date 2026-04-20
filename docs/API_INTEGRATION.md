# Guide d'intégration API

Ce document est le guide de référence pour intégrer l'API depuis une application, un script, un service ou une IA.

## 1. Vue rapide

Base URL typiques :
- local direct : `http://localhost:8017`
- même réseau Docker : `http://manga-news-api:8000`
- autre machine du LAN : `http://<ip-hote>:8017`

Contrat public actuel :
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

Important :
- il n'existe **pas** de routes admin publiques aujourd'hui ;
- la source de vérité machine-readable reste `GET /openapi.json`.

## 2. Authentification

Si `API_TOKEN` est vide, l'API ne demande pas d'authentification.

Si `API_TOKEN` est défini :

```http
Authorization: Bearer <token>
```

Exemple `curl` :

```bash
curl -H "Authorization: Bearer MON_TOKEN" "http://localhost:8017/health"
```

## 3. Format standard des réponses

La plupart des routes renvoient cette enveloppe :

```json
{
  "schema_version": "1.0",
  "ok": true,
  "found": true,
  "source": "manga_news",
  "source_url": "https://www.manga-news.com/...",
  "cached": false,
  "fetched_at": "2026-04-20T12:00:00+00:00",
  "cache_expires_at": "2026-04-21T12:00:00+00:00",
  "partial": false,
  "warnings": [],
  "fingerprint": "...",
  "pagination": null,
  "data": {}
}
```

Signification des champs importants :
- `found` : indique si une ressource exploitable a été trouvée ;
- `cached` : indique si le résultat vient du cache ;
- `partial` : vrai si l'API a dû servir une version de repli ;
- `warnings` : informations non bloquantes ;
- `fingerprint` : hash logique du `data`, utilisé aussi comme `ETag` ;
- `pagination` : métadonnées présentes sur les endpoints de liste (`search`, `search/resolve`, `news`, `planning`) quand le service en renvoie.

## 4. Cache côté client avec `ETag`

Quand l'API renvoie un `fingerprint`, elle renvoie aussi :
- `ETag: "<fingerprint>"`
- `X-Data-Fingerprint: <fingerprint>`

Workflow recommandé :
1. faire la première requête ;
2. stocker l'ETag ;
3. rejouer plus tard la même requête avec `If-None-Match` ;
4. traiter `304 Not Modified` comme “rien n'a changé”.

Exemple :

```bash
curl -i "http://localhost:8017/series/One-piece-Edition-originale"
```

Puis :

```bash
curl -i "http://localhost:8017/series/One-piece-Edition-originale"   -H 'If-None-Match: "<fingerprint>"'
```

## 5. Gestion des erreurs

Format d'erreur public actuel :

```json
{ "detail": "..." }
```

Codes à traiter :
- `401` : token absent ou invalide ;
- `404` : la page ciblée n'existe pas ;
- `502` : le fetch amont a échoué ou le parser n'a pas reconnu la page ;
- `304` : inchangé, pas de body.

Les payloads JSON d'exemple de ce type sont dans :
- [`examples/error_resource_not_found.json`](examples/error_resource_not_found.json)
- [`examples/error_upstream_parse.json`](examples/error_upstream_parse.json)

## 6. Exemples JSON figés

Avant d'intégrer en production, regarde aussi :
- [`examples/search_series_one_piece.json`](examples/search_series_one_piece.json)
- [`examples/search_resolve_series_one_piece.json`](examples/search_resolve_series_one_piece.json)
- [`examples/series_one_piece.json`](examples/series_one_piece.json)
- [`examples/series_related_one_piece.json`](examples/series_related_one_piece.json)
- [`examples/series_editions_one_piece_all.json`](examples/series_editions_one_piece_all.json)
- [`examples/volume_one_piece_110.json`](examples/volume_one_piece_110.json)
- [`examples/news_global_one_piece_sample.json`](examples/news_global_one_piece_sample.json)
- [`examples/planning_manga_vf_april_2026.json`](examples/planning_manga_vf_april_2026.json)

Pour une IA, c'est souvent le chemin le plus rapide :
1. lire `/openapi.json` ;
2. regarder 2 ou 3 payloads d'exemple ;
3. appeler la route réelle.

## 7. Référence endpoint par endpoint

### 7.1 `GET /health`

Usage : vérifier que l'API répond.

Réponse :

```json
{ "ok": true }
```

Exemple figé : [`examples/health_ok.json`](examples/health_ok.json)

### 7.2 `GET /search`

Recherche libre.

Paramètres :
- `q` : texte à chercher ;
- `kind` : `series`, `volume`, `all` ;
- `mode` : `best`, `all` ;
- `limit` : nombre maximum de résultats.

Exemple :

```bash
curl --get "http://localhost:8017/search"   --data-urlencode "q=one piece"   --data-urlencode "kind=series"   --data-urlencode "mode=all"   --data-urlencode "limit=5"
```

Exemple figé : [`examples/search_series_one_piece.json`](examples/search_series_one_piece.json)

Quand utiliser `/search` :
- si tu veux afficher plusieurs candidats à un utilisateur ;
- si tu veux journaliser les scores ;
- si tu veux choisir toi-même la stratégie de sélection.

### 7.3 `GET /search/resolve`

Même idée que `/search`, mais pensée pour l'automatisation.

Paramètres :
- `q` ;
- `kind` ;
- `limit`.

Réponse utile :
- `data.best` : meilleur résultat ;
- `data.candidates` : autres candidats ;
- `data.confidence` : `high`, `medium`, `low`, `none`.

Exemple :

```bash
curl --get "http://localhost:8017/search/resolve"   --data-urlencode "q=one piece tome 110"   --data-urlencode "kind=volume"
```

Exemple figé : [`examples/search_resolve_series_one_piece.json`](examples/search_resolve_series_one_piece.json)

### 7.4 `GET /series/{slug}`

Charge une fiche série à partir de son slug.

Paramètres utiles :
- `blocks` : projection par blocs ;
- `fields` : projection fine par chemins ;
- `include_raw_sections=true` : ajoute les sections brutes extraites du HTML.

Exemples :

```bash
curl "http://localhost:8017/series/One-piece-Edition-originale"
```

```bash
curl --get "http://localhost:8017/series/One-piece-Edition-originale"   --data-urlencode "blocks=identity,editions,stats"
```

```bash
curl --get "http://localhost:8017/series/One-piece-Edition-originale"   --data-urlencode "fields=title,vf.volumes,next_release_date"
```

Exemple figé : [`examples/series_one_piece.json`](examples/series_one_piece.json)

Blocs séries disponibles :
- `identity`
- `staff`
- `publishing`
- `presentation`
- `editions`
- `stats`
- `related`
- `raw`
- `raw_sections`

### 7.5 `GET /series/by-url`

Même comportement, mais à partir de l'URL Manga News complète.

Exemple :

```bash
curl --get "http://localhost:8017/series/by-url"   --data-urlencode "url=https://www.manga-news.com/index.php/serie/One-piece-Edition-originale"
```

### 7.6 `GET /series/{slug}/related`

Retourne les contenus liés à une série.

Exemple :

```bash
curl "http://localhost:8017/series/One-piece-Edition-originale/related"
```

Exemple figé : [`examples/series_related_one_piece.json`](examples/series_related_one_piece.json)

### 7.7 `GET /series/{slug}/editions`

Retourne les éditions VF, VO, ou les deux.

Paramètre :
- `edition=all|vf|vo`

Exemple :

```bash
curl "http://localhost:8017/series/One-piece-Edition-originale/editions?edition=all"
```

Exemple figé : [`examples/series_editions_one_piece_all.json`](examples/series_editions_one_piece_all.json)

### 7.8 `GET /volume/{series_slug}/{volume_slug}`

Charge une fiche volume à partir des deux slugs.

Paramètres utiles :
- `blocks`
- `fields`
- `include_raw_sections`

Blocs volumes disponibles :
- `identity`
- `staff`
- `publishing`
- `presentation`
- `release`
- `scores`
- `related`
- `raw`
- `raw_sections`

Exemple :

```bash
curl "http://localhost:8017/volume/One-Piece/vol-110"
```

Exemple figé : [`examples/volume_one_piece_110.json`](examples/volume_one_piece_110.json)

### 7.9 `GET /volume/by-url`

Même comportement que la route par slugs, mais à partir d'une URL Manga News complète.

### 7.10 `GET /news/global`

Retourne les news globales issues du flux RSS public.

Exemple :

```bash
curl "http://localhost:8017/news/global?limit=5"
```

Exemple figé : [`examples/news_global_one_piece_sample.json`](examples/news_global_one_piece_sample.json)

### 7.11 `GET /news/series/{slug}`

Retourne les news liées à une série.

Exemple :

```bash
curl "http://localhost:8017/news/series/One-piece-Edition-originale?limit=10"
```

### 7.12 `GET /news/volume/{series_slug}/{volume_slug}`

Retourne les news liées à un volume précis.

Exemple :

```bash
curl "http://localhost:8017/news/volume/One-Piece/vol-110?limit=10"
```

### 7.13 `GET /news/volume/by-url`

Même comportement que la route par slugs, mais à partir de l'URL du volume.

### 7.14 `GET /planning`

Permet d'interroger le planning des sorties.

Paramètres principaux :
- `section=manga-vf|manga-vo`
- `year`
- `month`
- `page`
- `publisher`
- `q`
- `date_from`
- `date_to`
- `sort=date_asc|date_desc|title_asc|title_desc`
- `limit`

Exemple :

```bash
curl --get "http://localhost:8017/planning"   --data-urlencode "section=manga-vf"   --data-urlencode "year=2026"   --data-urlencode "month=4"   --data-urlencode "publisher=Glénat"   --data-urlencode "sort=date_asc"   --data-urlencode "limit=25"
```

Exemple figé : [`examples/planning_manga_vf_april_2026.json`](examples/planning_manga_vf_april_2026.json)

## 8. Flows d'intégration recommandés

### 8.1 Titre libre vers fiche série

1. appeler `/search/resolve?q=<titre>&kind=series`
2. lire `data.best.slug`
3. appeler `/series/{slug}`
4. mettre en cache côté client avec `ETag`

### 8.2 URL Manga News déjà connue

1. appeler `/series/by-url` ou `/volume/by-url`
2. éviter une recherche intermédiaire inutile

### 8.3 UI légère

1. appeler la fiche avec `fields=`
2. limiter le payload à ce que l'écran consomme réellement

### 8.4 Client robuste

1. traiter `401`, `404`, `502`, `304`
2. considérer les champs comme optionnels
3. ne jamais inventer une route absente de `/openapi.json`

## 9. Validation locale doc + contrat

Commande :

```bash
python scripts/validate_contract_and_docs.py
```

Ce contrôle vérifie :
- la génération de l'OpenAPI ;
- les routes critiques ;
- les tags critiques ;
- la validité des exemples JSON ;
- les liens Markdown locaux de la doc.
