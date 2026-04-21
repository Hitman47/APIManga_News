# Guide d'intégration API

Ce document s'adresse à un développeur, un script d'intégration, un service backend ou une autre IA qui doit consommer l'API sans halluciner des routes ou des champs.

## 1. Base URL

Contrat public actuel : **sans préfixe `/v1`**.

Exemples :
- Docker : `http://manga-news-api:8000`
- machine hôte : `http://localhost:8017`
- LAN : `http://<host-ip>:8017`

Commence toujours par lire `/openapi.json` sur l'instance réelle que tu consommes.

## 2. Authentification

Si `API_TOKEN` est vide, les routes publiques sont accessibles sans header d'auth.

Si `API_TOKEN` est défini, toutes les routes publiques attendent :

```http
Authorization: Bearer <api-token>
```

En cas d'erreur :

```json
{
  "code": "AUTH_REQUIRED",
  "detail": "Missing or invalid bearer token."
}
```

## 3. Routes publiques réellement exposées

### Santé
- `GET /health`

### Recherche
- `GET /search`
- `GET /search/resolve`

### Série
- `GET /series/{slug}`
- `GET /series/by-url`
- `GET /series/{slug}/related`
- `GET /series/by-url/related`
- `GET /series/{slug}/editions`
- `GET /series/by-url/editions`

### Volume
- `GET /volume/{series_slug}/{volume_slug}`
- `GET /volume/by-url`

### News
- `GET /news/global`
- `GET /news/series/{slug}`
- `GET /news/volume/{series_slug}/{volume_slug}`
- `GET /news/volume/by-url`

### Planning
- `GET /planning`

## 4. Routes et features à ne pas inventer

Ne construis pas ton client en supposant l'existence de :
- un préfixe de version du type `v1`
- des routes admin publiques
- un endpoint de lookup volume dédié
- une pagination commune sur toutes les réponses
- des filtres dédiés `title_vo=` ou `translated_title=`

## 5. Enveloppe commune

Les routes métier renvoient une enveloppe de ce type :

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
  "fingerprint": "fp-example",
  "data": {}
}
```

### Conseils d'interprétation

- `found=false` ne signifie pas forcément une erreur HTTP ;
- `cached=true` signifie que la réponse vient du cache SQLite ;
- `partial=true` signifie qu'une réponse stale a été servie en fallback ;
- `warnings` contient des signaux utiles quand un fallback a été utilisé ;
- `fingerprint` est le meilleur identifiant pour l'invalidation conditionnelle côté client.

## 6. Headers réellement utiles

Headers publics disponibles aujourd'hui :
- `ETag`
- `X-Data-Fingerprint`

### Requête conditionnelle

```http
If-None-Match: "<fingerprint>"
```

### Cas attendu
- `200` si la représentation a changé ;
- `304` si le fingerprint courant est identique.

## 7. Erreurs stables

Format :

```json
{
  "code": "RESOURCE_NOT_FOUND",
  "detail": "Resource not found on Manga News."
}
```

Codes actuellement utilisés :
- `AUTH_REQUIRED`
- `RESOURCE_NOT_FOUND`
- `UPSTREAM_FETCH_ERROR`
- `UPSTREAM_PARSE_ERROR`

### Interprétation conseillée

- `AUTH_REQUIRED` : token absent ou invalide ;
- `RESOURCE_NOT_FOUND` : page introuvable sur Manga News ;
- `UPSTREAM_FETCH_ERROR` : HTTP/réseau/timeout/empty response côté upstream ;
- `UPSTREAM_PARSE_ERROR` : HTML obtenu, mais contrat non extrait de manière fiable.

## 8. Recherche : comportement réel

### `/search`

Paramètres :
- `q` : texte recherché ;
- `kind` : `series`, `volume`, `all` ;
- `mode` : `best`, `all` ;
- `limit` : nombre max de résultats après tri.

Le service :
1. interroge plusieurs pages de recherche Manga News selon `kind` ;
2. parse les résultats HTML ;
3. déduplique par URL ;
4. trie par `score` décroissant ;
5. enrichit les résultats retenus avec `title_vo`, `translated_title` et, pour les séries, `vf` / `vo` si la fiche détaillée peut être relue.

### `/search/resolve`

Le service :
1. appelle `/search` ;
2. choisit un meilleur candidat `best` ;
3. calcule `confidence` (`high`, `medium`, `low`, `none`).

### Champs importants dans les résultats

- `title`
- `url`
- `kind`
- `score`
- `slug`
- `series_slug`
- `volume_slug`
- `title_vo`
- `translated_title`
- `vf` *(uniquement pertinent pour un résultat de type `series`)*
- `vo` *(uniquement pertinent pour un résultat de type `series`)*

## 9. Matching tolérant et score

Le matching est volontairement tolérant aux variations mineures de ponctuation, d'accents, de casse et d'espaces.

Exemple réel :
- entrée locale : `Dogs - Bullets & Carnage`
- titre Manga News : `Dogs: Bullets & Carnage`

Le client doit utiliser :
- `score` pour mesurer la similarité sur 100 ;
- `confidence` sur `/search/resolve` pour une lecture plus grossière.

### Compteurs de tomes VF / VO dans la recherche

Quand un résultat de recherche est de type `series`, l'API tente de relire la fiche série correspondante pour enrichir le résultat avec :
- `vf.volumes` et `vf.status` ;
- `vo.volumes` et `vo.status`.

C'est utile pour des cas comme :
- vérifier rapidement si une série a une édition VO plus avancée que la VF ;
- afficher un badge `VF 9 / VO 10` directement dans une UI de recherche ;
- décider côté client s'il faut charger la fiche série complète ou non.

Ces champs ne sont pas garantis : si la fiche ne les expose pas clairement, ils peuvent rester à `null`.

### Cas d'usage conseillé

- `score` élevé + `confidence=high` : bon candidat pour résolution automatique ;
- `score` moyen : affiche une validation utilisateur si ton workflow est sensible ;
- `score` bas : évite les automatismes agressifs.

## 10. Fiches série

### Routes
- `GET /series/{slug}`
- `GET /series/by-url?url=...`

### Champs utiles courants
- `title`
- `title_vo`
- `translated_title`
- `vf` *(uniquement pertinent pour un résultat de type `series`)*
- `vo` *(uniquement pertinent pour un résultat de type `series`)*
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
- `raw_sections`

### Projections

#### `blocks=`
Blocs disponibles :
- `identity`
- `staff`
- `publishing`
- `presentation`
- `editions`
- `stats`
- `related`
- `raw`
- `raw_sections`
- `all`

#### `fields=`
Chemins précis, par exemple :
- `title`
- `title_vo`
- `vf.volumes`
- `stats.likes`
- `next_release_date`

#### `include_raw_sections=true`
Ajoute `raw_sections` même si le champ n'est pas demandé explicitement.

## 11. Liens liés à une série

Routes :
- `GET /series/{slug}/related`
- `GET /series/by-url/related?url=...`

Retour allégé centré sur :
- `title`
- `related.series`
- `related.volumes`
- `related.anime`
- `related.drama`
- `related.dossiers`
- `related.univers`
- `related.external`
- `related.misc`

## 12. Éditions d'une série

Routes :
- `GET /series/{slug}/editions?edition=all|vf|vo`
- `GET /series/by-url/editions?url=...&edition=all|vf|vo`

Retour centré sur :
- `title`
- `series_slug`
- `vf`
- `vo`

Chaque item d'édition peut inclure :
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

## 13. Fiches volume

Routes :
- `GET /volume/{series_slug}/{volume_slug}`
- `GET /volume/by-url?url=...`

### Champs utiles courants
- `title`
- `series_title`
- `number`
- `number_int`
- `edition_label`
- `is_special`
- `is_one_shot`
- `title_vo`
- `translated_title`
- `vf` *(uniquement pertinent pour un résultat de type `series`)*
- `vo` *(uniquement pertinent pour un résultat de type `series`)*
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
- `raw_sections`

### Projections volume

Blocs disponibles :
- `identity`
- `staff`
- `publishing`
- `presentation`
- `release`
- `scores`
- `related`
- `raw`
- `raw_sections`
- `all`

## 14. News

Routes :
- `GET /news/global?limit=10`
- `GET /news/series/{slug}?limit=10`
- `GET /news/volume/{series_slug}/{volume_slug}?limit=10`
- `GET /news/volume/by-url?url=...&limit=10`

Chaque item expose :
- `title`
- `url`
- `published_at`
- `excerpt`
- `comments`
- `category`

## 15. Planning

Route :
- `GET /planning`

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

### Point important

`total_items` correspond au nombre d'items **après filtrage local** sur la page chargée. Ce n'est pas un total global de tout Manga News.

## 16. Cas d'intégration recommandés

### Trouver une série puis charger la fiche
1. `GET /search/resolve?q=<titre>&kind=series`
2. lire `data.best.slug`
3. `GET /series/{slug}`

### Trouver un volume puis charger la fiche
1. `GET /search/resolve?q=<titre>&kind=volume`
2. lire `data.best.series_slug` et `data.best.volume_slug`
3. `GET /volume/{series_slug}/{volume_slug}`

### UI compacte
- charger d'abord `search/resolve` ;
- utiliser `blocks`/`fields` sur les fiches pour éviter des payloads trop lourds ;
- réutiliser `ETag` pour éviter de refetch sans raison.

## 17. Points de fragilité réels

- le HTML de Manga News peut changer ;
- `title_vo` et `translated_title` ne sont pas garantis ;
- une requête `search/resolve` peut renvoyer `best=null` ;
- le planning n'est pas une API exhaustive du site, mais un parsing d'une page donnée ;
- `partial=true` doit être traité comme une réponse dégradée, pas comme un succès frais classique.

## 18. Validation de contrat

Validation rapide locale :

```bash
python scripts/validate_contract_and_docs.py
pytest
```

Exemples JSON utiles :
- [`docs/examples/search_response_one_piece.json`](examples/search_response_one_piece.json)
- [`docs/examples/resolve_response_one_piece.json`](examples/resolve_response_one_piece.json)
- [`docs/examples/series_one_piece.json`](examples/series_one_piece.json)
- [`docs/examples/volume_one_piece_91.json`](examples/volume_one_piece_91.json)
- [`docs/examples/planning_example.json`](examples/planning_example.json)
