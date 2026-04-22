# Guide d'intégration API

Ce document sert de référence pratique pour un développeur, un service externe ou une autre IA.

## 1. Base URL

Selon l'endroit depuis lequel tu appelles l'API :
- réseau Docker : `http://manga-news-api:8000`
- machine hôte : `http://localhost:8017`
- LAN : `http://<ip-hote>:8017`

Le contrat public **n'a pas** de préfixe `/v1`.

## 2. Authentification

### Cas 1 — API ouverte
Si `API_TOKEN` est vide, aucun header n'est nécessaire.

### Cas 2 — API protégée
Si `API_TOKEN` est défini, ajoute :

```http
Authorization: Bearer <token>
```

### Réponse 401 actuelle
Le format exact actuel est :

```json
{
  "detail": {
    "code": "AUTH_REQUIRED",
    "detail": "Missing or invalid bearer token."
  }
}
```

## 3. Enveloppe commune

Toutes les routes métier sauf `/health` renvoient une enveloppe standard :

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

### Sens des champs importants
- `found=false` : la route a répondu correctement mais sans ressource exploitable ;
- `cached=true` : la réponse vient du cache SQLite ;
- `partial=true` : la réponse provient d'un cache stale utilisé après échec upstream ;
- `warnings` : message explicatif, généralement lié à `partial=true` ;
- `fingerprint` : hash métier stable servant d'ETag ;
- `source_url` : URL Manga News effectivement utilisée.

## 4. Gestion du cache côté client

Quand un `fingerprint` est présent, l'API renvoie aussi :
- `ETag: "<fingerprint>"`
- `X-Data-Fingerprint: <fingerprint>`

Tu peux alors envoyer :

```http
If-None-Match: "<fingerprint>"
```

Si rien n'a changé, l'API répond `304 Not Modified` avec un corps vide.

## 5. Erreurs documentées

### 404

```json
{
  "code": "RESOURCE_NOT_FOUND",
  "detail": "Resource not found on Manga News."
}
```

### 502 — parsing

```json
{
  "code": "UPSTREAM_PARSE_ERROR",
  "detail": "Unable to extract the volume title."
}
```

Si `DEBUG_CAPTURE_HTML_ON_ERROR=true`, le détail peut inclure :

```text
Debug HTML saved to /tmp/manga-news-debug-html/volume-....html
```

### 502 — fetch upstream

```json
{
  "code": "UPSTREAM_FETCH_ERROR",
  "detail": "Manga News returned HTTP 503."
}
```

## 6. Référence route par route

### 6.1 `GET /health`

Usage : vérifier que l'application répond.

Réponse :

```json
{ "ok": true }
```

---

### 6.2 `GET /search`

Usage : rechercher des séries ou des volumes à partir d'un texte libre.

Paramètres :
- `q` : texte libre, obligatoire ;
- `kind` : `series`, `volume`, `all` ;
- `mode` : `best` ou `all` ;
- `limit` : 1 à 50.

Exemple :

```bash
curl --get "http://localhost:8017/search" \
  --data-urlencode "q=black night parade" \
  --data-urlencode "kind=series" \
  --data-urlencode "mode=all" \
  --data-urlencode "limit=5"
```

Résultat typique par item :
- `title`
- `url`
- `kind`
- `score`
- `slug`
- `series_slug`
- `volume_slug`
- `title_vo`
- `translated_title`

Important :
- `mode=best` retourne **une liste** contenant au mieux un seul item ;
- par défaut, la recherche ne lit que la page de recherche ;
- `include_editions=true` (par défaut) hydrate les compteurs `vf` / `vo` via la fiche série parente ;
- `enrich=true` déclenche en plus la relecture des fiches détaillées utiles pour récupérer `title_vo`, `translated_title` et la normalisation volume ;
- si l'enrichissement échoue, le résultat principal reste retourné.

---

### 6.3 `GET /search/resolve`

Usage : obtenir directement le meilleur candidat et sa confiance.

Paramètres :
- `q`
- `kind`
- `limit`

Exemple :

```bash
curl --get "http://localhost:8017/search/resolve" \
  --data-urlencode "q=one piece tome 110" \
  --data-urlencode "kind=volume" \
  --data-urlencode "limit=10"
```

Réponse :
- `data.query`
- `data.kind_requested`
- `data.confidence` (`high`, `medium`, `low`, `none`)
- `data.best`
- `data.candidates`

---

### 6.4 `GET /series/{slug}`
### 6.5 `GET /series/by-url`

Usage : fiche détaillée d'une série.

Paramètres communs :
- `blocks` : liste CSV de blocs métier ;
- `fields` : liste CSV de chemins ciblés ;
- `include_raw_sections` : booléen.

#### Blocs série disponibles
- `identity`
- `staff`
- `publishing`
- `presentation`
- `editions`
- `stats`
- `related`
- `raw` / `raw_sections`

#### Champs métier importants de la fiche série
- `title`
- `title_vo`
- `translated_title`
- `summary`
- `authors_story`
- `authors_art`
- `translators`
- `publisher_fr`
- `publisher_vo`
- `collection`
- `type`
- `genres`
- `prepublication`
- `origin`
- `illustration`
- `illustration_details`
- `advisory_age`
- `cover_image`
- `vf`
- `vo`
- `last_release_date`
- `next_release_date`
- `stats`
- `themes`
- `strengths`
- `related`
- `raw_sections` si demandé

Exemple léger :

```bash
curl --get "http://localhost:8017/series/One-piece-Edition-originale" \
  --data-urlencode "fields=title,title_vo,translated_title,vf.volumes,next_release_date"
```

Exemple bloc + champ :

```bash
curl --get "http://localhost:8017/series/One-piece-Edition-originale" \
  --data-urlencode "blocks=identity,stats" \
  --data-urlencode "fields=cover_image"
```

---

### 6.6 `GET /series/{slug}/related`
### 6.7 `GET /series/by-url/related`

Usage : récupérer les liens liés à une série.

Structure :
- `series`
- `volumes`
- `anime`
- `drama`
- `dossiers`
- `univers`
- `external`
- `misc`

Chaque entrée est un `LinkItem` avec `title`, `url`, `kind`.

---

### 6.8 `GET /series/{slug}/editions`
### 6.9 `GET /series/by-url/editions`

Usage : récupérer les éditions VF / VO d'une série.

Paramètre :
- `edition=all|vf|vo`

Structure :
- `data.title`
- `data.series_slug`
- `data.vf`
- `data.vo`

Chaque item d'édition expose notamment :
- `title`
- `url`
- `series_slug`
- `volume_slug`
- `number`
- `number_int`
- `edition_label`
- `is_special`
- `is_one_shot`
- `publication_date`
- `cover_image`

---

### 6.10 `GET /volume/{series_slug}/{volume_slug}`
### 6.11 `GET /volume/by-url`

Usage : fiche détaillée d'un volume. Par défaut, seule la fiche volume est lue. `include_parent_editions=true` ou une projection explicite sur `vf` / `vo` déclenche la lecture de la série parente.

Paramètres communs :
- `blocks`
- `fields`
- `include_raw_sections`

#### Blocs volume disponibles
- `identity`
- `staff`
- `publishing`
- `presentation`
- `release`
- `scores`
- `related`
- `raw` / `raw_sections`

#### Champs métier importants de la fiche volume
- `title`
- `series_title`
- `number`
- `number_int`
- `edition_label`
- `is_special`
- `is_one_shot`
- `title_vo`
- `translated_title`
- `summary`
- `authors_story`
- `authors_art`
- `translators`
- `publisher_fr`
- `publisher_vo`
- `collection`
- `type`
- `genres`
- `prepublication`
- `origin`
- `illustration`
- `illustration_details`
- `advisory_age`
- `publication_date`
- `isbn_ean`
- `price_code`
- `cover_image`
- `editorial_score`
- `reader_score`
- `related`
- `raw_sections` si demandé

Exemple :

```bash
curl --get "http://localhost:8017/volume/One-Piece/vol-110" \
  --data-urlencode "blocks=identity,release,scores" \
  --data-urlencode "fields=cover_image"
```

---

### 6.12 `GET /news/global`

Usage : flux RSS global Manga News, normalisé en JSON.

Paramètre :
- `limit`

Chaque item expose :
- `title`
- `url`
- `published_at`
- `excerpt`
- `comments`
- `category`

---

### 6.13 `GET /news/series/{slug}`

Usage : news liées à une série.

Paramètre :
- `limit`

---

### 6.14 `GET /news/volume/{series_slug}/{volume_slug}`
### 6.15 `GET /news/volume/by-url`

Usage : news liées à un volume.

Paramètre :
- `limit`

Le endpoint `by-url` est utile quand tu n'as qu'une URL Manga News complète.

---

### 6.16 `GET /planning`

Usage : récupérer une page de planning VF ou VO, puis filtrer localement.

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

Important :
- la route ne fait **pas** de pagination métier universelle ;
- elle va chercher **une page upstream**, puis applique des filtres locaux ;
- `total_items` correspond au total **après** filtrage local sur la page chargée, pas à un total global multi-pages côté Manga News.

Chaque item du planning expose notamment :
- `title`
- `url`
- `release_date`
- `authors`
- `publisher`
- `summary`
- `featured`
- `series_slug`
- `volume_slug`
- `number`
- `number_int`
- `edition_label`
- `is_special`
- `is_one_shot`

## 7. Flux d'intégration recommandés

### 7.1 À partir d'un titre libre, charger la fiche série
1. `GET /search/resolve?q=<titre>&kind=series`
2. récupérer `data.best.slug`
3. `GET /series/{slug}`

### 7.2 À partir d'un titre libre, charger la fiche volume
1. `GET /search/resolve?q=<titre>&kind=volume`
2. récupérer `series_slug` et `volume_slug`
3. `GET /volume/{series_slug}/{volume_slug}`

### 7.3 UI légère
- utilise `fields=` ou `blocks=` pour éviter les payloads complets ;
- stocke `fingerprint` et `ETag` ;
- rejoue avec `If-None-Match`.

### 7.4 Synchronisation robuste
- si `partial=true`, ne détruis pas ta donnée locale ;
- lis `warnings` ;
- considère que le cache stale a été servi à cause d'un problème upstream.

## 8. Règles simples pour une autre IA

Tu peux donner ces règles à un agent consommateur :
- n'invente jamais de route absente de `/openapi.json` ;
- n'invente pas de `/v1` ;
- suppose que tous les champs métier peuvent être absents ou `null` ;
- pour une recherche, essaie d'abord `/search/resolve` avant `/search` si tu veux un seul candidat ;
- pour une UI ou un prompt compact, privilégie `fields=` ;
- exploite `title_vo` et `translated_title` quand ils sont présents, mais ne suppose pas qu'ils existeront à chaque fois ;
- si tu vois `partial=true`, ne présente pas le résultat comme une donnée fraîche.

## 9. Limitations connues

- Le parsing dépend du HTML public de Manga News.
- Certaines variables de config existent sans être branchées au runtime public actuel.
- Les recherches gardent par défaut les compteurs `vf` / `vo` ; activer `enrich=true` seulement quand les titres alternatifs ou la normalisation volume sont réellement utiles, et passer `include_editions=false` seulement si la latence prime même sur les compteurs.
- Les enrichissements sont désormais dédupliqués et exécutés avec une concurrence bornée.


## Note de cache importante

Les réponses `series`, `volume`, `search`, `search/resolve` et `series/{slug}/editions` dépendent d'un cache SQLite local. Le runtime ajoute maintenant un cache mémoire L1, SQLite WAL, un `busy_timeout`, une déduplication single-flight pour éviter les fetchs et accès disque redondants, un cache source dédié pour les candidats de recherche, puis un cache séparé pour les blocs d'éditions série `vf` / `vo`. Quand le parseur évolue (par exemple pour mieux remonter `vf` / `vo`), l'application ignore automatiquement les anciennes entrées de cache incompatibles grâce à une version interne de schéma de cache. Après déploiement, un simple redémarrage de l'API suffit normalement à voir les nouvelles données. Supprimer le fichier SQLite de cache reste la méthode la plus radicale si vous voulez repartir d'un cache totalement vierge.


- `enrich=true` sur `/search` et `/search/resolve` doit rester un choix explicite : c'est utile, mais plus coûteux qu'une recherche brute, même si les enrichissements volume passent désormais par un chemin léger dédié.
- `include_editions=false` coupe aussi l’hydratation des compteurs `vf` / `vo` et reste donc le chemin le plus rapide possible quand ces compteurs sont inutiles.
- `include_parent_editions=true` sur les fiches volume doit rester opt-in.
- changer uniquement `limit` sur `/news/global`, `/news/series/...` ou `/news/volume/...` ne force plus un refetch upstream tant que la source news reste chaude en cache.
