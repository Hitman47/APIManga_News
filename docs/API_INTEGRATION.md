# API Integration Guide

Guide détaillé pour intégrer l'API dans un autre service, un script, un crawler ou un agent IA.

## Base URL

Contrat réel :
- Docker : `http://manga-news-api:8000`
- hôte local : `http://localhost:8017`
- réseau local : `http://<host>:8017`

Ne préfixe jamais les routes avec `/v1` dans cette version.

## Auth

### Quand `API_TOKEN` est vide
Aucun header n'est requis.

### Quand `API_TOKEN` est défini
Toutes les routes publiques attendent :

```http
Authorization: Bearer <API_TOKEN>
```

## Enveloppe commune

Toutes les routes métier renvoient une enveloppe `schema_version=1.0`.

```json
{
  "schema_version": "1.0",
  "ok": true,
  "found": true,
  "source": "manga_news",
  "source_url": "https://www.manga-news.com/...",
  "cached": false,
  "fetched_at": "2026-04-21T10:10:10+00:00",
  "cache_expires_at": "2026-04-22T10:10:10+00:00",
  "partial": false,
  "warnings": [],
  "fingerprint": "...",
  "data": {}
}
```

### Interprétation pratique
- `ok` : la requête API a réussi côté serveur ;
- `found` : la ressource demandée a effectivement été trouvée ou résolue ;
- `cached` : la réponse vient du cache ;
- `partial` : la réponse reste exploitable, mais avec un warning ;
- `fingerprint` : hash stable du `data`, utilisé aussi pour `ETag`.

## Erreurs

Format :

```json
{
  "code": "RESOURCE_NOT_FOUND",
  "detail": "Resource not found on Manga News."
}
```

Codes réellement utilisés :
- `AUTH_REQUIRED`
- `RESOURCE_NOT_FOUND`
- `UPSTREAM_FETCH_ERROR`
- `UPSTREAM_PARSE_ERROR`

## Headers HTTP réellement utiles

- `ETag`
- `X-Data-Fingerprint`

Requête conditionnelle :

```http
If-None-Match: "<etag-précédent>"
```

Si le contenu métier n'a pas changé : `304 Not Modified`.

## Endpoints

## 1) `GET /health`

Usage : disponibilité minimale.

Réponse :

```json
{
  "ok": true
}
```

## 2) `GET /search`

### Paramètres
- `q` : texte recherché, obligatoire
- `kind` : `series`, `volume`, `all`
- `mode` : `best`, `all`
- `limit` : 1 à 50

### Ce que fait l'endpoint
- interroge une ou plusieurs pages de recherche Manga-News ;
- score les candidats ;
- renvoie une liste ordonnée ;
- enrichit les candidats retenus avec les titres alternatifs ;
- enrichit aussi les compteurs `vf` / `vo` quand l'information parentale a pu être relue.

### Exemple réel type volume

```json
{
  "schema_version": "1.0",
  "ok": true,
  "found": true,
  "source": "manga_news",
  "source_url": "https://www.manga-news.com/index.php/recherche/?cat=manga-volume-vf&q=Dogs: Bullets & Carnage",
  "cached": false,
  "fetched_at": "2026-04-21T10:10:10+00:00",
  "cache_expires_at": "2026-04-22T10:10:10+00:00",
  "partial": false,
  "warnings": [],
  "fingerprint": "fp-search-dogs",
  "data": [
    {
      "title": "Dogs: Bullets & Carnage Vol.1",
      "url": "https://www.manga-news.com/index.php/manga/Dogs:-Bullets-Carnage/vol-1",
      "kind": "volume",
      "score": 100,
      "slug": null,
      "series_slug": "Dogs:-Bullets-Carnage",
      "volume_slug": "vol-1",
      "number": "1",
      "number_int": 1,
      "edition_label": null,
      "is_special": false,
      "is_one_shot": false,
      "title_vo": "Dogs: Bullets & Carnage",
      "translated_title": "Dogs: Bullets & Carnage",
      "vf": { "volumes": 9, "status": "En cours" },
      "vo": { "volumes": 10, "status": "En pause" }
    }
  ]
}
```

### Recommandation
- utilise `/search` si tu veux comparer plusieurs candidats et interpréter `score` toi-même.

## 3) `GET /search/resolve`

Même base que `/search`, mais l'API choisit un meilleur candidat et ajoute `confidence`.

### Paramètres
- `q`
- `kind`
- `limit`

### Exemple

```json
{
  "data": {
    "query": "one piece",
    "kind_requested": "series",
    "confidence": "high",
    "best": {
      "title": "One Piece",
      "kind": "series",
      "score": 98,
      "slug": "One-piece-Edition-originale",
      "title_vo": "ワンピース",
      "translated_title": "One Piece",
      "vf": { "volumes": 112, "status": "En cours" },
      "vo": { "volumes": 114, "status": "En cours" }
    },
    "candidates": []
  }
}
```

### Recommandation
- utilise `/search/resolve` si tu veux aller vite vers **un** slug ou **un** couple `series_slug` / `volume_slug`.

## 4) `GET /series/{slug}`
## 5) `GET /series/by-url`

Fiche série complète.

### Paramètres spécifiques
- `blocks` : liste CSV de blocs logiques à inclure
- `fields` : liste CSV de chemins précis à inclure
- `include_raw_sections` : inclut ou non `raw_sections`

### Blocs utiles
- `identity`
- `staff`
- `publishing`
- `presentation`
- `editions`
- `stats`
- `related`
- `raw`

### Exemple de projection

```bash
curl --get "http://localhost:8017/series/One-piece-Edition-originale" \
  --data-urlencode "blocks=editions,stats" \
  --data-urlencode "fields=title,vf.volumes"
```

## 6) `GET /series/{slug}/related`
## 7) `GET /series/by-url/related`

Renvoie uniquement les liens liés (`related`).

## 8) `GET /series/{slug}/editions`
## 9) `GET /series/by-url/editions`

### Paramètre
- `edition` : `all`, `vf`, `vo`

Renvoie les blocs d'éditions disponibles avec leurs items normalisés.

## 10) `GET /volume/{series_slug}/{volume_slug}`
## 11) `GET /volume/by-url`

Fiche volume complète.

### Particularité importante
La réponse volume inclut aussi `vf` / `vo` quand la série parente a pu être relue.

### Exemple minimal

```json
{
  "data": {
    "title": "One Piece - Tome 91",
    "series_title": "One Piece",
    "number": "91",
    "number_int": 91,
    "title_vo": "ワンピース",
    "translated_title": "One Piece",
    "publication_date": "2019-07-03",
    "isbn_ean": "9782344037102",
    "vf": { "volumes": 112, "status": "En cours" },
    "vo": { "volumes": 114, "status": "En cours" }
  }
}
```

## 12) `GET /news/global`
## 13) `GET /news/series/{slug}`
## 14) `GET /news/volume/{series_slug}/{volume_slug}`
## 15) `GET /news/volume/by-url`

Ces routes renvoient une liste d'items de news normalisés.

Chaque item peut contenir :
- `title`
- `url`
- `published_at`
- `excerpt`
- `comments`
- `category`

## 16) `GET /planning`

### Paramètres
- `section` : `manga-vf` ou `manga-vo`
- `year`
- `month`
- `page`
- `publisher`
- `q`
- `date_from`
- `date_to`
- `sort` : `date_asc`, `date_desc`, `title_asc`, `title_desc`
- `limit`

### Réponse
`data` contient :
- `section`
- `year`
- `month`
- `page`
- `filters`
- `sort`
- `total_items`
- `items`

Chaque `PlanningItem` peut déjà contenir :
- `number`
- `number_int`
- `edition_label`
- `is_special`
- `is_one_shot`

## Matching tolérant

Le champ `score` est déjà le signal de similarité exploitable côté client.

### Exemple utile
- requête : `Dogs - Bullets & Carnage`
- titre Manga-News : `Dogs: Bullets & Carnage`

Le score reste élevé parce que l'API normalise la ponctuation et les espaces avant comparaison.

## Cache et robustesse

Le service utilise :
- un cache SQLite persistant ;
- un cache négatif court ;
- un mode debug optionnel qui peut dumper le HTML brut sur erreur de parsing.

Ces comportements sont documentés plus en détail dans [DEPLOYMENT_AND_OPERATIONS.md](DEPLOYMENT_AND_OPERATIONS.md).

## Conseils pour une IA ou un agent

1. Commencer par `/openapi.json` pour lire le contrat exposé.  
2. Utiliser `/search/resolve` avant d'appeler `/series/...` ou `/volume/...`.  
3. Interpréter `score` comme un indice, pas comme une preuve absolue.  
4. Réutiliser `ETag` et `If-None-Match`.  
5. Ne pas inventer d'endpoints non présents dans le schéma.
