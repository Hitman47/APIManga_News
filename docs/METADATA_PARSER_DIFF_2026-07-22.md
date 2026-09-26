# Diff documentaire - parseur de métadonnées du 2026-07-22

Ce document résume uniquement les changements de cette livraison. La référence complète est dans [`METADATA_PARSING.md`](METADATA_PARSING.md).

## Contrat public

- aucune route ajoutée ou supprimée ;
- aucun paramètre modifié ;
- aucun champ ajouté ou retiré ;
- schéma OpenAPI inchangé.

## Avant

Le parseur cherchait un libellé par préfixe dans le texte aplati de toute la page.

Conséquences observées sur Blue Giant Momentum :

```json
{
  "title": "Blue Giant Momentum",
  "type": null,
  "genres": ["s Manga"]
}
```

- `Type` était rencontré sans sa valeur et produisait immédiatement `null` ;
- `Genre` reconnaissait à tort le texte de navigation `Genres Manga` ;
- les autres métadonnées structurées pouvaient également être perdues.

## Après

Le parseur lit prioritairement le bloc DOM portant un libellé exact et conserve un fallback strict pour l’ancien HTML.

```json
{
  "title": "Blue Giant Momentum",
  "type": "Seinen",
  "genres": ["Drame", "Tranche-de-vie"]
}
```

Changements internes :

- index DOM construit une seule fois par page ;
- reconnaissance exacte des libellés `strong`, `dt` et `th` ;
- prise en charge des valeurs réparties entre plusieurs liens ;
- frontière stricte dans le fallback texte ;
- préservation des valeurs non latines ;
- détection stricte des champs lors de l’extraction des sections libres.

## Cache

Avant, une invalidation par version globale aurait aussi rendu froids les caches HTML, actualités et planning.

Après, une révision dédiée invalide uniquement les résultats dépendants du parseur. Le HTML frais peut être reparsé localement, sans nouvel appel upstream.

## Tests ajoutés

- fixture de la structure HTML actuelle de Blue Giant Momentum ;
- test série `type` / `genres` et autres métadonnées ;
- test des métadonnées de recherche ;
- test volume avec DOM imbriqué ;
- test du fallback legacy face à `Genres Manga` ;
- test de réutilisation du cache HTML après changement de parseur.
