# Pipeline d'extraction — déroulé détaillé

## 1. Vue d'ensemble

```
Liste de fabricants
    │
    ├─► [0a] Recherche du site officiel
    │         échec ──────────────────────► URL fournie à la main
    │
    ├─► [0b] Recherche des pages catalogue et produit
    │         échec ──────────────────────► URL fournie à la main
    │
    ├─► [0c] Pour chaque produit :
    │         PDF trouvé ─────────────────► téléchargement + archivage
    │         pas de PDF ─────────────────► capture de la page produit
    │         ni l'un ni l'autre ─────────► saisie manuelle
    │
    ▼
Documents archivés (PDF ou HTML) + manifeste
    │
    ├─► [1] Lecture          texte + tableaux, page ou section web
    │
    ├─► [2] Découpage        sections identifiables (Power, Environment…)
    │
    ├─► [3] Extraction       un appel modèle par BLOC de champs
    │                        schéma étroit, citation obligatoire
    │
    ├─► [4] Plausibilité     règles de vraisemblance → `sur` ou `douteux`
    │
    ├─► [5] Stockage         SQLite, chaque champ avec son état
    │
    ├─► [6] Export           tout part en niveau `extrait`
    │
    └─► [7] Relecture        file priorisée, à la demande
              validation ───► le champ passe en `verifie`
```

Deux points d'attention structurent tout le reste.

**L'extraction se fait par bloc, jamais par type.** Un schéma de 35 champs fait
chuter la fiabilité ; cinq schémas de sept champs la préservent.

**La relecture n'est pas une étape du pipeline mais un processus continu.**
L'export a lieu sans elle : les données partent en niveau `extrait`, utilisables
mais signalées. La relecture les fait monter en `verifie` au fil de l'usage.
C'est ce découplage qui rend le volume atteignable.

## 1 bis. L'acquisition

### L'entrée est une liste de fabricants

```
data/fabricants.txt
    Dahua
    Hikvision
    Ajax Systems
    Paxton
    ...
```

Le module se débrouille à partir de là. Chaque étape qui échoue bascule sur la
suivante, et l'échec est journalisé pour que le complément manuel soit ciblé.

### La cascade, étape par étape

**[0a] Trouver le site officiel.** Recherche sur le nom du fabricant,
vérification sommaire que le domaine correspond bien au constructeur et non à
un revendeur. En cas d'échec ou d'ambiguïté, l'URL est demandée dans
`data/sources/sites_manuels.json`.

**[0b] Trouver les pages catalogue et produit.** Depuis la racine du site, on
repère les sections produit et on remonte les pages de référence individuelles.
C'est l'étape la plus fragile : elle dépend entièrement de la structure du
site. En cas d'échec, les URL de catalogue sont fournies à la main.

**[0c] Pour chaque page produit, chercher la meilleure source.** Dans l'ordre :

1. **Un PDF de notice** — le cas idéal, document figé et complet. Téléchargé,
   archivé, empreinte enregistrée.
2. **La page produit elle-même** — si aucun PDF n'est lié. La page est capturée
   en HTML et archivée. **Ce n'est pas un pis-aller** : beaucoup de fabricants,
   Ajax par exemple, ne publient leurs spécifications qu'en page web.
3. **Rien d'exploitable** — la référence est journalisée pour saisie manuelle.

### Pourquoi la page web est aussi importante que le PDF

Deux raisons.

**Le volume.** Télécharger et lire des dizaines de milliers de PDF prendrait un
temps déraisonnable et pèserait lourd en stockage. Une page produit se capture
en quelques secondes.

**La disponibilité.** Une part significative des fabricants ne publie plus de
fiche PDF, ou seulement pour une partie de leur gamme. S'en tenir aux PDF
reviendrait à amputer le catalogue sans raison.

Le PDF garde un avantage : il est figé. Une page web change, d'où l'archivage
systématique du HTML capturé et l'horodatage dans la citation.

### Générique puis adaptateur

`adapters/generic.py` traite le cas courant à chaque étape de la cascade. Un
adaptateur spécifique n'est écrit **qu'après un échec constaté** sur un
fabricant, et il hérite du générique en ne redéfinissant que ce qui diffère —
le plus souvent le repérage des pages produit.

Chaque adaptateur casse à la première refonte du site. Trois adaptateurs bien
choisis valent mieux que quinze écrits par anticipation.

### Requests puis Playwright

`requests` en premier : rapide, léger, suffisant pour la majorité des sites.
`playwright` en repli **automatique** quand la page revient vide ou
manifestement incomplète — signe d'un contenu injecté en JavaScript. Il est
lent, deux à cinq secondes par page contre une fraction de seconde, donc jamais
en mode par défaut. Le manifeste note quel outil a servi.

### Le manifeste

```json
{
  "fichier": "dahua/IPC-HDBW3441R-AS-P_datasheet.pdf",
  "url": "https://www.dahuasecurity.com/.../datasheet.pdf",
  "type_document": "pdf",
  "date_capture": "2026-09-03T14:22:11Z",
  "empreinte_sha256": "a3f1...",
  "outil": "requests",
  "statut": "archive"
}
```

L'empreinte détecte les mises à jour : au passage suivant, une empreinte
différente déclenche la réextraction de cette seule référence, l'ancienne
version étant conservée avec un suffixe de date.

### Journal des échecs

```json
{
  "fabricant": "Nedap",
  "etape": "0b_pages_catalogue",
  "raison": "Aucune section produit identifiée depuis la racine",
  "action_attendue": "Fournir l'URL du catalogue dans catalogues_manuels.json",
  "date": "2026-09-03T15:10:00Z"
}
```

`status` agrège ce journal : combien de fabricants bloqués, à quelle étape, et
ce qu'il faut fournir. **C'est ce qui rend le complément manuel supportable** —
tu sais exactement quoi renseigner au lieu d'explorer à l'aveugle.

### Cadence et politesse

- une requête toutes les deux à trois secondes par domaine ;
- `robots.txt` respecté, sans exception ;
- `User-Agent` identifiable, avec un moyen de contact ;
- reprise sur erreur avec attente croissante, abandon après trois tentatives ;
- aucun contournement de protection : un site qui bloque passe en manuel.

## 2. Les niveaux de fiabilité et les états d'extraction

Deux dimensions indépendantes, à ne pas confondre.

### Dimension 1 — le niveau de fiabilité, porté par le champ

| Niveau | Ce que c'est | Usage autorisé |
|---|---|---|
| `extrait` | Produit par le pipeline, jamais relu par un humain. | Tout, mais un calcul qui en dépend est marqué provisoire. |
| `verifie` | Relu et validé par un humain. | Tout, sans réserve. |

**Chaque champ porte son niveau, pas la référence.** Une caméra peut avoir une
puissance PoE `verifie` et une sensibilité `extrait`. C'est cette granularité
qui permet de relire ce qui compte sans relire le reste.

### Dimension 2 — l'état d'extraction, au sein du niveau `extrait`

Il indique la confiance du pipeline et détermine la place dans la file de
relecture.

**`sur`** — trois conditions cumulatives :
1. une valeur a été extraite ;
2. un extrait source est cité, et il contient bien la valeur ;
3. les règles de plausibilité passent.

**`douteux`** — dès qu'une des trois conditions échoue, ou que le modèle
signale un doute. Cas typiques :

- l'extrait cité ne contient pas la valeur annoncée (le modèle a paraphrasé) ;
- la valeur sort des bornes de plausibilité ;
- la notice donne plusieurs valeurs et le choix n'est pas évident ;
- l'unité est ambiguë ou absente ;
- la valeur concerne une variante de la gamme, pas la référence traitée.

**`absent`** — le champ n'existe pas dans la source. **Ce n'est pas une
erreur.** Beaucoup de fiches commerciales omettent le courant de repos : c'est
une information à chercher dans la notice d'installation, pas à inventer.

### Ce que voit l'utilisateur de l'application

| Situation | Comportement |
|---|---|
| Tous les champs du calcul en `verifie` | Résultat présenté sans réserve. |
| Au moins un champ en `extrait` | Résultat présenté, mais marqué provisoire, avec la liste des données non vérifiées. |
| Un champ obligatoire `absent` | Calcul impossible, le champ manquant est nommé. |

Le calcul se fait toujours quand c'est possible. Refuser de calculer parce
qu'une donnée n'a pas été relue serait pire que de calculer en le signalant.

## 3. Le découpage en blocs

Chaque type d'équipement est découpé pour l'extraction, indépendamment de la
structure du schéma final :

| Bloc | Champs typiques | Où les trouver dans une notice |
|---|---|---|
| `identification` | fabricant, référence, désignation, gamme | En-tête, première page |
| `alimentation` | tension, courant repos, courant alarme, PoE | Section « Power » |
| `environnement` | températures, IP, IK | Section « Environment » |
| `physique` | dimensions, poids, matériau, fixation | Section « Structure » |
| `metier` | les champs propres au type | Section « Technical Specification » |
| `accessoires` | requis, optionnels, compatibilité | Section « Ordering Information » |

Le bloc `accessoires` mérite une attention particulière : c'est lui qui permet
d'automatiser la nomenclature, et il est souvent présenté sous forme de tableau
d'options sans indication de ce qui est requis. En cas de doute sur le
caractère obligatoire d'un accessoire, le classer en optionnel et laisser la
relecture trancher.

## 4. La citation source

La citation prend **deux formes selon l'origine du document**, et le champ
`source` doit accepter les deux.

**Depuis un PDF** — la page suffit à retrouver l'information :

```json
{
  "valeur": 7.7,
  "etat": "sur",
    "niveau": "extrait",
  "source": {
    "type": "pdf",
    "fichier": "dahua/IPC-HDBW3441R-AS-P_datasheet.pdf",
    "page": 2,
    "extrait": "Max. (H.265+main stream/IR intensity+IR on): 6.4 W (12V DC); 7.7 W (PoE)"
  }
}
```

**Depuis une page web** — il n'y a pas de page, et le contenu peut changer.
L'horodatage devient la seule preuve, et le fichier archivé la seule garantie
de pouvoir revérifier :

```json
{
  "valeur": 260,
  "etat": "sur",
    "niveau": "extrait",
  "source": {
    "type": "html",
    "fichier": "ajax/hub-2-plus_specs_20260903.html",
    "url": "https://ajax.systems/products/specs/hub-2-plus/",
    "date_capture": "2026-09-03T14:22:11Z",
    "selecteur": "table.specs tr:nth-child(12)",
    "extrait": "Consommation en veille : 260 mA"
  }
}
```

Le `selecteur` est un confort de débogage, pas une garantie : il devient faux
dès que le site change. **C'est le fichier archivé qui fait foi**, jamais l'URL
vivante.

**La vérification de la citation est automatique** : si la valeur extraite
n'apparaît pas dans l'extrait cité — à la tolérance de formatage près — le
champ passe en `douteux`. C'est le garde-fou le plus efficace contre
l'invention, et il ne coûte rien.

## 5. Le stockage

SQLite, trois tables suffisent.

```
references
    id, fabricant, reference, type_equipement, fichier_source,
    date_extraction, statut  (en_cours | a_relire | validee | exportee)

champs
    id, reference_id, nom_champ, valeur, unite, etat,
    source_page, source_extrait, regle_echouee, usage

historique
    id, champ_id, ancienne_valeur, nouvelle_valeur, action, date
```

L'historique n'est pas un luxe : quand une valeur validée se révèle fausse six
mois plus tard, savoir qui l'a validée et sur quel extrait fait gagner du temps.

## 6. La relecture

Ce n'est pas une étape du pipeline mais un **processus continu**, qui tourne
indépendamment des extractions. L'interface traite une file priorisée, jamais
un lot complet — l'immense majorité des champs `extrait` ne sera jamais relue,
et n'a pas à l'être.

### La file, par ordre de priorité

1. **Gammes prioritaires** — les marques dominantes, choisies à la main. C'est
   le socle de qualité qu'on constitue en premier, avant toute mise en service.
2. **Références utilisées** — dès qu'une référence est posée dans un projet
   réel, ses champs `douteux` remontent, puis ses champs `sur`, par fréquence
   d'usage décroissante.
3. **Signalements** — un utilisateur conteste une valeur, elle repasse en tête.

Dans chaque strate, les champs `usage: calcul` passent avant les autres.

### L'écran de relecture

```
┌─────────────────────────────────────────────────────────────┐
│ courant_repos_ma          mA        [CALCUL]                │
│ alimente : autonomie_batterie, bilan_consommation           │
│ utilisée dans 3 projets                                     │
│                                                             │
│ Valeur proposée : 3200          état : douteux              │
│ ⚠ Règle échouée : attendu entre 1 et 2000 mA               │
│                                                             │
│ Extrait source, page 2 :                                    │
│   « Basic: 3.2W (12 V DC); 3.9 W (PoE) »                   │
│                                                             │
│ [ Valider ]  [ Corriger : ____ ]  [ Marquer absent ]        │
└─────────────────────────────────────────────────────────────┘
```

Cet exemple est réel et illustre exactement ce que la relecture rattrape : le
modèle a lu 3,2 W et l'a converti en 3 200 mA, ce qui n'a aucun sens — une
puissance n'est pas un courant. La règle de plausibilité attrape l'aberration,
l'extrait source rend l'erreur évidente en une seconde, et le relecteur corrige
en calculant 3,2 W ÷ 12 V ≈ 267 mA.

Toute action fait passer le champ en niveau `verifie`, et l'avertissement
disparaît chez tous les utilisateurs.

**L'objectif de temps se mesure par champ, pas par référence** : quelques
secondes pour un cas évident. Si l'interface impose plus de deux clics pour
trancher, c'est elle qu'il faut corriger.

## 7. L'export

**Tous les champs sont exportés**, avec leur niveau de fiabilité. C'est le
changement le plus important par rapport à un pipeline classique : on n'attend
pas la relecture pour livrer.

```json
{
  "version": "1.0",
  "date_export": "2026-09-15",
  "references": [
    {
      "fabricant": "Dahua",
      "reference": "DH-IPC-HDBW3441R-AS-P",
      "type_equipement": "camera_dome",
      "champs": {
        "puissance_poe_w": { "valeur": 7.7, "niveau": "verifie" },
        "poe_classe": { "valeur": "3", "niveau": "extrait" },
        "sensibilite_lux": { "valeur": null, "niveau": "absent" }
      },
      "sources": {
        "puissance_poe_w": {
          "type": "pdf",
          "fichier": "dahua/IPC-HDBW3441R-AS-P_datasheet.pdf",
          "page": 2
        }
      }
    }
  ]
}
```

L'application lit le niveau de chaque champ et adapte son comportement : un
calcul qui consomme un champ `extrait` affiche un avertissement nommant la
donnée concernée.

Les sources voyagent avec les données. C'est ce qui permet d'afficher d'où
vient une valeur quand un utilisateur la conteste — et il la contestera.

## 8. Ajouter un fabricant

1. Ajouter son nom à `data/fabricants.txt`.
2. Lancer `discover`. Le module cherche le site, les pages catalogue, les pages
   produit, et pour chacune la meilleure source disponible.
3. Lire le journal des échecs : quels fabricants bloqués, à quelle étape, et ce
   qu'il faut fournir.
4. Compléter les fichiers manuels correspondants — site, catalogue ou URL de
   produit selon l'étape en échec.
5. Lancer `acquire`, puis `extract`. (Au 2026-10-16, `extract` ne
   traite que le jeu d'évaluation, `--jeu` ; l'extraction par fabricant
   reste à écrire.)
6. **Exporter immédiatement.** Les données partent en niveau `extrait`, elles
   sont utilisables tout de suite.
7. La relecture suit son cours, indépendamment : gammes prioritaires d'abord,
   puis ce que l'usage fait remonter.

**L'étape 6 est le point important.** Rien n'attend la relecture. Un fabricant
extrait aujourd'hui est disponible aujourd'hui, avec ses avertissements.

**Ne pas chercher à automatiser l'étape 4.** Renseigner dix URL à la main prend
cinq minutes ; rendre la découverte exhaustive sur un site récalcitrant prend
des heures et casse à la prochaine refonte.

## 9. Ce qui reste manuel, et le restera

- Le choix des gammes prioritaires à relire en premier.
- Les URL que la découverte n'a pas su résoudre.
- L'arbitrage des valeurs douteuses.
- La décision qu'un accessoire est requis plutôt qu'optionnel.
- L'écriture d'un adaptateur, quand un site résiste durablement.

Ces points sont ceux où l'expertise métier a le plus de valeur. Le pipeline
existe pour les dégager du bruit, pas pour les remplacer.

**Et c'est précisément ce que le découplage permet** : sans lui, il faudrait
relire des dizaines de milliers de références avant de livrer quoi que ce soit.
Avec lui, le volume arrive d'un coup et la qualité monte là où elle sert.
