# Use Cases and Recipes

## 1. Résoudre rapidement une série

```bash
curl --get "http://localhost:8017/search/resolve" \
  --data-urlencode "q=Dogs - Bullets & Carnage" \
  --data-urlencode "kind=series"
```

## 2. Trouver un volume précis à partir d'un titre libre

```bash
curl --get "http://localhost:8017/search/resolve" \
  --data-urlencode "q=one piece tome 91" \
  --data-urlencode "kind=volume"
```

## 3. Lire uniquement quelques champs d'une fiche série

```bash
curl --get "http://localhost:8017/series/One-piece-Edition-originale" \
  --data-urlencode "fields=title,vf.volumes,vo.volumes"
```

## 4. Lire une fiche volume complète

```bash
curl "http://localhost:8017/volume/One-Piece/vol-91"
```

## 5. Vérifier les compteurs VF/VO sur une recherche volume

```bash
curl --get "http://localhost:8017/search" \
  --data-urlencode "q=Dogs: Bullets & Carnage" \
  --data-urlencode "kind=volume" \
  --data-urlencode "mode=best"
```

Champs attendus sur le meilleur résultat :
- `title_vo`
- `translated_title`
- `vf`
- `vo`

## 6. Lire les éditions VF/VO d'une série

```bash
curl --get "http://localhost:8017/series/One-piece-Edition-originale/editions" \
  --data-urlencode "edition=all"
```

## 7. Lire le planning VF filtré

```bash
curl --get "http://localhost:8017/planning" \
  --data-urlencode "section=manga-vf" \
  --data-urlencode "publisher=Glénat" \
  --data-urlencode "q=one piece" \
  --data-urlencode "sort=date_desc"
```

## 8. Débugger un `vf` / `vo` inattendu à `null`

1. Lire la fiche série correspondante (`/series/{slug}`).
2. Vérifier si la réponse est `cached: true`.
3. Si oui et que tu viens de déployer une nouvelle version, redémarrer l'app ou supprimer le fichier SQLite de cache.
4. Vérifier sur la page Manga-News que le bloc `#numberblock` expose encore les compteurs.
