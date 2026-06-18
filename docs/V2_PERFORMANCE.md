# V2 performance

Ce document décrit uniquement le comportement expérimental de la branche `v2`.
La documentation existante à la racine et dans `docs/` reste la documentation
legacy et n'est pas modifiée.

## Objectifs

Ordre de priorité :

1. réduire les appels vers Manga News ;
2. réduire la latence ;
3. conserver une fraîcheur contrôlée à la demande.

La V2 n'ajoute aucun rafraîchissement périodique. Une entrée expirée est
rafraîchie uniquement lorsqu'une requête cliente la demande.

## Changements

- `/search` n'enrichit plus les résultats par défaut ;
- `/search` retourne jusqu'à 50 correspondances par défaut avec `mode=all` ;
- les compteurs `vf` / `vo` ne sont plus hydratés par défaut ;
- `mode=best` enrichit au maximum un candidat ;
- les appels HTTP vers Manga News sont limités globalement à 6 simultanés par
  processus avec `REQUEST_MAX_CONCURRENCY` ;
- le conteneur limite Uvicorn à 20 connexions concurrentes ;
- un cache stale utilisable continue d'être servi pendant la durée d'un
  negative cache ;
- les événements `upstream.fetch` exposent le temps total et le temps d'attente
  dans la file de concurrence via `/health/runtime`.

## Enrichissement explicite

Une recherche simple couvre une franchise complète, y compris les suites,
spin-offs et séries dérivées dont le titre correspond :

```text
GET /search?q=fairy%20tail&kind=series
```

Les valeurs par défaut V2 sont `mode=all`, `limit=50`,
`include_related=true` et `include_books=true`.

Le fichier `openapi.json` à la racine est généré depuis le même schéma FastAPI
que `/openapi.json`. Un test empêche sa publication s'il n'est plus synchronisé.

Pour retrouver le contrat enrichi de la V1 :

```text
GET /search?q=one%20piece&kind=series&enrich=true&include_editions=true
```

Pour une recherche rapide :

```text
GET /search?q=one%20piece&kind=series&mode=best&limit=1
```

## Etat de sortie d'une serie

La V2 ajoute une route dediee pour obtenir, a partir d'un slug de serie, le
dernier tome VF sorti et le prochain tome VF annonce :

```text
GET /series/One-piece-Edition-originale/release-state
```

Cette route reutilise la fiche serie et la page editions VF. Elle ne relit pas
les fiches volume par defaut. Pour recuperer aussi l'ISBN/EAN du dernier tome et
du prochain tome, activer explicitement l'enrichissement :

```text
GET /series/One-piece-Edition-originale/release-state?include_isbn=true
```

Parametres utiles :

- `today=YYYY-MM-DD` : force la date de reference, pratique pour les tests ;
- `include_special=true` : inclut les volumes detectes comme speciaux ;
- `include_isbn=true` : relit uniquement les fiches volume last/next pour
  remplir `isbn_ean`.

Le fichier `v2.env.example` contient les réglages recommandés pour un
conteneur disposant de 2 CPU et 2 Go de RAM.

## Test Docker isolé

La V2 possède son propre Compose et son propre tag GHCR. Elle remplace le
conteneur legacy sur le même port public `8017`, sans modifier la branche
`main`.

### Déploiement NAS

L'image V2 multiarchitecture publiée par GitHub Actions est :

```text
ghcr.io/hitman47/apimanga_news:v2
```

Le fichier `docker-compose.v2.yml` tire directement cette image. Aucun clone du
dépôt ni build local n'est nécessaire :

```bash
docker compose -f docker-compose.v2.yml pull
docker compose -f docker-compose.v2.yml up -d
```

L'API V2 est ensuite disponible sur `http://ADRESSE_DU_NAS:8017`.

L'ancien conteneur doit être arrêté avant le démarrage de la V2, car deux
conteneurs ne peuvent pas publier simultanément le port `8017`.

Le package GHCR est privé. Le NAS doit être connecté au registre avec
l'utilisateur `Hitman47` et un token GitHub disposant au minimum du droit
`read:packages` :

```bash
echo "$GHCR_TOKEN" | docker login ghcr.io -u Hitman47 --password-stdin
```

Dans Portainer, ajouter `ghcr.io` dans **Registries** avec ces mêmes
identifiants, puis sélectionner ce registre pour la stack.

Le tag `latest` reste associé à la version legacy. Le workflow V2 publie aussi
un tag immuable `v2-sha-<commit>` pour permettre un retour précis à une version
antérieure.

### Construction locale

Pour construire la V2 depuis les sources :

```powershell
docker compose `
  -f docker-compose.v2.yml `
  -f docker-compose.v2-build.yml `
  up -d --build
```

### Timeout TLS du registry

Si le build échoue avant la première étape avec `TLS handshake timeout`, le
moteur Docker Desktop n'arrive pas à joindre le registry. Le projet n'est pas
encore en cours de construction à ce stade.

Vérifications utiles :

```powershell
docker pull python:3.12-slim
docker pull public.ecr.aws/docker/library/python:3.12-slim
```

L'image de base est configurable si un miroir accessible est disponible :

```powershell
$env:PYTHON_BASE_IMAGE = "mon-registry/python:3.12-slim"
docker compose `
  -f docker-compose.v2.yml `
  -f docker-compose.v2-build.yml `
  up -d --build
```

Si plusieurs registries expirent, vérifier dans Docker Desktop la configuration
Proxy, DNS et certificats d'entreprise, puis redémarrer Docker Desktop.

### Antivirus ou proxy avec inspection HTTPS

Si le pull fonctionne mais que `pip install` échoue avec
`CERTIFICATE_VERIFY_FAILED`, Windows approuve probablement une autorité locale
qui n'existe pas encore dans l'image Linux.

Exporter cette autorité au format Base-64 X.509, puis utiliser l'override
fourni :

```powershell
$env:DOCKER_CA_CERT_FILE = "C:\chemin\autorite-locale.crt"
docker compose `
  -f docker-compose.v2.yml `
  -f docker-compose.v2-build.yml `
  -f docker-compose.v2-ca.yml `
  up -d --build
```

Le certificat est monté comme secret BuildKit, ajouté au magasin Linux pendant
le build, puis absent du contexte et des couches applicatives. Le dossier local
`.docker-certs` est ignoré par Git.

## Benchmarks

Le runner V2 couvre plusieurs franchises et plusieurs niveaux de coût :

- recherches légères de séries et volumes ;
- recherches enrichies avec `vf` / `vo` ;
- projections de fiches série et volume ;
- résolution d'un volume par numéro via les éditions VF ;
- enrichissement d'un volume depuis sa série parente ;
- etat de sortie VF d'une serie, avec et sans enrichissement ISBN ;
- actualités et planning ;
- charge concurrente mixte ;
- comparaison du premier passage et du cache chaud.

### Test rapide

```powershell
.\.venv\Scripts\python.exe scripts\run_v2_benchmarks.py --profile quick
```

### Mesure isolée

Le filtre `--scenario` évite qu'un scénario précédent remplisse le cache. Il
peut être répété pour sélectionner plusieurs cas :

```powershell
.\.venv\Scripts\python.exe scripts\run_v2_benchmarks.py `
  --scenario series_naruto_projection `
  --passes 2 `
  --skip-concurrency
```

Pour diagnostiquer rapidement une API ou un moteur Docker indisponible :

```powershell
.\.venv\Scripts\python.exe scripts\run_v2_benchmarks.py `
  --profile quick `
  --timeout 15 `
  --max-consecutive-unavailable 1 `
  --skip-concurrency
```

Le runner s'arrête par défaut après deux erreurs de connexion consécutives.

### Test standard recommandé

```powershell
.\.venv\Scripts\python.exe scripts\run_v2_benchmarks.py `
  --profile standard `
  --passes 2 `
  --concurrency 8 `
  --concurrent-requests 24
```

### Test plus lourd

Le profil `stress` interroge davantage de routes Manga News. Il doit rester
occasionnel :

```powershell
.\.venv\Scripts\python.exe scripts\run_v2_benchmarks.py `
  --profile stress `
  --passes 3 `
  --repetitions 2 `
  --concurrency 12 `
  --concurrent-requests 48
```

Les rapports sont écrits dans `benchmark-results/<date>/` :

- `report.json` : données complètes et deltas de métriques ;
- `summary.csv` : moyenne, p50, p95, erreurs et réponses cache par scénario ;
- `samples.csv` : chaque requête individuelle.

Le passage 1 mesure l'état courant du cache. Les passages suivants mesurent le
cache chaud. Pour un vrai test à froid isolé, arrêter la V2, supprimer uniquement
le dossier `data-v2`, puis redémarrer le Compose V2.

Indicateurs à surveiller :

- `upstream_fetch_success` : doit fortement diminuer sur les passages chauds ;
- `cache_hits` : doit augmenter ;
- `p95_ms` : plus représentatif que la moyenne sous concurrence ;
- `upstream_fetch_retries` et `upstream_fetch_errors` : doivent rester proches
  de zéro ;
- `cached_responses` : doit couvrir la majorité du second passage.

## Diagnostic du parsing

Le profilage d'une fiche One Piece réelle de 531 Ko, 11 606 nœuds DOM,
1 166 lignes de texte et 831 liens a identifié deux surcoûts :

- la recherche du contexte de chaque lien remontait les ancêtres et les frères
  précédents, avec un coût qui augmentait tout au long du document ;
- les mêmes lignes et les mêmes préfixes de champs étaient normalisés plusieurs
  dizaines de milliers de fois dans les sections et les statistiques.

Après suppression du parcours contextuel et création d'un index normalisé
réutilisé par tous les extracteurs, les coûts observés sont :

- construction BeautifulSoup : environ 865 ms ;
- normalisation unique des 1 166 lignes : environ 74 ms ;
- résumé et points forts : moins de 1 ms chacun ;
- toutes les sections brutes : environ 3 ms ;
- les 16 champs bibliographiques : environ 14 ms ;
- compteurs et notes : environ 7 ms au total ;
- liens associés : environ 437 ms.

Le parsing complet de cette fiche est passé d'environ 23 s lors du premier
constat à une médiane proche de 2,75 s sur cinq passages locaux. La variabilité
restante vient principalement de la construction du DOM et du parcours des
831 liens, pas d'un champ bibliographique isolé.
