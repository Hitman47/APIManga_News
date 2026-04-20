# Cas d'usage et recettes

Ce document donne des workflows concrets, sans théorie inutile.

## 1. Trouver une série à partir d'un titre libre

Objectif : l'utilisateur tape `one piece`, tu veux une fiche série.

```bash
curl --get "http://localhost:8017/search/resolve"   --data-urlencode "q=one piece"   --data-urlencode "kind=series"
```

Puis :

```bash
curl "http://localhost:8017/series/One-piece-Edition-originale"
```

Payloads d'appui :
- [`examples/search_resolve_series_one_piece.json`](examples/search_resolve_series_one_piece.json)
- [`examples/series_one_piece.json`](examples/series_one_piece.json)

## 2. Trouver un volume précis

Objectif : récupérer les infos du tome 110.

```bash
curl --get "http://localhost:8017/search/resolve"   --data-urlencode "q=one piece tome 110"   --data-urlencode "kind=volume"
```

Puis :

```bash
curl "http://localhost:8017/volume/One-Piece/vol-110"
```

Payload d'appui : [`examples/volume_one_piece_110.json`](examples/volume_one_piece_110.json)

## 3. Charger une fiche minimale pour une UI légère

Exemple série :

```bash
curl --get "http://localhost:8017/series/One-piece-Edition-originale"   --data-urlencode "fields=title,cover_image,vf.volumes,next_release_date"
```

Exemple volume :

```bash
curl --get "http://localhost:8017/volume/One-Piece/vol-110"   --data-urlencode "fields=title,publication_date,isbn_ean,cover_image"
```

## 4. Afficher les éditions VF / VO d'une série

```bash
curl "http://localhost:8017/series/One-piece-Edition-originale/editions?edition=all"
```

Payload d'appui : [`examples/series_editions_one_piece_all.json`](examples/series_editions_one_piece_all.json)

## 5. Construire une page “news liées à la série”

```bash
curl "http://localhost:8017/news/series/One-piece-Edition-originale?limit=20"
```

Pour une intégration plus simple, commence souvent par le flux global :
- [`examples/news_global_one_piece_sample.json`](examples/news_global_one_piece_sample.json)

## 6. Construire une page “sorties du mois”

```bash
curl --get "http://localhost:8017/planning"   --data-urlencode "section=manga-vf"   --data-urlencode "year=2026"   --data-urlencode "month=4"   --data-urlencode "sort=date_asc"   --data-urlencode "limit=100"
```

Payload d'appui : [`examples/planning_manga_vf_april_2026.json`](examples/planning_manga_vf_april_2026.json)

## 7. Éviter de télécharger la même chose en boucle

Premier appel :

```bash
curl -i "http://localhost:8017/series/One-piece-Edition-originale"
```

Deuxième appel :

```bash
curl -i "http://localhost:8017/series/One-piece-Edition-originale"   -H 'If-None-Match: "<fingerprint>"'
```

Si tu obtiens `304`, tu gardes ta copie locale.

## 8. Cas d'usage spécial : donner la doc à une autre IA

Ordre recommandé :
1. README ;
2. API integration ;
3. OpenAPI ;
4. 3 ou 4 JSON de `docs/examples/` ;
5. seulement ensuite les appels réels.

Cette approche limite fortement les hallucinations de routes ou de champs.

## 9. Mauvaises pratiques à éviter

### Mauvaise pratique 1

Utiliser `/search` avec `mode=all` pour tous les appels automatisés, alors que tu veux juste un meilleur résultat.

Mieux : `/search/resolve`.

### Mauvaise pratique 2

Tirer tout le payload série alors que ton écran n'utilise que `title` et `cover_image`.

Mieux : `fields=title,cover_image`.

### Mauvaise pratique 3

Supposer qu'un champ sera toujours rempli.

Mieux : traiter tous les champs comme potentiellement absents ou `null`.

### Mauvaise pratique 4

Documenter ou coder des routes absentes de `/openapi.json`.

Mieux : toujours repartir de l'OpenAPI réelle.
