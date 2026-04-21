# Cas d'usage et recettes

Des recettes courtes, concrètes et alignées avec le contrat réel.

## 1. Recherche simple d'une série

```bash
curl --get "http://localhost:8017/search" \
  --data-urlencode "q=one piece" \
  --data-urlencode "kind=series" \
  --data-urlencode "mode=all" \
  --data-urlencode "limit=5"
```

À lire dans la réponse :
- `data[].title`
- `data[].slug`
- `data[].score`
- `data[].title_vo`
- `data[].translated_title`
- `data[].vf.volumes` et `data[].vo.volumes` pour les résultats de type `series` quand ces compteurs sont disponibles

## 2. Résoudre directement le meilleur candidat

```bash
curl --get "http://localhost:8017/search/resolve" \
  --data-urlencode "q=one piece tome 110" \
  --data-urlencode "kind=volume" \
  --data-urlencode "limit=10"
```

À lire :
- `data.best.series_slug`
- `data.best.volume_slug`
- `data.best.score`
- `data.best.vf` / `data.best.vo` si le meilleur candidat est une série
- `data.confidence`

## 3. Charger une fiche série complète

```bash
curl "http://localhost:8017/series/One-piece-Edition-originale"
```

Champs utiles :
- `title`
- `title_vo`
- `translated_title`
- `publisher_fr`
- `vf`
- `vo`
- `stats`

## 4. Charger une fiche série légère

```bash
curl --get "http://localhost:8017/series/One-piece-Edition-originale" \
  --data-urlencode "fields=title,title_vo,translated_title,cover_image,vf.volumes,next_release_date"
```

## 5. Charger une fiche volume complète

```bash
curl "http://localhost:8017/volume/One-Piece/vol-110"
```

Champs utiles :
- `title`
- `number`
- `number_int`
- `edition_label`
- `is_special`
- `is_one_shot`
- `publication_date`
- `isbn_ean`
- `title_vo`
- `translated_title`

## 6. Charger une fiche volume légère

```bash
curl --get "http://localhost:8017/volume/One-Piece/vol-110" \
  --data-urlencode "blocks=identity,release" \
  --data-urlencode "fields=cover_image"
```

## 7. Utiliser une URL Manga News directe

### Série

```bash
curl --get "http://localhost:8017/series/by-url" \
  --data-urlencode "url=https://www.manga-news.com/index.php/serie/One-piece-Edition-originale"
```

### Volume

```bash
curl --get "http://localhost:8017/volume/by-url" \
  --data-urlencode "url=https://www.manga-news.com/index.php/manga/One-Piece/vol-110"
```

### News volume by-url

```bash
curl --get "http://localhost:8017/news/volume/by-url" \
  --data-urlencode "url=https://www.manga-news.com/index.php/manga/One-Piece/vol-110" \
  --data-urlencode "limit=10"
```

## 8. Récupérer les liens liés à une série

```bash
curl "http://localhost:8017/series/One-piece-Edition-originale/related"
```

## 9. Lister les éditions VF / VO d'une série

```bash
curl "http://localhost:8017/series/One-piece-Edition-originale/editions?edition=all"
```

## 10. Lire les news globales

```bash
curl "http://localhost:8017/news/global?limit=5"
```

## 11. Lire les news d'une série

```bash
curl "http://localhost:8017/news/series/One-piece-Edition-originale?limit=10"
```

## 12. Lire le planning VF avec filtres

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

Rappel : `total_items` est calculé après filtrage local sur la page chargée.

## 13. Éviter de refetch la même fiche

Premier appel :

```bash
curl -i "http://localhost:8017/series/One-piece-Edition-originale"
```

Deuxième appel avec ETag :

```bash
curl -i "http://localhost:8017/series/One-piece-Edition-originale" \
  -H 'If-None-Match: "<fingerprint>"'
```

## 14. Exploiter les titres alternatifs

Cas pratique : afficher à la fois le titre principal, le titre VO et le titre traduit quand ils existent.

```bash
curl --get "http://localhost:8017/search" \
  --data-urlencode "q=black night parade" \
  --data-urlencode "kind=series" \
  --data-urlencode "mode=all"
```

Puis afficher :
- `title`
- `title_vo`
- `translated_title`

## 15. Vérifier la tolérance aux variantes de ponctuation

```bash
curl --get "http://localhost:8017/search" \
  --data-urlencode "q=Dogs - Bullets & Carnage" \
  --data-urlencode "kind=series" \
  --data-urlencode "mode=all" \
  --data-urlencode "limit=10"
```

Attendu :
- le bon résultat remonte malgré `:` vs `-` ;
- `score` reste élevé ;
- `/search/resolve` doit généralement produire `confidence=medium` ou `high`.

## 16. Débugger un parse upstream cassé

Active dans l'environnement :

```env
DEBUG_CAPTURE_HTML_ON_ERROR=true
DEBUG_HTML_DUMP_DIR=/tmp/manga-news-debug-html
```

Puis rejoue la requête qui casse. Le détail de l'erreur peut inclure :

```text
Debug HTML saved to /tmp/manga-news-debug-html/...
```

## 17. Mauvaises pratiques à éviter

### Mauvaise pratique 1
Supposer que `title_vo` ou `translated_title` seront toujours présents.

### Mauvaise pratique 2
Supposer que `search/resolve` renvoie toujours un `best`.

### Mauvaise pratique 3
Supposer que `planning.total_items` représente tout Manga News.

### Mauvaise pratique 4
Coder `/v1/...` alors que le contrat réel est sans version.

### Mauvaise pratique 5
Traiter `partial=true` comme une donnée fraîche.

### Mauvaise pratique 6
Inventer une route admin ou `lookup/volume` parce qu'une vieille doc en parlait.

## 18. Vérifier les compteurs VF / VO directement depuis la recherche

```bash
curl --get "http://localhost:8017/search" \
  --data-urlencode "q=Dogs - Bullets & Carnage" \
  --data-urlencode "kind=series" \
  --data-urlencode "mode=all" \
  --data-urlencode "limit=10"
```

À lire dans la réponse :
- `data[0].title`
- `data[0].score`
- `data[0].vf.volumes` et `data[0].vf.status`
- `data[0].vo.volumes` et `data[0].vo.status`

Exemple d'usage UI : afficher directement `VF 9 / VO 10` dans une liste de résultats sans charger tout de suite `/series/{slug}`.
