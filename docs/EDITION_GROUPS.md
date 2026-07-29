# Groupes d'editions VF

Cette fonctionnalite distingue les editions d'une meme serie sans modifier les
reponses historiques de `/search`, `/series/{slug}`, `/series/{slug}/editions`
ou `/volume/{series_slug}/{volume_slug}`.

## Obtenir les editions d'une serie connue

```http
GET /series/Eden/edition-groups
```

La reponse compacte contient un groupe par section de la page Manga-News :

```json
{
  "title": "Eden",
  "series_slug": "Eden",
  "groups": [
    {
      "edition_label": "edition_originale",
      "display_name": "Edition originale",
      "series_slug": "Eden",
      "volume_count": 18,
      "total_volumes": 18,
      "highest_volume_number": 18,
      "status": "completed",
      "status_source": "explicit",
      "status_confidence": "high",
      "items": []
    },
    {
      "edition_label": "perfect",
      "display_name": "Edition Perfect",
      "series_slug": "Eden-Perfect-Edition",
      "volume_count": 9,
      "total_volumes": 9,
      "highest_volume_number": 9,
      "status": "completed",
      "status_source": "inferred",
      "status_confidence": "medium",
      "items": []
    }
  ]
}
```

Ajouter `include_volumes=true` remplit `items`. Cela ne declenche pas d'appel
Manga-News supplementaire : le parse complet est mis en cache, puis la reponse
compacte masque seulement les items.

## Rechercher puis analyser

```http
GET /search/editions?q=eden&mode=best&include_volumes=false
```

- `mode=best` analyse seulement la meilleure serie et reste le mode recommande ;
- `mode=all` analyse jusqu'a `limit` series ;
- `limit` vaut 10 par defaut et ne peut pas depasser 50 ;
- `include_volumes=false` conserve une petite reponse.

En `mode=all`, une serie dont la page d'editions ne peut pas etre analysee est
ignoree avec `partial=true` et un avertissement; les autres resultats restent
disponibles.

Cette route est distincte de `/search`. Le sens de l'ancien parametre
`include_editions`, qui hydrate uniquement les compteurs globaux `vf` et `vo`,
reste inchange.

## Sens des compteurs

- `volume_count` : nombre d'URL de tomes distinctes listees dans la section ;
- `highest_volume_number` : plus grand numero entier observe ;
- `available_numbers` : numeros entiers reellement observes ;
- `total_volumes` : total renseigne uniquement quand `status=completed`.

Pour une edition en cours ou indeterminable, `volume_count` reste exploitable,
mais `total_volumes` vaut `null`. L'API ne transforme donc pas un simple nombre
de tomes actuellement publies en total final certain.

## Statut et provenance

Valeurs de `status` : `completed`, `ongoing`, `unknown`.

Valeurs de `status_source` :

- `explicit` : Manga-News publie le statut dans les donnees de la page ;
- `inferred` : l'API applique une deduction documentee ;
- `unknown` : aucun statut suffisamment defendable.

`status_confidence` vaut `high`, `medium`, `low` ou `none`. `status_reason`
explique la source ou la deduction. Pour Eden Perfect, le statut est infere a
partir de l'edition originale terminee de 18 tomes et du ratio exact 2:1 avec
les 9 tomes Perfect. Ce n'est pas presente comme une declaration explicite de
Manga-News.

Une inference de fin n'est appliquee qu'aux editions compilees connues
(`perfect`, `deluxe`, `ultimate`, `kanzenban`, `double`, `triple`,
`grand_format`), lorsque l'edition originale est explicitement terminee et que
le ratio observe vaut exactement 2:1 ou 3:1. Sinon, le statut reste `unknown`.

## Selectionner une edition par numero

Le parametre facultatif `edition_label` est ajoute a la route existante :

```http
GET /volume/Eden/number/1?edition_label=perfect
```

Il selectionne ici `/manga/Eden-Perfect-Edition/vol-1`. Sans
`edition_label`, la route suit exactement son algorithme historique.

Le meme filtre est disponible pour les dates de sortie :

```http
GET /series/Eden/release-state?edition_label=perfect
```

La qualite de ce resultat depend de la presence de dates de publication dans
les cartes de l'edition. Le statut global du groupe et le calcul dernier/prochain
tome sont deux informations distinctes.

## Parsing et performances

Le parseur cherche chaque `.boxedTitleWrapper`, lit son titre, puis n'analyse
que le `.boxedContent` immediatement associe. Les recommandations et tendances
situees ailleurs sur la page sont ignorees. Les URL sont dedupliquees avant le
calcul des compteurs.

Pour un slug connu, un cache froid demande une page Editions VF. Une recherche
ajoute les pages de recherche, puis une page Editions VF par serie retenue. Les
requetes identiques chaudes sont servies depuis le cache SQLite.
