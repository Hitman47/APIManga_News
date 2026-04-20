# Cas d’usage et recettes

Ce document est volontairement orienté pratique. Il répond à la question : *comment utiliser l’API dans un vrai flux ?*

## 1. Cas d’usage classiques

## 1.1 Je veux la fiche complète d’une série

### Entrée

Tu connais le nom de la série, mais pas forcément son slug.

### Flux recommandé

1. `GET /search/resolve?q=<titre>&kind=series`
2. prends `data.best.slug`
3. appelle `GET /series/{slug}`
4. conserve l’`ETag`

### Exemple

```bash
curl -H "Authorization: Bearer $API_TOKEN" \
  "$BASE_URL/search/resolve?q=one%20piece&kind=series&limit=10"
```

Puis :

```bash
curl -H "Authorization: Bearer $API_TOKEN" \
  "$BASE_URL/series/One-piece-Edition-originale"
```

## 1.2 Je veux le tome 91 de One Piece

### Entrée

Tu connais déjà la série et le numéro.

### Flux recommandé

Utilise directement `/lookup/volume`.

```bash
curl -H "Authorization: Bearer $API_TOKEN" \
  "$BASE_URL/lookup/volume?series=One%20Piece&number=91"
```

### Pourquoi c’est préférable

Parce que :

- tu évites de gérer toi-même la résolution
- l’API te renvoie à la fois le volume et le contexte de résolution
- tu limites les heuristiques côté client

## 1.3 Je veux juste quelques champs, pas toute la fiche

### Série

```bash
curl -H "Authorization: Bearer $API_TOKEN" \
  "$BASE_URL/series/One-piece-Edition-originale?fields=title,vf.volumes,stats.reader_score"
```

### Volume

```bash
curl -H "Authorization: Bearer $API_TOKEN" \
  "$BASE_URL/volume/One-Piece/vol-91?fields=title,number_int,publication_date,isbn_ean"
```

### Quand utiliser `blocks`

Utilise `blocks` si tu veux des groupes logiques.

Exemple :

```bash
curl -H "Authorization: Bearer $API_TOKEN" \
  "$BASE_URL/volume/One-Piece/vol-91?blocks=release,scores"
```

## 1.4 Je veux suivre l’actualité d’une série

```bash
curl -H "Authorization: Bearer $API_TOKEN" \
  "$BASE_URL/news/series/One-piece-Edition-originale?limit=10"
```

Tu peux ensuite stocker le `fingerprint` ou l’`ETag` pour savoir si le contenu a changé entre deux passages.

## 1.5 Je veux construire un écran planning

Exemple : nouveautés VF filtrées par éditeur et mot-clé.

```bash
curl -G -H "Authorization: Bearer $API_TOKEN" \
  "$BASE_URL/planning" \
  --data-urlencode "section=manga-vf" \
  --data-urlencode "publisher=Glénat" \
  --data-urlencode "q=one piece" \
  --data-urlencode "sort=date_desc" \
  --data-urlencode "limit=10"
```

Le client doit lire `pagination` et ne pas supposer que 10 résultats signifie forcément “fin de liste”.

## 2. Cas d’usage IA / agent

## 2.1 Agent qui cherche une série puis répond à un utilisateur

### Stratégie

- si l’utilisateur donne un titre flou -> `/search/resolve`
- si la confiance est suffisante -> `/series/{slug}` ou `/volume/...`
- si la confiance est faible -> proposer plusieurs candidats

### Exemple de logique

1. `search/resolve?q=monster&kind=series`
2. lire `data.confidence`
3. si `high` ou `medium`, charger la fiche complète
4. si `low`, afficher aussi `data.candidates`

## 2.2 Agent qui connaît déjà “série + tome”

Règle simple : **ne pas bricoler une recherche floue si `/lookup/volume` suffit**.

Exemple :

```text
Entrée : “donne-moi les infos du tome 91 de One Piece”
Action : GET /lookup/volume?series=One%20Piece&number=91
```

## 2.3 Agent qui doit limiter son trafic

L’agent doit :

- stocker l’`ETag`
- rejouer avec `If-None-Match`
- respecter `429` et `Retry-After`
- éviter d’appeler les endpoints admin sauf besoin réel

## 2.4 Prompt de base pour une autre IA

Tu peux donner cette consigne à une autre IA :

> Tu consommes une API Manga News dont la base URL se termine déjà par `/v1`. Pour les endpoints publics, envoie `Authorization: Bearer <API_TOKEN>`. Pour les endpoints admin, envoie `Authorization: Bearer <ADMIN_TOKEN>`. Si tu connais une série et un numéro de tome, utilise `/lookup/volume`. Sinon, commence par `/search/resolve`. Gère explicitement `401`, `404`, `429`, `502`, et réutilise les `ETag` quand tu relis la même ressource.

## 3. Recettes curl prêtes à copier

## 3.1 Initialisation shell

Linux / macOS :

```bash
export BASE_URL="http://localhost:8017/v1"
export API_TOKEN="ton_token_public"
export ADMIN_TOKEN="ton_token_admin"
```

Windows PowerShell :

```powershell
$env:BASE_URL = "http://localhost:8017/v1"
$env:API_TOKEN = "ton_token_public"
$env:ADMIN_TOKEN = "ton_token_admin"
```

## 3.2 Série par recherche puis chargement

```bash
curl -H "Authorization: Bearer $API_TOKEN" \
  "$BASE_URL/search/resolve?q=one%20piece&kind=series&limit=10"

curl -H "Authorization: Bearer $API_TOKEN" \
  "$BASE_URL/series/One-piece-Edition-originale"
```

## 3.3 Volume par recherche libre

```bash
curl -H "Authorization: Bearer $API_TOKEN" \
  "$BASE_URL/search/resolve?q=one%20piece%20tome%2091&kind=volume&limit=10"

curl -H "Authorization: Bearer $API_TOKEN" \
  "$BASE_URL/volume/One-Piece/vol-91"
```

## 3.4 Volume directement par série + numéro

```bash
curl -H "Authorization: Bearer $API_TOKEN" \
  "$BASE_URL/lookup/volume?series=One%20Piece&number=91"
```

## 3.5 News globales

```bash
curl -H "Authorization: Bearer $API_TOKEN" \
  "$BASE_URL/news/global?limit=10"
```

## 3.6 Invalidation admin ciblée

```bash
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  "$BASE_URL/admin/cache/invalidate" \
  -d '{"resource_url":"https://www.manga-news.com/index.php/manga/One-Piece/vol-91"}'
```

## 3.7 Lecture des métriques

```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$BASE_URL/admin/metrics"
```

## 4. Ce qu’un client ne doit pas faire

- ne pas utiliser les routes non versionnées si `/v1` est disponible
- ne pas traiter `UPSTREAM_PARSE_ERROR` comme une absence métier définitive
- ne pas ignorer `Retry-After`
- ne pas refaire en boucle la même recherche floue si `lookup/volume` suffit
- ne pas appeler les endpoints admin avec le token public
- ne pas supposer qu’un champ absent est forcément “faux” ; certains champs peuvent être `null` faute d’information amont

## 5. Scénarios de validation humaine

Quand tu livres l’API à quelqu’un, fais-lui tester au minimum :

1. `GET /v1/health`
2. `GET /v1/search/resolve?q=one%20piece&kind=series`
3. `GET /v1/lookup/volume?series=One%20Piece&number=91`
4. `GET /v1/news/global?limit=5`
5. `GET /v1/planning?section=manga-vf&limit=5`
6. `GET /v1/admin/metrics`

Si ces 6 points marchent, la base de l’API est exploitable.
