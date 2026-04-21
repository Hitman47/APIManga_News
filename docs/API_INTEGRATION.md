# API Integration Guide

Ce guide décrit **le contrat réel** de l'API actuelle.

## Base URL

- Docker : `http://manga-news-api:8000`
- machine hôte : `http://localhost:8017`
- LAN : `http://<host-ip>:8017`

## Auth

Si `API_TOKEN` est défini :

```http
Authorization: Bearer <API_TOKEN>
```

## Enveloppe

Toutes les routes métier renvoient une enveloppe `schema_version=1.0`.

Champs à surveiller :
- `found` : aucun résultat exploitable ou pas ;
- `cached` : la réponse vient du cache ;
- `partial` : fallback sur une réponse stale ;
- `warnings` : explications complémentaires ;
- `fingerprint` : hash de `data` ;
- `source_url` : page Manga-News réellement consultée.

## Endpoints

### 1) `GET /health`

Disponibilité minimale.

### 2) `GET /search`

Paramètres :
- `q` : texte libre ;
- `kind` : `series`, `volume`, `all` ;
- `mode` : `best`, `all` ;
- `limit` : 1 à 50.

Comportement :
- lance une ou plusieurs pages de recherche Manga-News ;
- score les résultats ;
- déduplique les URLs ;
- enrichit les meilleurs résultats avec les champs détaillés.

Pour un résultat `series`, l'API peut ajouter :
- `title_vo`
- `translated_title`
- `vf`
- `vo`

Pour un résultat `volume`, l'API peut ajouter :
- `title_vo`
- `translated_title`
- `number`
- `number_int`
- `edition_label`
- `is_special`
- `is_one_shot`
- `vf`
- `vo`

Les compteurs `vf` / `vo` sont lus prioritairement dans le bloc `#numberblock` de Manga-News.

### 3) `GET /search/resolve`

Même logique que `/search`, mais renvoie :
- `best`
- `candidates`
- `confidence` (`high`, `medium`, `low`, `none`)

### 4) `GET /series/{slug}`
### 5) `GET /series/by-url`

Fiche série complète.

Paramètres additionnels :
- `blocks` : sous-ensembles logiques ;
- `fields` : chemins ciblés ;
- `include_raw_sections` : inclure `raw_sections`.

Blocs série :
- `identity`
- `staff`
- `publishing`
- `presentation`
- `editions`
- `stats`
- `related`
- `raw`
- `raw_sections`

### 6) `GET /series/{slug}/related`
### 7) `GET /series/by-url/related`

Renvoie uniquement les liens liés (`related`).

### 8) `GET /series/{slug}/editions`
### 9) `GET /series/by-url/editions`

Paramètre :
- `edition` : `all`, `vf`, `vo`

Renvoie les listes d'éditions visibles sur Manga-News.

Important :
- cette route expose les **items d'édition** ;
- les compteurs globaux `vf` / `vo` viennent de la fiche série, pas de ce payload.

### 10) `GET /volume/{series_slug}/{volume_slug}`
### 11) `GET /volume/by-url`

Fiche volume complète.

La réponse volume inclut aussi `vf` / `vo` quand la série parente a pu être relue.

Concrètement :
- la page volume fournit l'identité du tome ;
- la fiche série parente fournit les compteurs globaux `vf` / `vo` ;
- ces compteurs sont extraits du bloc HTML `#numberblock` quand il est présent.

### 12) `GET /news/global`
### 13) `GET /news/series/{slug}`
### 14) `GET /news/volume/{series_slug}/{volume_slug}`
### 15) `GET /news/volume/by-url`

Listes de news normalisées.

### 16) `GET /planning`

Paramètres :
- `section` : `manga-vf`, `manga-vo`
- `year`, `month`, `page`
- `publisher`
- `q`
- `date_from`, `date_to`
- `sort` : `date_asc`, `date_desc`, `title_asc`, `title_desc`
- `limit`

Le filtre `q` est appliqué après normalisation, côté API.

## ETag

Chaque enveloppe métier expose :
- `ETag`
- `X-Data-Fingerprint`

Usage recommandé :
1. lire une première réponse ;
2. renvoyer ensuite `If-None-Match` ;
3. gérer `304 Not Modified`.

## Erreurs

Format actuel :

```json
{
  "code": "UPSTREAM_PARSE_ERROR",
  "detail": "..."
}
```

Codes principaux :
- `AUTH_REQUIRED`
- `RESOURCE_NOT_FOUND`
- `UPSTREAM_PARSE_ERROR`
- `UPSTREAM_FETCH_ERROR`

## Notes importantes sur le cache

L'API met les réponses en cache dans SQLite. Les payloads `series`, `volume`, `search` et `search/resolve` dépendent d'une version interne de clé de cache.

Conséquence utile :
- après un changement de parseur ou d'enrichissement, l'application ne réutilise pas les anciennes entrées de cache incompatibles ;
- si tu veux néanmoins repartir immédiatement d'un état vierge, supprime le fichier `DB_PATH` ou son contenu.

## Recommandations client

- consomme uniquement les routes présentes dans `/openapi.json` ;
- conserve et rejoue les `ETag` ;
- gère explicitement `401`, `404`, `502` ;
- exploite `score` sur `/search` et `confidence` sur `/search/resolve` si la similarité de titre est importante ;
- ne traite pas `UPSTREAM_PARSE_ERROR` comme une absence définitive de donnée.
