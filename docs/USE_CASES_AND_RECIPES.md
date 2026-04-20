# Cas d'usage et recettes

Ce document donne des workflows concrets, sans théorie inutile.

## 1. Trouver une série à partir d'un titre libre

Objectif : l'utilisateur tape `one piece`, tu veux une fiche série.

```bash
curl --get "http://localhost:8017/search/resolve" \
  --data-urlencode "q=one piece" \
  --data-urlencode "kind=series"
```

Puis :

```bash
curl "http://localhost:8017/series/One-piece-Edition-originale"
```

## 2. Trouver un volume précis

Objectif : récupérer les infos du tome 110.

```bash
curl --get "http://localhost:8017/search/resolve" \
  --data-urlencode "q=one piece tome 110" \
  --data-urlencode "kind=volume"
```

Puis :

```bash
curl "http://localhost:8017/volume/One-Piece/vol-110"
```

## 3. Charger une fiche minimale pour une UI légère

Exemple série :

```bash
curl --get "http://localhost:8017/series/One-piece-Edition-originale" \
  --data-urlencode "fields=title,cover_image,vf.volumes,next_release_date"
```

Exemple volume :

```bash
curl --get "http://localhost:8017/volume/One-Piece/vol-110" \
  --data-urlencode "fields=title,publication_date,isbn_ean,cover_image"
```

## 4. Afficher les éditions VF / VO d'une série

```bash
curl "http://localhost:8017/series/One-piece-Edition-originale/editions?edition=all"
```

## 5. Construire une page “news liées à la série”

```bash
curl "http://localhost:8017/news/series/One-piece-Edition-originale?limit=20"
```

## 6. Construire une page “sorties du mois”

```bash
curl --get "http://localhost:8017/planning" \
  --data-urlencode "section=manga-vf" \
  --data-urlencode "year=2026" \
  --data-urlencode "month=4" \
  --data-urlencode "sort=date_asc" \
  --data-urlencode "limit=100"
```

## 7. Éviter de télécharger la même chose en boucle

Premier appel :

```bash
curl -i "http://localhost:8017/series/One-piece-Edition-originale"
```

Deuxième appel :

```bash
curl -i "http://localhost:8017/series/One-piece-Edition-originale" \
  -H 'If-None-Match: "<fingerprint>"'
```

Si tu obtiens `304`, tu gardes ta copie locale.

## 8. Mauvaises pratiques à éviter

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
