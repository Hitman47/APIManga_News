# Architecture

Ce document explique comment les composants s'enchaînent réellement.

## Vue d'ensemble

```mermaid
flowchart LR
    C[Client / Outil / IA] --> A[FastAPI routes]
    A --> B[MangaNewsService]
    B --> D[SQLiteCache]
    B --> E[AsyncFetcher]
    E --> F[Manga News HTML / RSS]
    B --> G[Parsers HTML / RSS]
    G --> H[Modèles Pydantic]
    H --> A
```

## Chaîne de traitement d'une requête

1. **Route FastAPI**
   - valide les paramètres ;
   - vérifie le Bearer token si `API_TOKEN` est actif ;
   - injecte / propage `X-Request-Id` via un middleware HTTP ;
   - enregistre les métriques HTTP agrégées ;
   - délègue au `MangaNewsService`.

2. **Service métier**
   - calcule une clé de cache stable ;
   - consulte le cache positif ;
   - consulte le negative cache si activé ;
   - mutualise les fetchs concurrents identiques via un mécanisme local de type single-flight ;
   - fetch l'upstream si nécessaire ;
   - parse la réponse ;
   - construit l'enveloppe finale.

3. **Observabilité runtime**
   - un `MetricsStore` agrège compteurs, timings roulants et derniers événements ;
   - `GET /health/runtime` expose ces métriques ainsi que l'état du cache et les defaults effectifs ;
   - les logs applicatifs reprennent `request_id` quand il existe.

4. **Cache SQLite**
   - stocke les réponses positives ;
   - stocke aussi les erreurs négatives courtes (`negative_cache_entries`) ;
   - garde une fenêtre stale pour servir une ancienne réponse si l'upstream échoue ;
   - réutilise une connexion SQLite persistante avec `journal_mode=WAL`, `synchronous=NORMAL` et `busy_timeout`.

5. **Fetcher HTTP**
   - envoie les requêtes vers Manga News ;
   - suit les redirections ;
   - traduit les erreurs HTTP / réseau en erreurs applicatives.

6. **Parsers**
   - analysent le HTML / RSS ;
   - extraient les champs normalisés ;
   - lèvent `ParseError` quand la page n'est pas exploitable.

## Flux de cache

```mermaid
flowchart TD
    A[Requête] --> B{Entrée positive fraîche ?}
    B -- Oui --> C[Retour cache]
    B -- Non --> D{Entrée négative fraîche ?}
    D -- Oui --> E[Relance ResourceNotFound / ParseError]
    D -- Non --> F[Fetch upstream]
    F --> G{Parsing OK ?}
    G -- Oui --> H[Écrit cache positif]
    H --> I[Réponse]
    G -- Non --> J[Écrit negative cache]
    J --> K{Ancien cache stale utilisable ?}
    K -- Oui --> L[Retour stale + warning]
    K -- Non --> M[Erreur]
```

## Search vs search/resolve

### `/search`
- interroge plusieurs pages de recherche Manga News selon `kind` ;
- cache d'abord les **pages source de recherche** par URL, indépendamment de `mode` et `limit` ;
- recharge ces pages source en parallèle, dans la limite de `SEARCH_SOURCE_CONCURRENCY` ;
- déduplique les URLs ;
- applique un ranking métier avant et après enrichissement : match exact titre/slug, priorité série vs volume selon la requête, puis priorité `media_kind` pour faire remonter les mangas principaux avant les romans/essais/livres dérivés ;
- enrichit ensuite les résultats retenus en mutualisant les fiches série / volume identiques, dans la limite de `SEARCH_ENRICHMENT_CONCURRENCY`.

### `/search/resolve`
- s'appuie sur `/search` ;
- choisit un `best` ;
- calcule une confiance (`high`, `medium`, `low`, `none`).

## Projections série / volume

Le service supporte deux mécanismes :
- `blocks=` : blocs métier prédéfinis ;
- `fields=` : chemins précis ;
- `include_raw_sections=true` : sections brutes du HTML déjà nettoyées.

C'est utile pour :
- les UI légères ;
- les prompts d'IA ;
- limiter la taille des payloads ;
- éviter des post-traitements inutiles côté client.

## Particularités utiles

### Titres alternatifs et typologie de recherche
- `title_vo`
- `translated_title`
- `source_type`
- `media_kind`

Ils sont disponibles sur les fiches détaillées et remontent aussi dans les recherches quand l'enrichissement réussit. `source_type` reflète le `Type` Manga-News. `media_kind` est une classification métier calculée par l'API pour distinguer manga principal, spin-off, roman, essai, guide, artbook, cookbook, etc.

### Normalisation volume
Les parseurs produisent des champs standardisés pour les volumes :
- `number`
- `number_int`
- `edition_label`
- `is_special`
- `is_one_shot`

Ces champs se retrouvent sur :
- les fiches volume ;
- les items d'éditions série ;
- les items du planning.

## Debug HTML

Quand `DEBUG_CAPTURE_HTML_ON_ERROR=true`, un `ParseError` sur une route cacheable peut sauver :
- un dump `.html` de la page upstream ;
- un fichier `.json` de métadonnées.

Le chemin est injecté dans le message d'erreur :

```text
Debug HTML saved to /tmp/manga-news-debug-html/...
```

## Ce qui existe dans le code mais n'est pas encore une vraie feature publique

Présent dans la config ou dans des modules, mais non exposé comme contrat public aujourd'hui :
- admin API publique ;
- rate limiting branché aux routes.

Les variables suivantes sont maintenant **actives** dans le runtime :
- `LOG_FORMAT`
- `X-Request-Id` sur toutes les réponses ;
- `/health/runtime` pour l'observabilité technique ;
- `REQUEST_MAX_RETRIES`
- `REQUEST_BACKOFF_SECONDS`
- `SEARCH_SOURCE_CONCURRENCY`
- `SEARCH_ENRICHMENT_CONCURRENCY`

## Enrichissement des recherches

Pour certains résultats `/search`, le service relit une fiche détaillée avant de répondre :
- résultat `series` -> relit la fiche série pour injecter `title_vo`, `translated_title`, `vf`, `vo` ;
- résultat `volume` -> relit la fiche volume pour injecter les champs normalisés du volume, puis relit la fiche série parente pour injecter `vf` / `vo`.

Ce comportement rend les réponses plus utiles, mais explique aussi pourquoi une recherche peut déclencher plusieurs fetchs amont lors d'un cache froid.

## Réglages d'exécution réellement pilotables

Les knobs suivants sont à nouveau pilotés par l'environnement et appliqués par le runtime :

- `SQLITE_BUSY_TIMEOUT_MS` pour le `PRAGMA busy_timeout` SQLite ;
- `CACHE_MEMORY_ENTRIES` pour le cache mémoire L1 ;
- `SEARCH_DEFAULT_ENRICH` et `SEARCH_DEFAULT_INCLUDE_EDITIONS` pour les routes de recherche ;
- `VOLUME_DEFAULT_INCLUDE_PARENT_EDITIONS` pour l'hydratation des compteurs sur `/volume` ; la valeur par défaut recommandée est `false` pour éviter un fetch parent implicite sur chaque volume.


## Optimisations structurelles des fiches

- les pages série et volume disposent maintenant d'un cache HTML brut partagé ;
- les parseurs légers `series-search-meta` et `volume-search-meta` relisent ce HTML pour hydrater rapidement `title_vo`, `translated_title`, `vf`, `vo`, `number`, `edition_label`, `is_special`, `is_one_shot` ;
- les routes détaillées (`/series`, `/volume`) peuvent ensuite parser le même HTML déjà en cache sans nouveau fetch upstream.
