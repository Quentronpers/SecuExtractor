# CLAUDE.md — SecurScope Catalog

Pipeline d'extraction des caractéristiques techniques d'équipements depuis les
notices PDF constructeur. Projet **autonome**, distinct de l'application
SecurScope. Sa sortie est un fichier de données vérifiées que l'application
importe.

## Le principe qui commande tout

**Toute donnée entre dans la base. Aucune ne ment sur sa fiabilité.**

Le pipeline vise le volume — plusieurs dizaines de milliers de références, à
l'image de ce que proposent les outils concurrents — sans que ce volume soit
conditionné à une relecture humaine exhaustive, qui serait impossible.

La réconciliation tient en un principe : **une valeur non relue est utilisable,
mais elle est marquée comme telle, et le logiciel le dit à l'utilisateur.**

### Deux niveaux de fiabilité, portés par la donnée elle-même

| Niveau | Ce que c'est | Ce qu'on peut en faire |
|---|---|---|
| `extrait` | Valeur produite par le pipeline, avec sa citation source, jamais relue par un humain. | Sélection, placement sur plan, nomenclature. Alimente un calcul **en le marquant comme reposant sur une donnée non vérifiée**. |
| `verifie` | Valeur relue et validée par un humain. | Tout, sans réserve. |

Une référence n'a donc pas un état global : **chacun de ses champs porte le
sien**. Une caméra peut avoir une désignation `extrait` et une puissance PoE
`verifie`, ou l'inverse. C'est la granularité qui rend le modèle tenable.

### Ce que cela change pour l'application

Quand un calcul consomme au moins un champ `extrait`, son résultat est marqué
comme provisoire et l'utilisateur voit lesquelles de ses données ne sont pas
vérifiées. Le calcul se fait quand même — refuser de calculer serait pire — mais
il ne se présente jamais comme certain.

Le jour où le champ passe en `verifie`, l'avertissement disparaît pour tout le
monde, sans que rien d'autre ne change.

**C'est aussi un argument produit.** Aucun concurrent n'indique d'où viennent
ses données ni ce qui a été contrôlé. Afficher la source et le niveau de
vérification est une différence visible, pas seulement une précaution.

### Le tri des champs à relire

Un champ `extrait` ne devient pas `verifie` par hasard. Trois portes d'entrée
dans la file de relecture, par ordre de priorité :

1. **Gammes prioritaires** — les marques dominantes du marché, choisies à la
   main. C'est le socle de qualité qu'on constitue en premier.
2. **Déclenchement par l'usage** — une référence effectivement posée dans un
   projet réel remonte dans la file. On vérifie ce qui sert, pas ce qui dort.
3. **Signalement** — un utilisateur conteste une valeur, elle repasse en file.

Le reste attend, et c'est très bien : une référence jamais utilisée n'a jamais
besoin d'être relue.

### Trois états d'extraction, à ne pas confondre avec les niveaux

Au sein du niveau `extrait`, le pipeline distingue ce qu'il a produit :

| État | Signification | Devenir |
|---|---|---|
| `sur` | Valeur trouvée, extrait source cité, plausibilité vérifiée. | Exportée en `extrait`. Relue plus tard selon la priorité. |
| `douteux` | Valeur trouvée mais citation incohérente ou plausibilité en échec. | Exportée en `extrait`, **placée en tête de file de relecture**. |
| `absent` | Champ introuvable dans la source. | Reste vide, jamais inféré. |

En cas d'hésitation, `douteux` — le faux négatif coûte une minute de relecture,
le faux positif fait dimensionner un switch trop petit sur un chantier réel.

## Stack

- **Python** 3.13 dans le conteneur (code compatible 3.12)
- **Outillage** : `uv` (dépendances, `uv.lock`), `ruff` (format et lint), `mypy`, `pytest`
- **Acquisition** : `requests` + `BeautifulSoup` en premier, repli `playwright`
  quand la page dépend du JavaScript
- **Lecture** : `pdfplumber` pour les PDF, conversion en texte structuré pour
  les fiches HTML
- **Modèle** : API Anthropic, traitement par lots (moitié prix)
- **Validation de forme** : `pydantic` v2
- **Stockage** : SQLite (un seul fichier, aucun serveur)
- **Relecture** : Streamlit, application locale

Pas de Django, pas de PostgreSQL, pas de serveur web. Ce projet produit un
artefact, il ne rend pas de service.

## L'acquisition : ratisser large, par repli progressif

L'entrée du pipeline est **une liste de fabricants**, pas une liste d'URL. Le
module se débrouille pour trouver les produits, et ne demande une intervention
humaine que là où il échoue.

```
Liste de fabricants
    │
    ├─► [1] Trouver le site officiel
    │        échec ─────────────────────► URL fournie à la main
    │
    ├─► [2] Trouver les pages catalogue et produit
    │        échec ─────────────────────► URL fournie à la main
    │
    ├─► [3] Pour chaque produit : chercher un PDF de notice
    │        trouvé ────────────────────► téléchargement et archivage
    │        absent ────────────────────► extraction depuis la page produit
    │
    └─► [4] Ni PDF ni page exploitable ─► saisie manuelle
```

**Chaque échec est journalisé, jamais silencieux.** La commande `status`
remonte ce qui n'a pas abouti et à quelle étape, pour que le complément manuel
soit ciblé au lieu d'être une exploration à l'aveugle.

### La page produit est une source de plein droit

Beaucoup de fabricants — Ajax en est l'exemple type — publient leurs
spécifications en page web sans jamais produire de PDF. **La page web n'est pas
un pis-aller : c'est une source équivalente**, avec sa propre forme de citation
(URL, horodatage, extrait). Télécharger un PDF quand il existe reste préférable
parce que le document est figé, mais l'absence de PDF n'exclut pas une
référence.

C'est aussi ce qui rend le volume atteignable : télécharger et lire des dizaines
de milliers de PDF serait interminable, alors qu'une page produit se traite en
quelques secondes.

### Générique d'abord, adaptateur ensuite

`adapters/generic.py` traite le cas courant : recherche du site, repérage des
liens catalogue, détection des pages produit, extraction des liens de notice.

Un adaptateur spécifique n'est écrit **qu'après un échec constaté** sur un
fabricant, et il hérite du générique en ne redéfinissant que ce qui diffère.
Chaque adaptateur est une dette qui se réveille à la première refonte du site :
trois adaptateurs bien choisis valent mieux que quinze écrits par anticipation.

### Stratégie de récupération

`requests` d'abord — rapide, suffisant pour la majorité des sites. `playwright`
en repli automatique quand la page revient vide ou manifestement incomplète,
signe d'un contenu injecté en JavaScript. Le manifeste note quel outil a servi.

### Cadre à respecter

Les caractéristiques techniques sont des faits, librement réutilisables. Le
téléchargement automatisé, lui, se discipline :

- respecter `robots.txt`, sans exception ;
- cadence lente, une requête toutes les deux à trois secondes par domaine ;
- en-tête `User-Agent` identifiable, avec un moyen de contact ;
- reprise sur erreur avec attente croissante, abandon après trois tentatives ;
- aucun contournement de protection : un site qui bloque passe en manuel ;
- ne jamais redistribuer les documents téléchargés.

Un scraper qui se fait bloquer coûte plus cher qu'une saisie manuelle.

### Ce que l'acquisition produit

Un dossier `data/sources/<fabricant>/` avec les documents archivés, et un
manifeste qui garde pour chacun son origine, sa date de capture et son
empreinte. **Le pipeline lit ce dossier sans jamais savoir d'où il vient** —
c'est ce qui permet à l'acquisition de casser sans emporter le reste avec elle.

## Commandes

L'hôte (NAS) n'a ni Python ni jq : **tout tourne dans le conteneur
`dev_catalog`**, démarré par `docker compose up -d dev` (le dépôt y est
monté sur `/app`, l'environnement est dans `/opt/venv`). Les commandes
ci-dessous se lancent donc sous la forme
`docker exec dev_catalog sh -c "cd /app && <commande>"`.

```bash
# Découverte : à partir d'une liste de fabricants
python -m catalog.cli discover --fabricants data/fabricants.txt

# Téléchargement et archivage de ce qui a été découvert
python -m catalog.cli acquire --fabricant dahua

# Extraction sur ce qui est archivé
python -m catalog.cli extract --fabricant dahua

# File de relecture, par priorité
streamlit run catalog/review/app.py

# Export du catalogue, avec les niveaux de fiabilité
python -m catalog.cli export --out data/catalog.json

# État : découvert, extrait, vérifié, échecs par étape
python -m catalog.cli status
```

### Vérifications

```bash
ruff format --check catalog tests && ruff check catalog tests   # format + lint
mypy                                                             # types
pytest                                                           # tests, architecture comprise
```

La CI (`.github/workflows/ci.yml`) rejoue les trois à chaque push sur
`master`. Les hooks de `.claude/` formatent et contrôlent chaque fichier
édité, et bloquent un commit dont les fichiers indexés ne passent pas.

`tests/test_architecture.py` garde : la frontière de l'acquisition (seul
`catalog/cli.py` importe `catalog.acquisition`, et l'acquisition n'importe
rien de l'aval), fichier ≤ 300 lignes, fonction ≤ 30 lignes hors
docstring, ≤ 5 paramètres. Les écarts gelés vont dans
`tests/architecture_debt.txt`, qui ne peut que rétrécir.

Aucun test n'appelle le réseau ni l'API Anthropic : le client modèle se
remplace par un faux. Ce qui appelle l'API (`extract`, évaluation en
direct) coûte de l'argent et se lance avec l'accord de Quentin.

## Structure

```
securscope-catalog/
├── CLAUDE.md
├── docs/
│   └── pipeline.md              # le déroulé détaillé, à lire une fois
│
├── schema/
│   └── specifications-equipements.json   # LA référence, ne pas modifier ici
│
├── catalog/
│   ├── cli.py                   # point d'entrée en ligne de commande
│   ├── models.py                # modèles Pydantic générés depuis le schéma
│   ├── acquisition/
│   │   ├── fetcher.py           # requests, repli playwright, cadence
│   │   ├── discovery.py         # recherche des pages catalogue et notices
│   │   ├── manifest.py          # journal des fichiers : url, date, empreinte
│   │   └── adapters/
│   │       ├── generic.py       # cas courant, à essayer en premier
│   │       └── <fabricant>.py   # uniquement si le générique échoue
│   ├── reading/
│   │   ├── pdf_reader.py        # texte et tableaux depuis un PDF
│   │   ├── html_reader.py       # texte structuré depuis une fiche web
│   │   └── chunker.py           # découpage en sections exploitables
│   ├── extraction/
│   │   ├── client.py            # appel du modèle, abstraction du fournisseur
│   │   ├── prompts.py           # gabarits par famille d'équipement
│   │   └── runner.py            # orchestration d'un lot
│   ├── plausibility/
│   │   ├── rules.py             # règles de vraisemblance par champ
│   │   └── checker.py           # application des règles
│   ├── storage/
│   │   ├── db.py                # SQLite, schéma et connexion
│   │   └── repository.py        # lecture et écriture des extractions
│   ├── review/
│   │   └── app.py               # interface Streamlit de relecture
│   └── export/
│       └── writer.py            # export du catalogue vérifié
│
└── data/
    ├── sources/
    │   ├── <fabricant>/         # notices archivées, PDF et HTML
    │   ├── manifeste.json       # url, date, empreinte de chaque fichier
    │   ├── sites_manuels.json    # sites que la recherche n'a pas trouvés
    │   ├── catalogues_manuels.json  # pages catalogue à fournir
    │   ├── produits_manuels.json    # URL de produits à fournir
    │   └── echecs.json           # journal : quoi, où, quelle action attendue
    ├── catalog.db               # SQLite, non versionné
    └── catalog.json             # sortie, non versionnée
```

Le dossier `data/sources/` n'est pas versionné mais il est **conservé**. Un
document supprimé rend invérifiables toutes les citations qui en dépendent.

## Le schéma d'extraction

`schema/specifications-equipements.json` définit 54 types d'équipements et
1 470 champs, répartis en 5 familles. **C'est la source de vérité.** Les
modèles Pydantic sont générés depuis lui, jamais écrits à la main en parallèle.

Chaque champ y déclare :
- `type` — string, number, integer, boolean, enum, array, object
- `unite` — l'unité attendue après conversion
- `obligatoire` — si son absence doit être signalée
- `usage` — identification, calcul, selection, nomenclature
- `alimente` — les calculateurs qui consomment ce champ

Les champs marqués `usage: calcul` sont ceux dont l'exactitude compte le plus :
ils alimentent les calculs d'autonomie, de budget PoE et de capacité. Un doute
sur eux passe en `douteux` sans hésitation.

## Règles d'extraction — non négociables

1. **Citation obligatoire.** Toute valeur extraite porte son extrait source :
   fichier, page, et le texte exact d'où elle vient. Sans citation, la valeur
   est `douteux` quelle que soit la confiance du modèle.
2. **Jamais d'inférence.** Un champ absent de la notice reste `absent`. Le
   modèle ne calcule pas, ne déduit pas, ne complète pas par analogie avec un
   produit voisin.
3. **La valeur maximale prime.** Quand une notice donne une valeur de base et
   une valeur maximale — typiquement la consommation PoE — retenir la maximale.
   Sous-estimer une consommation fait sous-dimensionner un switch.
4. **Les plages restent des plages.** Une focale « 2,7-13,5 mm » est conservée
   telle quelle en chaîne. C'est le calcul, plus tard, qui décidera de la borne
   à retenir.
5. **Pas de conversion hasardeuse.** Une puissance en watts ne devient pas un
   courant en milliampères sans tension connue. Si les deux sont donnés,
   remplir les deux champs. Sinon, remplir celui qui existe.
6. **Un schéma étroit par appel.** Ne jamais demander au modèle de remplir les
   35 champs d'un type en une fois : découper par bloc (identification,
   alimentation, environnement, physique, accessoires). La fiabilité chute
   brutalement avec la largeur du schéma.

## Les règles de plausibilité

Elles sont ce qui rattrape les erreurs que la citation ne détecte pas. Un
modèle peut citer correctement un extrait et se tromper sur l'unité.

Exemples à implémenter dans `plausibility/rules.py` :

| Champ | Règle | Si échec |
|---|---|---|
| `courant_repos_ma` | entre 1 et 2 000 mA | `douteux` |
| `courant_alarme_ma` | ≥ `courant_repos_ma` | `douteux` sur les deux |
| `puissance_poe_w` | entre 1 et 90 W | `douteux` |
| `tension_alimentation_v` | dans {12, 24, 48} ± 20 % | `douteux` |
| `angle_horizontal_deg` | entre 1 et 360 | `douteux` |
| `capacite_batterie_ah` | entre 0,8 et 200 Ah | `douteux` |
| `nombre_zones_filaires` | entre 1 et 512 | `douteux` |
| `portee_m` | entre 0,5 et 500 m | `douteux` |

Ces bornes sont larges à dessein : elles attrapent les erreurs d'unité et de
virgule, pas les erreurs subtiles. Celles-là relèvent de la relecture humaine.

## L'interface de relecture

C'est la pièce centrale du projet, pas un accessoire. Elle traite **une file
priorisée**, pas un lot complet — puisque l'immense majorité des champs
`extrait` ne sera jamais relue, et n'a pas à l'être.

Ordre de la file :

1. les champs `douteux` des gammes prioritaires ;
2. les champs `douteux` des références effectivement utilisées en projet ;
3. les champs `sur` des références utilisées, par fréquence d'usage décroissante ;
4. les signalements d'utilisateurs.

Dans chaque strate, les champs `usage: calcul` passent avant les autres : un
champ de sélection approximatif est un inconvénient, un champ de calcul faux
est une faute.

Pour chaque champ, l'interface affiche :
- le nom du champ, son unité attendue, ce qu'il alimente
- la valeur proposée et son état d'extraction
- **l'extrait source cité, en clair**
- la règle de plausibilité en échec, s'il y en a une
- le nombre de projets utilisant cette référence, s'il y en a
- trois actions : valider, corriger, marquer absent

Une action fait passer le champ en `verifie` et l'avertissement disparaît pour
tous les utilisateurs.

**L'objectif de temps est de quelques secondes par champ**, pas par référence.
Si l'interface impose plus de deux clics pour trancher un cas évident, c'est
elle qu'il faut corriger.

## Ce qu'on ne fait pas

- Pas de recherche documentaire à l'exécution. Le catalogue est figé et sourcé.
- Pas d'aspiration systématique de catalogue. On cible les notices, on ne
  parcourt pas l'intégralité d'un site.
- Pas de contournement de protection. Un site qui bloque est traité à la main.
- Pas de redistribution des notices. On extrait des faits techniques, on ne
  republie pas les documents.
- Pas d'adaptateur écrit par anticipation. Le générique d'abord, l'adaptateur
  seulement après un échec constaté.
- Pas d'import direct dans la base de SecurScope. La frontière entre les deux
  projets est un fichier JSON versionné, et rien d'autre.

## Méthode de travail

Fichier par fichier, avec une responsabilité définie à l'avance. Quand un
fichier est demandé :

1. Lire les fichiers voisins pour s'aligner sur ce qui existe.
2. Écrire le fichier complet, typé, avec des docstrings courtes.
3. Signaler les hypothèses faites et ce qui aurait pu être découpé autrement.
4. Ne pas créer de fichiers annexes non demandés.

Les étapes d'envergure suivent le cycle commun aux projets de Quentin
(`vault/claude/workflow.md`) : `/cadrage` → plan dans `docs/chantiers/`,
un lot par session, `/verifier` après chaque étape, `/fin-de-lot` pour
clore (relecture, docs, vault, `reprise.md`, proposition de commit).

À la fin de chaque étape, proposer un **menu numéroté** des suites
possibles, auquel Quentin répond d'un chiffre.

### Ce que tu ne fais pas sans me demander

- `git commit` et `git push` ;
- ajouter ou changer une dépendance, l'outillage (`pyproject.toml`,
  `uv.lock`, `Dockerfile`, `docker-compose.yml`) ou la config des
  linters ;
- allonger `tests/architecture_debt.txt` ;
- modifier un document archivé ou le manifeste dans `data/sources/` ;
- modifier le jeu de référence annoté (`eval/reference/`) ;
- lancer ce qui appelle l'API Anthropic (`extract`, évaluation en direct).

Interdit sans exception : modifier `schema/` (la référence vit hors de ce
dépôt), lire ou écrire un `.env`, `--no-verify`.

## Contexte détaillé

`docs/pipeline.md` — le déroulé complet du pipeline, les états d'un champ, et
la procédure d'ajout d'une nouvelle gamme.
