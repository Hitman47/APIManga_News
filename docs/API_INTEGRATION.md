# Guide d'intégration API

Ce document est le guide de référence pour intégrer l'API depuis une application, un script, un service ou une IA.

## 1. Vue rapide

Base URL typiques :
- local direct : `http://localhost:8017`
- même réseau Docker : `http://manga-news-api:8000`
- autre machine du LAN : `http://<ip-hote>:8017`

Endpoints principaux :
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
  "data": {}
}
```

Signification des champs importants :
- `found` : indique si une ressource exploitable a été trouvée ;
- `cached` : indique si le résultat vient du cache ;
- `partial` : vrai si l'API a dû servir une version de repli ;
- `warnings` : informations non bloquantes ;
- `fingerprint` : hash logique du `data`, utilisé aussi comme `ETag`.

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
curl -i "http://localhost:8017/series/One-piece-Edition-originale" \
  -H 'If-None-Match: "<fingerprint>"'
```

## 5. Gestion des erreurs

Format d'erreur actuel :

```json
{ "detail": "..." }
```

Codes à traiter :
- `401` : token absent ou invalide ;
- `404` : la page ciblée n'existe pas ;
- `502` : le fetch amont a échoué ou le parser n'a pas reconnu la page ;
- `304` : inchangé, pas de body.

## 6. Référence endpoint par endpoint

### 6.1 `GET /health`

Usage : vérifier que l'API répond.

Réponse :

```json
{ "ok": true }
```

### 6.2 `GET /search`

Recherche libre.

Paramètres :
- `q` : texte à chercher ;
- `kind` : `series`, `volume`, `all` ;
- `mode` : `best`, `all` ;
- `limit` : nombre maximum de résultats.

Exemple :

```bash
curl --get "http://localhost:8017/search" \
  --data-urlencode "q=one piece" \
  --data-urlencode "kind=series" \
  --data-urlencode "mode=all" \
  --data-urlencode "limit=5"
```

Quand utiliser `/search` :
- si tu veux afficher plusieurs candidats à un utilisateur ;
- si tu veux journaliser les scores ;
- si tu veux choisir toi-même la stratégie de sélection.

### 6.3 `GET /search/resolve`

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
curl --get "http://localhost:8017/search/resolve" \
  --data-urlencode "q=one piece tome 110" \
  --data-urlencode "kind=volume"
```

### 6.4 `GET /series/{slug}`

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
curl --get "http://localhost:8017/series/One-piece-Edition-originale" \
  --data-urlencode "blocks=identity,editions,stats"
```

```bash
curl --get "http://localhost:8017/series/One-piece-Edition-originale" \
  --data-urlencode "fields=title,vf.volumes,next_release_date"
```

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

### 6.5 `GET /series/by-url`

Même comportement, mais à partir de l'URL Manga News complète.

Exemple :

```bash
curl --get "http://localhost:8017/series/by-url" \
  --data-urlencode "url=https://www.manga-news.com/index.php/serie/One-piece-Edition-originale"
```

### 6.6 `GET /series/{slug}/related`

Retourne les contenus liés à une série.

Exemple :

```bash
curl "http://localhost:8017/series/One-piece-Edition-originale/related"
```

### 6.7 `GET /series/{slug}/editions`

Retourne les éditions VF, VO, ou les deux.

Paramètre :
- `edition=all|vf|vo`

Exemple :

```bash
curl "http://localhost:8017/series/One-piece-Edition-originale/editions?edition=all"
```

### 6.8 `GET /volume/{series_slug}/{volume_slug}`

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

```bash
curl --get "http://localhost:8017/volume/One-Piece/vol-110" \
  --data-urlencode "fields=title,publication_date,isbn_ean"
```

### 6.9 `GET /volume/by-url`

Même comportement, mais à partir de l'URL du volume.

### 6.10 `GET /news/global`

Lit le flux RSS global.

Exemple :

```bash
curl "http://localhost:8017/news/global?limit=10"
```

### 6.11 `GET /news/series/{slug}`

Lit les news d'une série.

### 6.12 `GET /news/volume/{series_slug}/{volume_slug}`

Lit les news d'un volume.

### 6.13 `GET /news/volume/by-url`

Même comportement à partir de l'URL du volume.

### 6.14 `GET /planning`

Filtre le planning des sorties.

Paramètres :
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

Exemple complet :

```bash
curl --get "http://localhost:8017/planning" \
  --data-urlencode "section=manga-vf" \
  --data-urlencode "year=2026" \
  --data-urlencode "month=4" \
  --data-urlencode "publisher=Glénat" \
  --data-urlencode "q=one piece" \
  --data-urlencode "date_from=2026-04-01" \
  --data-urlencode "date_to=2026-04-30" \
  --data-urlencode "sort=date_asc" \
  --data-urlencode "limit=25"
```

## 7. Workflows recommandés

### Workflow A — chercher une série et charger sa fiche

1. `GET /search/resolve?q=<titre>&kind=series`
2. lire `data.best.slug`
3. `GET /series/{slug}`
4. stocker l'ETag
5. rejouer avec `If-None-Match` plus tard

### Workflow B — chercher un tome puis récupérer ses métadonnées

1. `GET /search/resolve?q=<titre+tome>&kind=volume`
2. lire `data.best.series_slug` et `data.best.volume_slug`
3. `GET /volume/{series_slug}/{volume_slug}`

### Workflow C — interface qui affiche plusieurs résultats

1. `GET /search?mode=all&limit=10`
2. afficher `title`, `kind`, `score`
3. laisser l'utilisateur choisir
4. charger ensuite `/series/...` ou `/volume/...`

### Workflow D — surveillance légère d'un planning

1. lancer `GET /planning?...`
2. stocker `ETag`
3. relancer régulièrement avec `If-None-Match`
4. traiter `304` comme “aucun changement”

## 8. Conseils d'intégration pour une IA

Quand tu branches cette API à une autre IA :

- commence par `/openapi.json` pour le contrat réel ;
- ne suppose aucune route non documentée ;
- préfère `/search/resolve` à `/search` si tu veux automatiser ;
- quand tu connais déjà l'URL Manga News, utilise les routes `/by-url` ;
- exploite `ETag` pour éviter les requêtes inutiles ;
- utilise `fields` et `blocks` si tu veux limiter le bruit.

Prompt minimal réutilisable :

> Utilise `GET /openapi.json` comme source de vérité. Pour résoudre un manga, appelle d'abord `/search/resolve`. Ensuite, charge `/series/{slug}` ou `/volume/{series_slug}/{volume_slug}`. Réutilise l'ETag avec `If-None-Match` quand tu relances une même requête. N'invente aucune route absente de l'OpenAPI.

## 9. Ce qu'il faut éviter

- parser directement le HTML si l'API fournit déjà la donnée ;
- supposer que tous les champs seront toujours remplis ;
- supposer que `search/resolve` est infaillible ;
- documenter des routes qui n'existent pas dans `/openapi.json`.
