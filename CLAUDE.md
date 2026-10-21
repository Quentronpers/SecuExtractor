# CLAUDE.md — SecurScope Catalog

> Instructions for the coding agent (Claude Code), in French. The project
> overview for readers is `README.md`; parts marked « prévu » are planned,
> not built yet.

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
- **Modèle** : serveur compatible OpenAI (`/v1/chat/completions`), sortie
  JSON au format strict : Ollama en local (`qwen3:14b`, sur le PC de
  Quentin), Groq en comparaison
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

**Chaque échec est journalisé, jamais silencieux**, avec sa cause, dans
`data/sources/echecs.json`. La commande `status` (prévue) en fera la synthèse :
ce qui n'a pas abouti et à quelle étape, pour que le complément manuel
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

- respecter `robots.txt`, sans exception, lu selon la RFC 9309 : fichier
  indisponible (erreur 4xx, stockage S3 ou Azure sans `robots.txt`) → accès
  autorisé ; serveur injoignable ou erreur 5xx → accès interdit ;
- cadence lente, une requête toutes les deux à trois secondes par domaine ;
- en-tête `User-Agent` identifiable, avec un moyen de contact ;
- reprise sur erreur avec attente croissante, abandon après trois tentatives
  (erreur réseau, 429 et 5xx seulement ; `Retry-After` respecté) ;
- robots.txt revérifié à chaque redirection ;
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

# Extraction : seul le jeu d'évaluation existe pour l'instant (pas encore
# d'extraction par fabricant). Bloc alimentation, sur le PC (avec l'accord
# de Quentin). Par défaut Ollama local et qwen3:14b ; LLM_BASE_URL et
# LLM_MODEL les changent, Groq exige LLM_API_KEY et LLM_MODEL. Installé
# (pip install -e .), `catalog` remplace `python -m catalog.cli`.
python -m catalog.cli extract --jeu miseaupoint [--ids axis-03,hik-01] \
    [--executions 3] [--fournisseur ollama|groq] [--reflexion none|low|medium]

# Évaluation contre le corrigé, sans modèle (rapport dans eval/resultats/) :
# une exécution rejouée depuis les réponses brutes, ou la ligne de base
# par expressions régulières avec le rappel du découpage
python -m catalog.cli evaluate --run data/extractions/resultats/<dossier>
python -m catalog.cli evaluate --ligne-de-base --jeu miseaupoint
# Deux rapports comparés par bootstrap apparié (notices communes)
python -m catalog.cli evaluate --comparer eval/resultats/A.json eval/resultats/B.json

# Notices du jeu : retéléchargement et contrôle d'empreinte (vérification
# seule ; --archiver écrit dans data/sources/, avec l'accord de Quentin)
python -m catalog.cli recuperer [--ids axis-03]

# Prévu, pas encore construit (coquilles) : file de relecture, export du
# catalogue avec les niveaux de fiabilité, état par étape
streamlit run catalog/review/app.py
python -m catalog.cli export --out data/catalog.json
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

Aucun test n'appelle le réseau ni le modèle : le client et le modèle se
remplacent par des faux. `extract` occupe le GPU du PC ou le quota Groq
et se lance avec l'accord de Quentin.

### Extraction sur le PC

Le NAS n'a pas de GPU : les extractions tournent sur le PC Linux de
Quentin, qui a un clone du dépôt et une copie de `data/sources/`.

1. Ollama sur l'hôte, joignable depuis le conteneur et avec un contexte
   fixé : `OLLAMA_HOST=0.0.0.0 OLLAMA_CONTEXT_LENGTH=16384 ollama serve`,
   puis `ollama pull qwen3:14b`.
2. `docker compose up -d dev`, puis
   `docker exec -e LLM_BASE_URL=http://172.17.0.1:11434/v1 -e LLM_MODEL=qwen3:14b dev_catalog sh -c "cd /app && python -m catalog.cli extract --jeu miseaupoint --ids axis-03"`
   (`172.17.0.1` : passerelle du bridge Docker par défaut).
   La commande lit le contexte réel et le digest dans `/api/ps` et
   prévient si le modèle déborde de la VRAM.
3. Rapporter au NAS `data/extractions/` (`brut/` et `resultats/`) :
   `evaluate` y rejoue tout sans modèle. Ce dossier n'est pas versionné,
   il contient le texte des notices.

**Variante sans Docker** (le PC n'en a pas ; décision de Quentin le
2026-10-16, sans `uv.lock`) :

1. Environnement : `python3.12 -m venv .venv && .venv/bin/pip install -e . ruff mypy pytest`
   (`.venv/` est ignoré par git). Tests, ruff et mypy se lancent avec
   `.venv/bin/`. `recuperer`, `discover` et `acquire` exigent
   `SECURSCOPE_CONTACT` (contact du User-Agent), défini par le compose dans
   le conteneur : hors conteneur, l'exporter.
2. Ollama est un service systemd, joignable en local sans
   `OLLAMA_HOST=0.0.0.0`. Contexte fixé par `sudo systemctl edit ollama`
   (`Environment="OLLAMA_CONTEXT_LENGTH=16384"`), puis
   `sudo systemctl restart ollama`.
3. `.venv/bin/catalog extract --jeu miseaupoint` (Ollama local et
   `qwen3:14b` par défaut), puis
   `.venv/bin/catalog evaluate --run data/extractions/resultats/<dossier>`.
4. `data/sources/` se copie depuis le NAS (`rsync -a <hôte-nas>:<dépôt>/data/sources/ data/sources/`)
   plutôt que de se retélécharger : l'empreinte d'une page HTML change d'un
   téléchargement à l'autre, et `evaluate` retrouve un fichier par son
   empreinte. Contrôle : `recuperer` doit rendre 50/50 « present ».

## Structure

```
SecuExtractor/
├── CLAUDE.md
├── README.md                    # point d'entrée en anglais, résultats chiffrés
├── docs/
│   ├── pipeline.md              # le déroulé détaillé, à lire une fois
│   └── chantiers/               # plans de chantier et journal des décisions
│
├── catalog/
│   ├── cli.py                   # point d'entrée en ligne de commande
│   ├── acquisition/
│   │   ├── fetcher.py           # requests, repli playwright, cadence, reprises
│   │   ├── robots.py            # lecture de robots.txt selon la RFC 9309
│   │   ├── discovery.py         # recherche des pages catalogue et notices
│   │   ├── recuperation.py      # retéléchargement du jeu, contrôle d'empreinte
│   │   ├── manifest.py          # journal des fichiers : url, date, empreinte
│   │   └── adapters/
│   │       ├── generic.py       # cas courant, à essayer en premier
│   │       └── <fabricant>.py   # uniquement si le générique échoue
│   ├── reading/
│   │   ├── page.py              # modèle Page commun aux lecteurs, nettoyage du texte
│   │   ├── pdf_reader.py        # texte et tableaux depuis un PDF
│   │   ├── html_reader.py       # texte structuré depuis une fiche web
│   │   └── chunker.py           # découpage en sections exploitables
│   ├── extraction/
│   │   ├── cibles/              # champs visés par famille et bloc (repris de SecurScope)
│   │   ├── cible.py             # chargement des cibles, type d'une valeur
│   │   ├── client.py            # client compatible OpenAI (Ollama, Groq), reprises
│   │   ├── ollama.py            # contexte réel et digest du modèle (/api/ps)
│   │   ├── brut.py              # réponses brutes archivées et rejouées
│   │   ├── prompts.py           # gabarit, message et schéma strict par bloc
│   │   ├── citations.py         # contrôle de citation, sans modèle
│   │   ├── etats.py             # état final sur / douteux / absent d'un champ
│   │   └── runner.py            # orchestration d'un lot
│   ├── plausibility/
│   │   ├── rules.py             # règles de vraisemblance par champ
│   │   ├── regles_extraits.py   # règles qui confrontent une valeur à son extrait
│   │   ├── indices.py           # indices de consommation, calibre, typique
│   │   └── checker.py           # application des règles
│   ├── storage/                 # prévu (coquille)
│   │   ├── db.py                # SQLite, schéma et connexion
│   │   └── repository.py        # lecture et écriture des extractions
│   ├── review/                  # prévu (coquille)
│   │   └── app.py               # interface Streamlit de relecture
│   ├── export/                  # prévu (coquille)
│   │   └── writer.py            # export du catalogue vérifié
│   └── evaluation/
│       ├── notices.py           # jeu de notices, tirage, fichier archivé
│       ├── reference.py         # format du corrigé (eval/reference/)
│       ├── execution.py         # sous-commande extract sur le jeu
│       ├── evaluate.py          # sous-commande evaluate (rejeu, ligne de base, comparaison)
│       ├── rejeu.py             # rejeu des réponses brutes, sans modèle
│       ├── metriques.py         # comparaison au corrigé, taux, bootstrap
│       ├── comparaison.py       # bootstrap apparié entre deux rapports
│       ├── rapport.py           # eval/resultats/<nom>.json et .md
│       ├── decoupage.py         # rappel du découpage
│       └── ligne_de_base.py     # ligne de base sans LLM (regex)
│
├── eval/                        # jeu d'évaluation publié
│   ├── notices.csv              # 50 notices : URL, empreinte, jeu (miseaupoint / test)
│   ├── GUIDE.md                 # guide d'annotation
│   ├── reference/               # corrigé annoté, une notice par fichier
│   ├── prompts/                 # textes exacts des prompts mesurés
│   └── resultats/               # rapports d'évaluation (README.md : index)
│
├── tests/                       # tests unitaires, architecture, fixtures faites main
├── .github/workflows/ci.yml     # ruff, mypy, pytest à chaque push
├── Dockerfile, docker-compose.yml  # conteneur de développement dev_catalog
│
└── data/
    ├── sources/
    │   ├── <fabricant>/         # notices archivées, PDF et HTML
    │   ├── manifeste.json       # url, date, empreinte de chaque fichier
    │   ├── sites_manuels.json    # sites que la recherche n'a pas trouvés
    │   ├── catalogues_manuels.json  # pages catalogue à fournir
    │   ├── produits_manuels.json    # URL de produits à fournir
    │   └── echecs.json           # journal : quoi, où, quelle action attendue
    ├── extractions/             # réponses brutes et résultats d'extract, non versionnés
    ├── catalog.db               # SQLite, non versionné (prévu)
    └── catalog.json             # sortie, non versionnée (prévue)
```

Le dossier `data/sources/` n'est pas versionné mais il est **conservé**. Un
document supprimé rend invérifiables toutes les citations qui en dépendent.

## Le schéma d'extraction

**C'est SecurScope qui fixe, par ses besoins, les champs à extraire**
(décision du 2026-10-15). Le modèle de données de SecurScope (dépôt
privé) dit quels
attributs et quels ports chaque équipement porte, avec leurs clés anglaises
(`power_w_peak`, port `poe_pd` et son `class`…). Ce projet en reprend, par
famille et par bloc, une description courte dans
`catalog/extraction/cibles/<famille>_<bloc>.json` : clé SecurScope, unité,
définition, et le commit SecurScope d'où elle vient. Ces fichiers de cibles
sont la référence de l'extraction.

L'ancien schéma français `schema/specifications-equipements.json` (54
types) et `catalog/models.py`, qui en était généré, ont été supprimés le
2026-10-21 : ils n'étaient plus la référence et rien ne les importait.
L'historique git les garde.

Les champs qui alimentent un calcul de SecurScope (budget PoE, autonomie,
capacité, compatibilité d'alimentation) sont ceux dont l'exactitude compte le
plus. Un doute sur eux passe en `douteux` sans hésitation.

## Règles d'extraction — non négociables

1. **Citation obligatoire.** Toute valeur extraite porte son extrait source :
   fichier, page, et le texte exact d'où elle vient. Sans citation, la valeur
   est `douteux` quelle que soit la confiance du modèle.
2. **Jamais d'inférence.** Un champ absent de la notice reste `absent`. Le
   modèle ne calcule pas, ne déduit pas, ne complète pas par analogie avec un
   produit voisin. Seule exception : les bornes d'une tension à tolérance
   (« 12 V DC ± 25 % » → 9 et 15, `eval/GUIDE.md`), que le contrôle de
   citation recalcule.
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

Règles du bloc alimentation des caméras, dans `plausibility/rules.py`
(et `regles_extraits.py` pour celles qui lisent l'extrait cité)
(clés SecurScope ; tout échec met le champ en `douteux`). Les règles des
autres familles s'écriront avec leurs cibles, quand un chantier les ouvrira.

| Champ | Règle |
|---|---|
| `power_w`, `power_w_peak` | entre 1 et 200 W |
| `ports.poe.power_w` | entre 1 et 90 W ; ≤ plafond de la classe extraite (3,84 / 6,49 / 12,95 / 25,5 / 40 / 51 / 62 / 71,3 W ; classe et puissance du pire cas, GUIDE), sinon de la plus haute classe citée, 71,3 W sans classe citée (les deux si la classe est extraite) ; aucun plafond si la notice parle d'un PoE propriétaire (High PoE, Hi-PoE, injecteur, PoH) |
| `ports.poe.power_w` (extrait) | douteux si l'extrait porte un indice de typique (typ, basic, nominal, average, avg, moyen) et, sur la ligne de la valeur retenue, une puissance plus haute que ne précède ni calibre (injecteur, classe, norme…) ni autre alimentation (AC, DC) |
| `ports.poe.power_w` (extrait) | douteux si c'est la plus basse d'un couple « Max. A/B W » (chauffage ou IR en marche / à l'arrêt) |
| `ports.poe.class` et `min_standard` | cohérents : af ⇒ 0–3, at ⇒ 0–4, bt ⇒ 1–8, ou classe admise par une norme plus haute citée et dont le numéro est cité (classe du pire cas, GUIDE) (les deux) ; af avec plus de 12,95 W sans at ni bt cités (les deux) |
| `ports.dc.voltage_min_v`, `voltage_max_v` | dans {12, 24, 36, 48} ± 25 % ; min ≤ max et min ≥ max / 3 (les deux) ; 44–57 V avec un extrait qui parle de PoE |
| `ports.dc.current_standby_ma` | entre 20 et 2 000 mA ; ≤ `current_peak_ma` (les deux) ; jamais seul : sans `current_peak_ma`, douteux (un courant unique est le maximal) |
| `ports.dc.current_peak_ma` | entre 100 et 5 000 mA ; tension × courant entre 0,5 et 2 fois `power_w_peak` |
| `power_w`, `ports.poe.power_w` | ≤ `power_w_peak` (les deux) |
| `power_w` (extrait) | douteux si l'extrait, sans indice de typique, donne un couple de maximums « Max. A/B W » (chauffage ou IR en marche / à l'arrêt) et que la valeur est A ou B |
| `power_w_peak` | ≥ la plus forte consommation citée quand le texte cite plusieurs alimentations (PoE, DC, AC) ; consommation = valeur en W précédée sur sa ligne d'un indice (max, typical, approx, consumption), ou qui suit une telle valeur ; calibres exclus (midspan, injecteur, alimentation, transformateur, classe, norme, PoE propriétaire, switch, sortie) |
| `ports.dc`, `ports.poe` (extrait) | déclaré `false` alors que son propre extrait donne une tension continue chiffrée (hors 44–57 V et hors « output ») ou parle de PoE sans le nier (« PoE: N/A », « non-PoE ») ; « output » avant ou après la tension l'écarte |
| attributs d'un port | absents si le port n'est pas déclaré présent |

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

Les étapes d'envergure suivent le cycle commun aux projets de Quentin :
`/cadrage` → plan dans `docs/chantiers/`, un lot par session, `/verifier` après chaque étape, `/fin-de-lot` pour
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
- lancer une extraction réelle (`extract`) : elle occupe le GPU du PC ou le quota Groq.

Interdit sans exception : lire ou écrire un `.env`, `--no-verify`.

## Contexte détaillé

`docs/pipeline.md` — le déroulé complet du pipeline, les états d'un champ, et
la procédure d'ajout d'une nouvelle gamme.
