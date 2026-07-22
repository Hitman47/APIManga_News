# Parsing des métadonnées Manga-News

Ce document décrit le fonctionnement complet du parseur des métadonnées de fiches série et volume.

## Périmètre

Le mécanisme alimente notamment :

- `title_vo` et `translated_title` ;
- `authors_story`, `authors_art` et `translators` ;
- `publisher_fr`, `publisher_vo` et `collection` ;
- `type`, `genres`, `prepublication` et `origin` ;
- les informations propres aux volumes comme `publication_date`, `isbn_ean` et `price_code`.

Il est utilisé par les fiches détaillées et par les métadonnées servant à enrichir les recherches.

## Structure HTML actuelle

Manga-News sépare maintenant le libellé, le séparateur et les valeurs dans plusieurs nœuds HTML :

```html
<li class="book-genre">
  <strong>Genre</strong>:
  <a>Drame</a>,
  <a>Tranche-de-vie</a>
</li>
```

Une lecture globale du texte transforme cette structure en plusieurs lignes indépendantes. Le parseur ne peut donc pas supposer que `Genre` et sa valeur se trouvent sur la même ligne.

## Ordre d’extraction

### 1. Index DOM prioritaire

Le parseur parcourt une seule fois les libellés structurés portés par `strong`, `dt` ou `th`.

Pour chaque libellé reconnu exactement, il récupère la valeur dans le même bloc logique :

- le même `li` pour la structure Manga-News actuelle ;
- la même ligne `tr` pour une structure tabulaire ;
- le `dd` suivant pour une liste `dt` / `dd`.

Les valeurs multiples restent séparées par leurs virgules puis sont normalisées par le modèle métier. Ainsi, `Drame, Tranche-de-vie` produit bien :

```json
["Drame", "Tranche-de-vie"]
```

### 2. Fallback texte legacy

Si aucun bloc DOM structuré n’est disponible, le parseur conserve la compatibilité avec l’ancien format :

```text
Type: Shonen
Genre: Aventure, Fantastique
```

Le libellé doit respecter une frontière exacte. `Genre` peut donc reconnaître `Genre: Drame`, mais ne reconnaît plus `Genres Manga`.

Les valeurs non latines sont préservées : le séparateur `:` est analysé avant la normalisation utilisée pour les comparaisons.

## Effet sur les sections libres

La même règle de frontière stricte sert à détecter la fin des sections comme `Résumé` ou `Thèmes`. Un titre de navigation tel que `Genres Manga` n’est plus pris pour le champ `Genre` et ne tronque plus une section par simple préfixe.

## Cache après une évolution du parseur

Le cache distingue deux couches :

1. le HTML Manga-News téléchargé ;
2. le JSON métier produit par le parseur.

Une révision dédiée est intégrée aux clés des résultats parsés `series`, `volume`, `series-search-meta`, `volume-search-meta` et des recherches agrégées.

Lors d’une mise à jour du parseur :

- les anciens JSON parsés ne sont plus relus ;
- le HTML encore frais reste utilisable ;
- la première requête reparse ce HTML localement sans nécessairement appeler Manga-News ;
- les actualités, le planning et les autres caches indépendants ne sont pas vidés.

Un redémarrage avec la nouvelle image Docker suffit. Il n’est pas nécessaire de supprimer `cache.sqlite3` pour cette correction.

## Exemple Blue Giant Momentum

```http
GET /series/Blue-Giant-Momentum?fields=title,type,genres
```

Résultat métier attendu dans `data` :

```json
{
  "title": "Blue Giant Momentum",
  "type": "Seinen",
  "genres": ["Drame", "Tranche-de-vie"]
}
```

Le premier appel après déploiement peut indiquer `cached=false` parce que le JSON vient d’être recalculé. Les appels suivants utilisent le nouveau cache et indiquent normalement `cached=true`.

## Couverture de tests

Les tests automatisés couvrent :

- la structure DOM actuelle de Blue Giant Momentum ;
- la collision historique avec `Genres Manga` ;
- les métadonnées série et volume ;
- les recherches enrichies ;
- l’ancien format sur une seule ligne ;
- les titres VO non latins ;
- la réutilisation du HTML frais après changement de version du parseur.
