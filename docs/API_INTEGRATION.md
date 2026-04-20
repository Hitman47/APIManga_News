# API Manga News — Guide d'intégration détaillé

Ce document décrit le contrat d'intégration de l'API pour qu'un autre projet, un autre développeur ou une autre IA puisse la brancher sans relire le code source.

## 1. Usage visé

Cette API est conçue comme **service interne** entre applications. Le cas d'usage typique est :

- un autre conteneur veut obtenir des informations structurées à partir de Manga News ;
- il ne doit pas scraper le HTML lui-même ;
- il doit pouvoir éviter les retraitements inutiles grâce au cache et à `ETag`.

## 2. Base URL

Choisir l'URL selon le contexte d'appel.

### Depuis l'hôte

- `http://localhost:8017`

### Depuis un autre conteneur Docker sur le même réseau Compose

- `http://manga-news-api:8000`

Ne pas utiliser `localhost:8017` depuis un autre conteneur : `localhost` pointerait vers ce conteneur lui-même.

## 3. Authentification

Authentification Bearer **optionnelle**.

### Cas 1 — `API_TOKEN` absent ou vide

Aucun header n'est nécessaire.

### Cas 2 — `API_TOKEN` défini

Tous les appels doivent envoyer :

```http
Authorization: Bearer <TOKEN>
```

Un client doit donc être capable de fonctionner avec ou sans Bearer selon sa configuration.

## 4. Contrat d'enveloppe global

Tous les endpoints métier renvoient la même enveloppe JSON de haut niveau.

```json
{
  "ok": true,
  "found": true,
  "source": "manga_news",
  "source_url": "https://www.manga-news.com/...",
  "cached": true,
  "fetched_at": "2026-04-20T12:00:00+00:00",
  "cache_expires_at": "2026-04-21T12:00:00+00:00",
  "partial": false,
  "warnings": [],
  "schema_version": "1.0",
  "fingerprint": "<sha256>",
  "data": {}
}
```

### Signification

- `ok`: succès logique ;
- `found`: indique si la ressource ou la liste contient un résultat exploitable ;
- `source`: toujours `manga_news` ;
- `source_url`: URL upstream réellement utilisée ;
- `cached`: réponse issue du cache SQLite ;
- `fetched_at`: date du snapshot renvoyé ;
- `cache_expires_at`: date de fin de fraîcheur ;
- `partial`: vrai si la réponse a été servie depuis un cache périmé après erreur upstream ;
- `warnings`: liste de messages d'avertissement ;
- `schema_version`: version de contrat ;
- `fingerprint`: hash stable du champ `data` ;
- `data`: charge utile métier.

## 5. ETag et cache HTTP côté client

Chaque endpoint métier renvoie deux headers :

- `ETag: "<fingerprint>"`
- `X-Data-Fingerprint: <fingerprint>`

### Règle d'intégration recommandée

Lors d'un premier appel :

1. stocker la réponse JSON ;
2. stocker `ETag`.

Lors d'un appel suivant sur la même ressource :

```http
If-None-Match: "<etag précédent>"
```

### Comportement attendu

- si les données ont changé : `200 OK` + nouveau JSON ;
- si les données n'ont pas changé : `304 Not Modified` + pas de corps.

Pour un autre projet, c'est la meilleure façon d'éviter de retraiter la même fiche série, volume ou planning.

## 6. Endpoints disponibles

## 6.1 `GET /health`

Usage : disponibilité simple.

Réponse :

```json
{"ok": true}
```

Ne pas attendre l'enveloppe standard ici.

---

## 6.2 `GET /search`

Recherche des séries et/ou des volumes.

### Paramètres

- `q` obligatoire : texte recherché ;
- `kind`: `series`, `volume`, `all` ; défaut `all` ;
- `mode`: `best`, `all` ; défaut `best` ;
- `limit`: 1 à 50 ; défaut `10`.

### Réponse `data`

Liste de résultats.

```json
[
  {
    "title": "One Piece",
    "url": "https://www.manga-news.com/index.php/serie/One-piece-Edition-originale",
    "kind": "series",
    "score": 97,
    "slug": "One-piece-Edition-originale",
    "series_slug": "One-piece-Edition-originale",
    "volume_slug": null
  }
]
```

### Quand utiliser `/search`

Utiliser `/search` si le client veut :

- afficher plusieurs résultats ;
- proposer un choix utilisateur ;
- conserver plusieurs candidats.

---

## 6.3 `GET /search/resolve`

Résout directement le meilleur match exploitable pour une requête.

### Paramètres

- `q` obligatoire ;
- `kind`: `series`, `volume`, `all` ; défaut `series` ;
- `limit`: 1 à 20 ; défaut `5`.

### Réponse `data`

```json
{
  "query": "one piece",
  "kind": "series",
  "confidence": "high",
  "result": {
    "title": "One Piece",
    "url": "https://www.manga-news.com/index.php/serie/One-piece-Edition-originale",
    "kind": "series",
    "score": 98,
    "slug": "One-piece-Edition-originale",
    "series_slug": "One-piece-Edition-originale",
    "volume_slug": null
  },
  "candidates": []
}
```

### Sens des champs

- `confidence`: niveau de confiance du meilleur match (`high`, `medium`, `low`, `none`) ;
- `result`: meilleur candidat ;
- `candidates`: autres candidats éventuels.

### Quand utiliser `/search/resolve`

C'est l'endpoint recommandé pour une intégration automatisée. Le pattern conseillé est :

1. appeler `/search/resolve` ;
2. lire `data.result.kind` ;
3. si `series`, appeler `/series/{slug}` ;
4. si `volume`, appeler `/volume/{series_slug}/{volume_slug}`.

---

## 6.4 `GET /series/{slug}`

Retourne la fiche d'une série Manga News.

### Exemple

```http
GET /series/One-piece-Edition-originale
```

## 6.5 `GET /series/by-url`

Même donnée, mais à partir d'une URL complète Manga News.

### Paramètre

- `url` obligatoire

### Réponse `data`

```json
{
  "title": "One Piece",
  "title_vo": "ワンピース",
  "translated_title": null,
  "summary": "...",
  "authors_story": ["Eiichiro Oda"],
  "authors_art": ["Eiichiro Oda"],
  "translators": [],
  "publisher_fr": "Glénat",
  "publisher_vo": "Shueisha",
  "collection": "Shonen",
  "type": "Shonen",
  "genres": ["Aventure", "Action"],
  "prepublication": "Weekly Shonen Jump",
  "origin": "Japon",
  "illustration": "n&b + couleurs",
  "advisory_age": "8+",
  "cover_image": "https://...jpg",
  "vf": {
    "volumes": 112,
    "status": "En cours"
  },
  "vo": {
    "volumes": 114,
    "status": "En cours"
  },
  "last_release_date": "2026-04-08",
  "next_release_date": "2026-05-06",
  "stats": {
    "likes": 531,
    "in_collection": 7053,
    "in_wishlist": 984,
    "marketplace": 2,
    "editorial_score": 16.23,
    "reader_score": 16.5
  },
  "themes": ["Série manga incontournable", "aventure fantastique pirates"],
  "strengths": "Un énorme succès populaire.",
  "source_url": "https://www.manga-news.com/index.php/serie/One-piece-Edition-originale"
}
```

### Notes d'intégration

- `vf` et `vo` peuvent être absents (`null`) ;
- certains champs textuels peuvent être `null` selon la fiche upstream ;
- un client robuste doit accepter les valeurs manquantes.

---

## 6.6 `GET /volume/{series_slug}/{volume_slug}`

Retourne une fiche volume.

## 6.7 `GET /volume/by-url`

Même donnée, mais à partir d'une URL complète.

### Réponse `data`

```json
{
  "title": "One Piece Vol.110",
  "series_title": "One Piece",
  "title_vo": "ワンピース",
  "translated_title": "One Piece",
  "summary": "...",
  "authors_story": ["Eiichiro Oda"],
  "authors_art": ["Eiichiro Oda"],
  "translators": ["Djamel RABAHI", "Julien FAVEREAU"],
  "publisher_fr": "Glénat",
  "publisher_vo": "Shueisha",
  "collection": "Shonen",
  "type": "Shonen",
  "genres": ["Aventure", "Fantastique"],
  "prepublication": "Shonen Jump",
  "origin": "Japon - 1997",
  "illustration": "208 pages n&b + couleurs",
  "advisory_age": "8+",
  "publication_date": "2025-09-27",
  "isbn_ean": "9782344064092",
  "price_code": "7.20",
  "cover_image": "https://...jpg",
  "editorial_score": 16.0,
  "reader_score": 15.5,
  "source_url": "https://www.manga-news.com/index.php/manga/One-Piece/vol-110"
}
```

---

## 6.8 `GET /news/global`

Retourne les dernières news globales via le flux RSS.

### Paramètre

- `limit`: 1 à 50 ; défaut `10`

### Réponse `data`

Liste de news :

```json
[
  {
    "title": "Titre news",
    "url": "https://...",
    "published_at": "2026-03-10",
    "excerpt": "Résumé court",
    "comments": 0,
    "category": "Manga"
  }
]
```

---

## 6.9 `GET /news/series/{slug}`

Retourne les news liées à une série.

## 6.10 `GET /news/volume/{series_slug}/{volume_slug}`

Retourne les news liées à un volume.

## 6.11 `GET /news/volume/by-url`

Même logique mais à partir de l'URL volume.

---

## 6.12 `GET /planning`

Retourne le planning VF ou VO, avec filtres locaux.

### Paramètres

- `section`: `manga-vf` ou `manga-vo` ; défaut `manga-vf` ;
- `year`: année optionnelle ;
- `month`: mois optionnel ;
- `page`: entier ; défaut `1` ;
- `publisher`: filtre éditeur ;
- `q`: filtre texte ;
- `date_from`: borne basse ;
- `date_to`: borne haute ;
- `sort`: `date_asc`, `date_desc`, `title_asc`, `title_desc` ;
- `limit`: nombre max d'items après filtrage local.

### Réponse `data`

```json
{
  "section": "manga-vf",
  "year": 2026,
  "month": 4,
  "page": 1,
  "filters": {
    "publisher": "Glénat",
    "query": null,
    "date_from": "2026-04-01",
    "date_to": "2026-04-30"
  },
  "sort": "date_asc",
  "total_items": 1,
  "items": [
    {
      "title": "One Piece Vol.110",
      "url": "https://www.manga-news.com/index.php/manga/One-Piece/vol-110",
      "release_date": "2026-04-27",
      "authors": ["Eiichirô ODA"],
      "publisher": "Glénat",
      "summary": "Résumé",
      "featured": false,
      "series_slug": "One-Piece",
      "volume_slug": "vol-110"
    }
  ]
}
```

### Note importante

Le filtre est appliqué **localement après parsing** de la page récupérée sur Manga News. Ce n'est pas un moteur de recherche upstream.

## 7. Gestion des erreurs

### 401

Si `API_TOKEN` est configuré et absent/incorrect :

```json
{
  "detail": "Missing or invalid bearer token."
}
```

### 404

Ressource introuvable sur Manga News :

```json
{
  "detail": "Resource not found on Manga News."
}
```

### 502

Erreur d'upstream ou de parsing :

```json
{
  "detail": "..."
}
```

Un client doit donc distinguer au minimum :

- erreur d'auth ;
- ressource absente ;
- problème de parsing/upstream.

## 8. Stratégie d'intégration recommandée pour une autre IA

### Cas 1 — trouver une série et récupérer sa fiche

1. appeler `/search/resolve?q=<titre>&kind=series`
2. lire `data.result.slug`
3. appeler `/series/{slug}`
4. stocker `ETag`
5. aux appels suivants, envoyer `If-None-Match`

### Cas 2 — surveiller le planning d'un éditeur

1. appeler `/planning?section=manga-vf&publisher=<éditeur>&year=<année>&month=<mois>`
2. stocker `ETag`
3. renvoyer `If-None-Match` lors des rafraîchissements

### Cas 3 — partir d'une URL Manga News connue

- si URL série : `/series/by-url?url=...`
- si URL volume : `/volume/by-url?url=...`

## 9. Bloc prêt à donner à une autre IA

Tu peux donner ceci à une autre IA pour qu'elle intègre l'API dans un autre projet :

```text
Tu dois intégrer une API interne nommée Manga News Private API.

Règles d'intégration :
- Base URL : http://manga-news-api:8000 depuis Docker, ou http://localhost:8017 depuis l'hôte.
- Auth Bearer optionnelle : si un token est configuré, envoyer Authorization: Bearer <TOKEN>.
- Endpoints principaux :
  - GET /health
  - GET /search?q=...&kind=series|volume|all&mode=best|all&limit=N
  - GET /search/resolve?q=...&kind=series|volume|all&limit=N
  - GET /series/{slug}
  - GET /series/by-url?url=...
  - GET /volume/{series_slug}/{volume_slug}
  - GET /volume/by-url?url=...
  - GET /news/global?limit=N
  - GET /news/series/{slug}?limit=N
  - GET /news/volume/{series_slug}/{volume_slug}?limit=N
  - GET /news/volume/by-url?url=...&limit=N
  - GET /planning?section=manga-vf|manga-vo&year=YYYY&month=MM&page=1&publisher=...&q=...&date_from=YYYY-MM-DD&date_to=YYYY-MM-DD&sort=date_asc|date_desc|title_asc|title_desc&limit=N
- Tous les endpoints métier renvoient une enveloppe JSON avec : ok, found, source, source_url, cached, fetched_at, cache_expires_at, partial, warnings, schema_version, fingerprint, data.
- Le champ data dépend de l'endpoint.
- Toujours gérer les headers ETag et X-Data-Fingerprint.
- Si une réponse fournit ETag, le réutiliser dans If-None-Match sur les appels suivants.
- Si l'API répond 304, réutiliser le dernier JSON stocké côté client.
- Pour obtenir rapidement une fiche à partir d'un titre, utiliser /search/resolve avant /series/{slug} ou /volume/{series_slug}/{volume_slug}.
- Gérer les erreurs 401, 404 et 502 proprement.
```
