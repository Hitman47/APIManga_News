# Use Cases and Recipes

## 1. Trouver la bonne série à partir d'un titre local

```bash
curl --get "http://localhost:8017/search/resolve" \
  --data-urlencode "q=Dogs - Bullets & Carnage" \
  --data-urlencode "kind=series"
```

Pourquoi ça marche : la recherche est tolérante à la ponctuation et aux espaces.

## 2. Trouver un volume précis à partir d'un titre libre

```bash
curl --get "http://localhost:8017/search/resolve" \
  --data-urlencode "q=one piece tome 91" \
  --data-urlencode "kind=volume"
```

## 3. Récupérer une fiche série complète

```bash
curl "http://localhost:8017/series/One-piece-Edition-originale"
```

## 4. Récupérer seulement une partie d'une fiche série

```bash
curl --get "http://localhost:8017/series/One-piece-Edition-originale" \
  --data-urlencode "blocks=editions,stats" \
  --data-urlencode "fields=title,vf.volumes"
```

## 5. Récupérer une fiche volume complète

```bash
curl "http://localhost:8017/volume/One-Piece/vol-91"
```

## 6. Vérifier les compteurs VF/VO sur une recherche volume

```bash
curl --get "http://localhost:8017/search" \
  --data-urlencode "q=Dogs: Bullets & Carnage" \
  --data-urlencode "kind=volume" \
  --data-urlencode "mode=best" \
  --data-urlencode "limit=10"
```

À vérifier dans la réponse :
- `title_vo`
- `translated_title`
- `vf`
- `vo`

## 7. Lire les news globales

```bash
curl "http://localhost:8017/news/global?limit=10"
```

## 8. Lire le planning VF d'un mois

```bash
curl --get "http://localhost:8017/planning" \
  --data-urlencode "section=manga-vf" \
  --data-urlencode "year=2026" \
  --data-urlencode "month=4" \
  --data-urlencode "publisher=Glénat"
```

## 9. Utiliser ETag correctement

### Premier appel

```bash
curl -i "http://localhost:8017/series/One-piece-Edition-originale"
```

### Appel conditionnel

```bash
curl -i "http://localhost:8017/series/One-piece-Edition-originale" \
  -H 'If-None-Match: "<etag_précédent>"'
```

## Mauvaises pratiques à éviter

- coder `/v1/...` alors que le contrat réel est sans version ;
- inventer des routes admin ;
- supposer un champ toujours présent ;
- ignorer `score` et `confidence` lors de la résolution ;
- oublier que `vf` / `vo` sur un volume dépendent de la lecture de la série parente.
