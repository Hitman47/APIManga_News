# Architecture

## Vue d'ensemble

```mermaid
flowchart LR
    Client --> API[FastAPI]
    API --> Service[MangaNewsService]
    Service --> Fetcher[AsyncFetcher]
    Service --> Cache[SQLiteCache]
    Fetcher --> MN[Manga-News]
```

## Rôles

- `app/main.py` : exposition HTTP et OpenAPI ;
- `app/manga_news/service.py` : orchestration, cache, enrichissement, projections ;
- `app/manga_news/parsers.py` : lecture HTML et normalisation ;
- `app/cache.py` : cache SQLite principal + cache négatif ;
- `app/utils.py` : normalisation de texte, matching, dates, slugs.

## Flux de recherche

```mermaid
sequenceDiagram
    participant C as Client
    participant A as API
    participant S as Service
    participant M as Manga-News
    participant K as Cache

    C->>A: GET /search?q=...
    A->>S: search(...)
    S->>K: lookup cache
    alt cache miss
        S->>M: fetch page(s) de recherche
        S->>S: parse + score + dedupe
        S->>M: enrichissement éventuel fiche série/volume
        S->>K: store payload
    end
    S-->>A: enveloppe
    A-->>C: JSON + ETag
```

## D'où viennent les compteurs VF / VO

- source HTML : bloc `#numberblock` sur la fiche série Manga-News ;
- consommation directe : `/series/{slug}` ;
- consommation indirecte : `/volume/{series_slug}/{volume_slug}` et résultats de recherche enrichis.

Cela explique pourquoi :
- un volume peut avoir `vf` / `vo` même si sa page propre ne contient pas ces compteurs ;
- un résultat de recherche volume peut avoir `vf` / `vo` après enrichissement de la série parente.
