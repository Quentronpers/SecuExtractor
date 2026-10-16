# Chantier eval-alimentation — extraction mesurée du bloc alimentation des caméras IP

> Statut : **validé par Quentin le 2026-10-15** (relu par `expert-metier`
> et `architecte-llm` le même jour). L1, L1 bis et L2 terminés le 2026-10-16
> (L2 non commité à la rédaction) ; prochain lot : L3a (client et réponses
> brutes).
> Sert l'étude de cas de la phase 2 de la recherche d'emploi
> (vault : `projets/AI-Solutions-Engineer`), du 2026-10-15 au 2026-11-15.

## 1. Le besoin

Faire tourner l'extraction pour de vrai sur une seule famille, les caméras
IP, et sur un seul bloc, l'alimentation, **et prouver par des chiffres ce
qu'elle vaut**. Pas « ça a l'air de marcher » : un jeu de 50 notices réelles
dont on connaît la bonne réponse, un script qui compare, et des métriques
qu'on peut rejouer à chaque changement de prompt ou de modèle.

Le résultat doit tenir debout devant un client industriel : un modèle
**local**, sans coût par appel et sans donnée qui sort, comparé à un gros
modèle hébergé, avec l'écart chiffré.

## 2. Décisions

| Décision | Pourquoi |
|---|---|
| **Périmètre : `camera_dome`, `camera_tube`, `camera_ptz`**, bloc alimentation. `camera_thermique` exclue. | Les trois types portent les mêmes champs d'alimentation dans SecurScope (`video.camera.fixed`, `video.camera.ptz`). Les PTZ apportent les cas durs (802.3bt, 24 V AC, chauffage). |
| **Les champs cibles sont ceux du modèle SecurScope** (décision de Quentin, 2026-10-15), pas ceux de `schema/specifications-equipements.json`. Onze champs : présence des ports `poe` et `dc` (2 booléens) ; attributs de la caméra `power_w` (typique) et `power_w_peak` (maximale, IR + chauffage + moteur) ; port `poe_pd` : `class`, `power_w` (pire cas en PoE), `min_standard` ; port `power_dc_in` : `voltage_min_v`, `voltage_max_v`, `current_standby_ma`, `current_peak_ma`. | Le but est que la donnée extraite entre telle quelle dans SecurScope : `power_w_peak` alimente la règle `poe_budget` (Σ ≤ 80 % du budget du switch), les tensions du port DC servent au contrôle de compatibilité avec l'alimentation. Les courants sont presque toujours absents des fiches caméra : ils mesurent si le modèle invente un courant à partir des watts (règle 5 de CLAUDE.md). |
| **Ces 11 champs sont décrits dans `catalog/extraction/cibles/camera_alimentation.json`** (clé SecurScope, unité, définition reprise du modèle, commit SecurScope d'origine). Le schéma français n'est pas touché ; le réaligner sur SecurScope est un chantier à part (§6). | SecurScope est privé et vit ailleurs : le projet ne peut pas le lire en CI, sur le PC ni dans le dépôt public. Une description courte, datée et sourcée suffit. |
| **Corrigé annoté par Claude, relu par Quentin** (changé le 2026-10-16, faute de temps de Quentin ; prévu d'abord : annoté à la main par Quentin). Claude a lu chaque notice et cité page et extrait ; les champs dont il n'est pas sûr sont en `douteux` et Quentin les tranche, puis contrôle entièrement quelques notices tirées au hasard (à la place de la réannotation). Publié tel quel dans les limites. | Les modèles évalués (Ollama, Groq) ne sont pas Claude : le corrigé reste indépendant d'eux. Risque assumé : un LLM annotateur peut partager les erreurs de lecture d'un LLM extracteur ; la relecture des `douteux` et le contrôle aléatoire le mesurent. |
| **Jeu de mise au point (15) et jeu de test (35)**, tirés au hasard dès L1, stratifiés par type et fabricant. Le prompt ne s'ajuste que sur les 15 ; le test est mesuré une fois par version de prompt et son empreinte est enregistrée. | Sans cette séparation, on ajuste le prompt au corrigé et les chiffres publiés sont flatteurs. |
| **Modèle principal local** : Ollama sur le PC de Quentin (GPU 16 Go), `qwen3:14b` comme premier candidat. **Comparaison** avec un gros modèle ouvert gratuit sur **Groq** (confirmé par Quentin). | Coût nul, données qui ne sortent pas : l'argument qui compte chez un industriel. La comparaison donne le plafond atteignable. |
| **Un seul client, compatible OpenAI** (`/v1/chat/completions`), paramétré par URL, modèle et clé, appelé avec `requests` (déjà en dépendance). Sortie structurée par **un seul schéma JSON au format strict** (tous les champs `required`, `additionalProperties: false`, nullables en `["number", "null"]`), validée par Pydantic. | Ollama et Groq exposent la même API ; le format strict est le plus petit commun dénominateur des deux. Changer de modèle reste un paramètre. |
| **Chaque réponse brute est enregistrée** (requête, corps, réflexion, `finish_reason`, `usage`, durée) sous une clé d'empreinte (modèle, prompt, texte envoyé, paramètres, n° d'exécution). `evaluate` rejoue citations, plausibilité et métriques **depuis ces réponses, sans GPU, sur le NAS**. | Le GPU et le quota Groq sont rares ; la logique de contrôle change souvent. On n'interroge le modèle qu'une fois par configuration. |
| **Les extractions tournent sur le PC (Linux)**, le développement reste sur le NAS. Le PC a un clone du dépôt et une copie de `data/sources/` ; le conteneur joint l'Ollama de l'hôte par `host.docker.internal` (déclaré `host-gateway` dans le compose, nécessaire sous Linux). Réponses brutes et résultats reviennent au NAS. | Choix de Quentin. Le NAS n'a pas de GPU. |
| **Les cas ambigus sont tranchés dans `eval/GUIDE.md`**. Le corrigé porte, en plus de la valeur, l'**état attendu** et une **note hors modèle** (« 24 VAC », « chauffage inclus »). | Le modèle SecurScope ne prévoit pas tout (24 V AC, par exemple) : le corrigé garde la trace de ce qui ne rentre pas. |
| **CLAUDE.md, « Stack »** : « API Anthropic, traitement par lots » devient « modèle compatible OpenAI : Ollama en local, Groq en comparaison ». | La doc ne doit pas mentir. Modifiée au lot L3c. |
| **Résultats d'extraction en JSON** (`data/extractions/`), pas encore en SQLite. | Le stockage SQLite, la relecture et l'export sont un autre chantier : ne pas rouvrir tout le projet. |
| **Une notice = une référence**, suffixe compris (-I, -Z, -H). La référence visée est passée au modèle. | Sans cela, la « bonne réponse » est ambiguë et la mesure ne vaut rien. |
| **Rien de redistribué** : le dépôt public contient les annotations, l'URL et l'empreinte SHA-256 de chaque notice, jamais le PDF ni son texte. | CLAUDE.md, « Cadre à respecter ». L'empreinte permet à chacun de vérifier qu'il a le même document. |

**Exclu** : les autres blocs et familles, SQLite, la relecture Streamlit,
l'export, le format d'import SecurScope, l'automatisation de la découverte
(les 50 URL sont fournies à la main dans `produits_manuels.json`).

## 3. Modules et interfaces

```
eval/                              # versionné, public
├── GUIDE.md                       # règles d'annotation (cas ambigus tranchés)
├── notices.csv                    # id, fabricant, reference, type, url, format, sha256, jeu (miseaupoint|test)
├── reference/<id>.json            # corrigé de Quentin (protégé par hook)
└── resultats/<date>_<modele>_<prompt>.json   # sorties de `evaluate`, versionnées

catalog/
├── reading/pdf_reader.py          # lire(chemin) -> list[Page]  (texte + tableaux, n° de page)
├── reading/html_reader.py         # lire(chemin) -> list[Page]  (une « page » par section titrée)
├── reading/chunker.py             # selectionner(pages, bloc) -> list[Page]
├── extraction/cibles/camera_alimentation.json   # les 11 champs SecurScope visés
├── extraction/client.py           # ClientCompatibleOpenAI(url, modele, cle?).completer_json(...)
├── extraction/brut.py             # enregistrement et relecture des réponses brutes (data/extractions/brut/)
├── extraction/prompts.py          # gabarit("camera", "alimentation") + VERSION_PROMPT
├── extraction/citations.py        # verifier_citation(champ, valeur, extrait, pages) -> motif | None
├── extraction/runner.py           # extraire_document(...) -> ResultatBloc
├── plausibility/rules.py          # règles des 11 champs, y compris les cohérences entre champs
└── evaluation/
    ├── reference.py               # modèle Pydantic du corrigé, chargement de eval/
    ├── metriques.py               # comparaison valeur à valeur, agrégats, bootstrap
    └── rapport.py                 # écrit eval/resultats/*.json et un résumé Markdown
```

- `catalog.evaluation` rejoint la liste `DOWNSTREAM` du test
  d'architecture : il n'importe pas l'acquisition, l'empreinte est lue
  dans `manifeste.json` comme une donnée.
- Une section HTML tient lieu de page : son titre va dans
  `SourceHTML.selecteur`, le modèle cite le numéro de section.
- Sous-commandes : `extract --notices eval/notices.csv --jeu <miseaupoint|test>
  --modele <nom> --executions 3` (sur le PC) et `evaluate --run <dossier>`
  (partout, sans modèle).
- Configuration par variables d'environnement (`.env`, jamais lu par
  Claude) : `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` (Groq seulement).

### Pièges des fournisseurs (vérifiés par `architecte-llm` le 2026-10-15)

- **Ollama tronque sans prévenir** : contexte par défaut de 4k jetons sous
  24 Go de VRAM, non réglable par requête sur `/v1`. On fixe
  `OLLAMA_CONTEXT_LENGTH` côté serveur, on l'enregistre, et toute réponse
  `finish_reason=length` (ou dont `usage.prompt_tokens` trahit une
  troncature) compte comme **échec**, jamais comme `absent`. `ollama ps`
  vérifie que le modèle ne déborde pas sur le processeur.
- **Mode « thinking » de qwen3** : réglé explicitement (`reasoning_effort`
  sur `/v1`), mesuré comme une variable de l'expérience. Ses jetons
  consomment le budget de sortie.
- **Groq** : le mode strict n'existe que sur certains modèles (à vérifier
  au L5) ; quota gratuit de l'ordre de quelques milliers de jetons par
  minute et 200k par jour, donc 50 notices × 3 exécutions s'étalent sur
  plusieurs jours. `max_completion_tokens` relevé.

### Le contrôle de citation, déterministe

Le modèle rend pour chaque champ : `valeur`, `page`, `extrait`, `doute`.
Le code vérifie ensuite, sans modèle, **sur le texte exact envoyé au
modèle** (normalisé : NFKC, espaces insécables et fines, tirets, coupures
de fin de ligne, casse) :

1. l'extrait se retrouve dans la page citée ; sinon `citation_introuvable`.
   Si ses fragments sont présents mais séparés (tableau mal linéarisé que
   le modèle a recollé) : `citation_recomposee`, compté à part ;
2. la valeur apparaît dans l'extrait **comme nombre entier délimité**
   (« 7.7 » ne valide pas « 17.7 W ») **avec son unité accolée** (W, V,
   mA, A) ; sinon `valeur_hors_extrait`. Booléens, normes et classes ont
   une règle par champ (« PoE+ » = 802.3at, « Class 4 » = 4, table fermée ;
   « PoE++ », « Hi-PoE » hors table) ;
3. les règles de plausibilité passent.

Les trois conditions remplies, sans doute signalé → `sur` ; sinon `douteux`
avec le motif dans `regle_echouee`. Pas de valeur → `absent`.

**Limite connue, annoncée** : dans « 6,4 W (12V DC) ; 7,7 W (PoE) », les
deux valeurs passent le contrôle. Prendre la valeur DC pour la PoE, ou la
colonne d'une référence voisine, n'est pas attrapé par la citation : c'est
la mesure qui dira combien de fois cela arrive.

### Règles de plausibilité (proposées par `expert-metier`, adaptées au modèle SecurScope)

- Tensions du port DC autour de {12, 24, 36, 48} V ± 25 % (les tensions
  d'alimentation continue de SecurScope, plus 36 V vu sur des PTZ) ;
  `voltage_min_v` ≤ `voltage_max_v`, et min ≥ 0,6 × max.
- Une tension entre 44 et 57 V dont l'extrait parle de PoE → `douteux` :
  c'est la tension côté switch, pas une entrée DC de la caméra.
- `min_standard` et `class` cohérents : af ⇒ 0–3, at ⇒ 0–4, bt ⇒ 1–8.
- Port `poe.power_w` ≤ plafond côté caméra de la classe
  (12,95 / 25,5 / 40 / 51 / 62 / 71,3 W) ; entre 1 et 90 W sinon.
- `power_w` ≤ `power_w_peak` ; `poe.power_w` ≤ `power_w_peak`.
- Port PoE absent ⇒ `class`, `min_standard`, `poe.power_w` absents ; port
  DC absent ⇒ tensions et courants absents.
- Tension, courant et puissance tous connus : V × I entre 0,5 et 2 fois la
  puissance (attrape une confusion A / mA) ; courant < 20 mA sous 12 V →
  `douteux`.

## 4. Comment on mesure

Comparaison champ par champ avec le corrigé, **à l'identique après
normalisation** (unités, séparateur décimal) ; `class` en chaîne. Un
écart à 1 % près est publié comme indicateur à part, jamais compté juste.
Toute valeur non `absent` compte comme produite, quel que soit son état ;
une valeur fausse sur un champ présent au corrigé compte à la fois comme
faux positif et comme faux négatif.

| Métrique | Définition | Ce qu'elle prouve |
|---|---|---|
| **Précision** | valeurs justes / valeurs produites | quand il répond, il a raison |
| **Précision des `sur`** | valeurs justes / valeurs produites en `sur` | ce que l'application consommera sans réserve |
| **Rappel** | valeurs justes / valeurs présentes au corrigé | il trouve ce qui existe |
| **Exactitude** | cellules justes (absent compris) / 11 × notices | vue d'ensemble |
| **Invention**, par champ | champs absents au corrigé mais remplis / champs absents au corrigé | il n'invente pas (règle 2) |
| **Sous-estimation de `power_w_peak` et `poe.power_w`** | valeurs produites < corrigé / valeurs produites | la faute qui fait choisir un switch trop petit (règle `poe_budget` de SecurScope), comptée à part de la surestimation |
| **Citations** | `citation_introuvable` et `citation_recomposee` / valeurs produites | garde-fou contre l'invention |
| **Tri `douteux`** | erreurs marquées `douteux` / erreurs totales | le principe du projet : les erreurs vont en relecture |
| **Échecs techniques** | troncatures, JSON invalide, erreurs HTTP | robustesse |
| **Coût et latence** | secondes par notice, jetons ; coût nul en local, quota Groq | faisabilité à l'échelle |

**Rigueur** :
- température 0 et `seed` fixe en local ; **3 exécutions** par
  configuration, moyenne et écart min–max ;
- **intervalles de confiance à 95 % par bootstrap** en rééchantillonnant
  les notices (pas les cellules) ; comparaisons entre modèles par
  bootstrap apparié. Sur 35 notices de test, l'intervalle est de l'ordre
  de ±10 points : c'est écrit dans les limites ;
- **effectifs publiés par champ** (les courants et `poe_supporte = faux`
  reposent sur peu de cas) ;
- chaque résultat enregistre : empreinte du modèle (`/api/show`),
  quantification, version d'Ollama, contexte, réglage de réflexion,
  empreinte du prompt, commit, empreintes du corrigé et du jeu de test.

**Le chantier a réussi** quand ce tableau existe sur le jeu de test pour au
moins deux modèles locaux et un modèle Groq, rejouable par une commande,
avec une analyse d'erreurs (catégories, exemples cités). Objectifs
indicatifs pour le meilleur modèle local, à confirmer après la première
mesure : précision ≥ 90 % sur `power_w_peak`, invention ≤ 2 %, tri
`douteux` ≥ 80 % des erreurs.

## 5. Lots

### L1 — Jeu de notices et format du corrigé
- 50 notices publiques, au moins 8 fabricants. Ce que chacun apporte
  (`expert-metier`) : Hikvision (± 25 %, Hi-PoE, suffixes), Dahua (DC et
  PoE distincts, ePoE, 36 V DC sur PTZ), Axis (PoE seul, typique/max, High
  PoE contre bt), i-PRO (courants donnés, classe 0, « approx. »), Hanwha
  (PTZ 24 V AC et PoE+), Bosch (24 V AC, VA, midspan propriétaire),
  Uniview, Milesight, Vivotek ou Mobotix (classe seule), Ajax (page web
  seule). Environ 20 dômes, 20 tubes, 10 PTZ, une dizaine en HTML.
- **Au moins 3 notices pour chaque piège** : courant donné, PoE seul,
  24 V AC seul, classe sans norme, chauffage, multi-références, > 90 W.
- **Écarts constatés au choix des notices (2026-10-15, validés par
  Quentin)** :
  - *classe sans norme* : aucune notice constructeur ne donne une classe
    sans la norme (dix fabricants du jeu, plus Pelco, Avigilon, Vicon,
    Arecont et Canon lus) ; piège abandonné, publié dans les limites. La
    règle « norme absente » reste testée par les PoE propriétaires
    (Hi-PoE, High PoE, HPoE) ;
  - *24 V AC seul* : redéfini comme « pas d'entrée continue » (24 V AC
    seul ou avec PoE) ; 5 notices. Une caméra 24 V AC **ou** DC est un
    cas « deux tensions » (`eval/GUIDE.md`) ;
  - 12 PTZ et 18 tubes au lieu de 10 et 20 : les PTZ portent 24 V AC,
    > 90 W et chauffage ;
  - Ajax exclu (403 sur les pages produit, ABUS de même) : les 10
    notices HTML viennent de fabricants qui publient aussi des PDF ;
  - hik-02 et hik-03 passent en PDF (pages hikvision.com derrière un défi
    anti-robot, non contourné) et hik-02 vise la DS-2CD2387G2-LUK (PDF de
    la -LU en 403) ; ipro-01 retrouvée à sa nouvelle URL ;
  - `robots.txt` lu selon la RFC 9309 (choix de Quentin) : un 4xx, dont
    les 401/403 des stockages S3 et Azure sans `robots.txt` (Hikvision,
    Bosch, Hanwha), autorise ; injoignable ou 5xx interdit tout le domaine
    pour la session.
- `acquire` archive le document exact de chaque URL de
  `produits_manuels.json` (PDF tel quel, page HTML elle-même, aucun lien
  suivi) et respecte le `Crawl-delay` de `robots.txt` (100 s chez Dahua).
- `produits_manuels.json`, puis `acquire` ; `eval/notices.csv` avec
  l'empreinte du manifeste et le tirage mise au point / test. Un site qui
  bloque (souvent Hikvision ; Dahua, Hanwha et Bosch en JavaScript) : la
  notice est remplacée, jamais contournée.
- `catalog/extraction/cibles/camera_alimentation.json` (les 11 champs,
  repris du modèle SecurScope avec son commit).
- `eval/GUIDE.md`, avec les règles de `expert-metier` traduites dans le
  modèle SecurScope :
  - « 12 V DC ± 25 % » → `voltage_min_v` 9, `voltage_max_v` 15 ;
    « 12 V DC » seul → min = max = 12 (la seule tension déclarée) ;
  - jamais 48 ou 57 V venant du PoE dans les tensions du port DC ;
  - 24 V AC seul → port DC absent, note « 24 VAC » ; VA ≠ W ;
  - `power_w_peak` = la plus haute consommation annoncée, toutes
    alimentations confondues, IR, chauffage et moteur compris ;
    `power_w` = la typique, absente si la fiche n'en donne qu'une ;
    `poe.power_w` = le pire cas annoncé **en PoE** ;
  - « 6,4 W (12V DC) ; 7,7 W (PoE) » → `power_w_peak` 7,7,
    `poe.power_w` 7,7 ;
  - « PoE+ » = 802.3at ; « Class 4 » = 4 ; classe seule → `min_standard`
    absent ; Hi-PoE et autres PoE propriétaires → port PoE présent,
    `min_standard` absent ;
  - A → mA permis, W → mA jamais ; une valeur unique de courant va dans
    `current_peak_ma` (décidé le 2026-10-15 : les fiches la donnent avec
    la puissance maximale), typique + max dans les deux champs ;
  - `power_w_peak` garde le 24 V AC (décidé le 2026-10-15) ; le budget PoE
    de SecurScope lira `ports.poe.power_w` d'abord (piste notée dans la
    fiche SecurScope du vault) ;
  - fiche multi-références : la ligne de la référence complète, sinon
    absent.
- Modèle Pydantic du corrigé (`catalog/evaluation/reference.py`) ;
  `catalog.evaluation` ajouté au test d'architecture.
- Tests : un corrigé valide se charge ; valeur hors énumération, champ
  inconnu, page manquante pour une valeur présente → refusés ; identifiants
  uniques ; tirage stratifié reproductible (graine fixe).

### L1 bis — Annotation (Claude le 2026-10-16, relecture Quentin)
50 fichiers `eval/reference/<id>.json` écrits par Claude (`annotateur:
"Claude"`), 50/50 valides, chaque extrait retrouvé dans sa page (sauf
unv-02, archive HTML mal décodée). Les 20 champs `douteux` ont été
tranchés par Quentin le 2026-10-16 (règles ajoutées au GUIDE : typique en
PoE, maximum global reporté en PoE, tolérance après le courant ignorée,
calibre d'alimentation ≠ consommation). Contrôle complet par Quentin de
5 notices tirées au hasard (graine 20261016 : axis-09, bosch-03,
mobotix-03, unv-02, vivotek-03), soit 55 cellules : aucun écart. À
publier avec cette taille d'échantillon (5 notices sur 50 ne prouvent pas
un corrigé sans faute). Un validateur signale les fichiers malformés.

### L2 — Lecture des documents (fait le 2026-10-16)
- `pdf_reader` : texte et tableaux par page. `html_reader` : sections
  titrées, tableaux de spécifications compris. `chunker` : pages ou
  sections du bloc alimentation (Power, PoE, Consumption, Alimentation…),
  repli sur le document entier s'il est court.
- Tests : petits fichiers construits à la main dans `tests/fixtures/`,
  jamais de notice constructeur.

**Réalisé.**
- `catalog/reading/page.py` : modèle `Page(numero, texte, titre)` commun
  aux deux lecteurs ; `nettoyer()` remplace les caractères de contrôle
  (`\x01` chez Hanwha, mais toute la plage) par des espaces et réduit les
  espaces ordinaires ; les insécables sont gardées.
- `pdf_reader.lire(chemin) -> list[Page]` : tolérance horizontale de
  1,5 pt (3 collait les mots Axis, « Typical4.8W ») ; deux colonnes
  détectées par une gouttière vide centrée (milieu entre 0,42 et 0,58 de
  la largeur ; une gouttière décentrée est l'écart libellé/valeur d'un
  tableau, on ne coupe pas) ; si au moins 5 caractères différents se
  superposent, lecture dans l'ordre du flux PDF (Vivotek SD9364) ;
  tableaux pdfplumber d'au moins 3 cellules remplies ajoutés sous le
  texte en lignes « a | b | c », l'en-tête des modèles étant repris d'une
  page précédente pour un tableau de même largeur (Milesight).
- `html_reader` : sections par titre h1-h6 et par ligne de groupe de
  tableau (« Power » chez Dahua) ; rangées « libellé | valeur » ; cellule
  `rowspan` répétée sur chaque rangée (Hanwha) ; sections vides et
  doublons exacts retirés ; encodage déclaré respecté.
- `chunker.selectionner(pages, bloc)` : score = nombre de motifs du bloc
  présents (alimentation seulement, tout autre bloc lève `ValueError`),
  seuil 2, au plus 4 pages, document de 6 000 caractères ou moins envoyé
  entier.
- `fetcher.decoder()` : charset HTTP s'il existe, sinon encodage déclaré
  ou détecté (`UnicodeDammit`). Avant, `requests` supposait Latin-1 et
  l'archive unv-02 contenait « Â± ». unv-02 réarchivée avec l'accord de
  Quentin : l'ancienne entrée du manifeste passe en statut « remplace »
  avec un motif (le fichier reste sur disque), nouvelle empreinte
  `856b0f94…` dans `eval/notices.csv` et `eval/reference/unv-02.json`.
- Corrigé (accord de Quentin), valeurs inchangées : 4 extraits refaits
  (bosch-03 `power_w` et `power_w_peak`, vivotek-06 `power_w_peak` et
  `ports.poe.power_w`), les anciens venant de colonnes mêlées par la
  lecture par défaut ; bosch-03 : référence MIC-7502 corrigée en
  MIC-7522-Z30BR (faute de frappe) ; note `ports.poe` de vivotek-06
  mise à jour ; règle datée ajoutée à `eval/GUIDE.md` (« Fiche
  multi-références illisible ») : une ligne sans préfixe de modèle vaut
  pour chaque référence de la fiche (Vivotek SD9364 : 81,8 W vaut pour
  l'EH).
- Tests : 109 verts, ruff et mypy propres. `tests/fabrique_pdf.py` (petits
  PDF sans dépendance, Helvetica standard), `test_pdf_reader.py`,
  `test_html_reader.py` + `fixtures/fiche_produit.html`,
  `test_chunker.py`, 2 tests de `decoder()`. Aucune notice constructeur.

**Mesures** (scripts de banc hors dépôt, aucun fichier de résultats
versionné).
- Extraits du corrigé retrouvés dans la page lue (espaces ignorés) : PDF
  294/294 (286/294 avec pdfplumber par défaut, avant correction des 4
  extraits), HTML 82/82 (77/82 avant le réarchivage d'unv-02).
- Rappel du découpage : 376/376 valeurs du corrigé ont leur page ou
  section sélectionnée ; 4 400 caractères envoyés en moyenne par notice,
  16 000 au maximum (bosch-03).
- **Biais à publier dans les limites** : ces réglages ont été vérifiés sur
  les 50 notices, jeu de test compris. Seul le rappel est mesuré et rien
  n'a été réajusté après coup, mais les seuils ont été choisis en
  regardant ces notices.

**Contrôle hors jeu** (demandé par Quentin : des règles par marque, est-ce
de la triche ?). Aucune règle n'est propre à une marque (les noms ne sont
que dans les commentaires) : chacune se déclenche sur une condition
observable (caractère de contrôle, géométrie, `rowspan`). Mais les seuils
ont été réglés sur ces notices ; lecteur et découpage ont donc été passés,
sans rien retoucher, sur 10 documents jamais vus de 7 fabricants absents
du jeu (Pelco, Avigilon, Vicon x3 dont un en espagnol, Canon en français,
Grandstream en PDF et en HTML, TP-Link en HTML x2), archivés par
l'acquisition normale (`data/sources/<fabricant>/`, non versionnés).
Sélection 10/10 (la page d'alimentation est toujours retenue, y compris en
espagnol et en français) ; lisibilité 9/10. Défaut : Pelco, tableau sans
traits dont les libellés tiennent sur deux lignes, la valeur s'intercale
(« Environmental / PoE 13 W max / Dome »), même famille que Bosch « typ- /
ical » : limite connue, non corrigée (il faudrait un autre jeu frais pour
la mesurer). Avigilon : deux colonnes de valeurs mêlées sur les lignes de
comportement IR, pas sur la puissance. TP-Link : la page se contredit
(classe 0 / classe 4), problème de source. Ce contrôle ne vérifie que la
lecture et la sélection, pas l'extraction (pas de corrigé pour ces 10).

**À retenir pour la suite.**
- L4 : les noms de section HTML du corrigé sont parfois un libellé de
  rangée (i-PRO « Power Source and Power Consumption », Hanwha « Input
  Voltage ») alors que le lecteur titre la section par l'en-tête
  (« General », « Environmental & Electrical ») : mesurer le rappel du
  découpage en cherchant l'extrait du corrigé dans les sections
  sélectionnées, pas par le titre.
- `find_tables` de pdfplumber a besoin de traits : les tableaux sans
  traits restent lus en texte.
- Le lecteur ne transforme jamais une valeur.
- Remarque d'`expert-metier` non retenue (Quentin garde `sur`) : bosch-03
  `power_w_peak` 70 W est une valeur typique avec illuminateur, et les
  courants de la même page (environ 1,5 A sous 56 V) laissent attendre
  plus.

### L3a — Client et réponses brutes
- `client` compatible OpenAI : schéma strict, `finish_reason` contrôlé,
  reprise sur 429 avec attente croissante, délai d'expiration. `brut` :
  enregistrement et relecture par clé d'empreinte.
- Tests avec un faux transport : JSON valide → objet validé ; troncature →
  échec ; JSON malformé → nouvel essai puis échec ; 429 → attente puis
  réussite ; même clé → réponse rejouée sans appel.

### L3b — Citations et plausibilité
- Code pur : `citations.py` (§3) et `rules.py` (§3).
- Relevé au L1 (`expert-metier`, 2026-10-15) : la comparaison de citation
  ignore aussi les espaces (pdfplumber colle les mots des PDF Axis :
  « Typical4.8W,max10.7W ») ; la règle « `poe.power_w` ≤ plafond de la
  classe » compare au plafond de la **plus haute classe citée** dans la
  notice, pas à `class` (une caméra at Class 4 ou bt Class 6 à 51 W est
  juste) — l'extraction doit donc garder les autres classes citées.
- Tests : « 7.7 » ne valide pas « 17.7 W » ; extrait recollé →
  `citation_recomposee` ; « PoE+ » → 802.3at ; 6,5 W lu 65 W → `douteux` ;
  classe 4 avec 30 W → `douteux` ; 48 V → `douteux` ; chaque borne exacte.

### L3c — Runner, CLI et exécution sur le PC
- `prompts` (règles 1 à 5 de CLAUDE.md, `VERSION_PROMPT`, référence
  visée), `runner`, sous-commande `extract`. Mise à jour de CLAUDE.md
  (Stack, Commandes) et procédure d'exécution sur le PC (clone, copie de
  `data/sources/`, `OLLAMA_CONTEXT_LENGTH`, retour des réponses brutes).
- Premier passage réel sur 2 ou 3 notices de mise au point.
- Tests avec un faux client : réponse correcte → `sur` ; extrait
  introuvable → `douteux` ; champ non rendu → `absent`.

### L4 — Évaluation
- `metriques` (dont bootstrap), `rapport`, sous-commande `evaluate`
  rejouée depuis les réponses brutes. Mesure du **rappel du découpage**
  (la page de chaque valeur du corrigé est-elle sélectionnée ?) : il borne
  tout le reste.
- Première mesure `qwen3:14b` sur la mise au point, puis sur le test.
- Tests : un cas construit à la main (3 notices, résultats connus) donne
  exactement les métriques attendues ; absent des deux côtés compté juste
  et hors précision ; sous-estimation comptée à part ; bootstrap
  reproductible à graine fixe.

### L5 — Comparaison et itération
- Deux ou trois modèles locaux qui tiennent dans 16 Go, un gros modèle
  ouvert sur Groq (au format strict si disponible).
- Itérations du prompt sur la mise au point seulement, guidées par
  l'analyse d'erreurs ; le test est mesuré une fois par version retenue.
- Analyse d'erreurs : catégories (unité, base au lieu de maximale, DC pris
  pour PoE, variante voisine, invention, découpage, troncature) avec
  exemples cités.

### L6 — Restitution
- README public : le problème, la méthode, le tableau des résultats avec
  intervalles, les erreurs typiques, les limites (50 notices, un
  annotateur et son accord avec lui-même, intervalles larges), comment
  rejouer. Chiffres recopiés des fichiers de résultats.
- Vault et portfolio mis à jour (via `/fin-de-lot`).

## 6. Questions ouvertes

1. ~~Groq ou Grok ?~~ **Groq**, confirmé par Quentin le 2026-10-15.
2. ~~Système du PC~~ **Linux**, confirmé le 2026-10-15.
3. ~~Règle de tension~~ **{12, 24, 36, 48} V**, retenu le 2026-10-15 (les
   tensions continues de SecurScope plus 36 V) ; le risque de la tension
   PoE prise pour une entrée DC est couvert par une règle de cohérence
   (§3). La table de CLAUDE.md sera mise à jour au L3b.
4. ~~Sort du schéma français~~ **Décidé le 2026-10-15** :
   `schema/specifications-equipements.json` n'est plus la référence.
   C'est SecurScope qui fixe, par ses besoins, les champs à extraire ; ce
   projet les reprend dans des fichiers de cibles par famille et par bloc
   (`catalog/extraction/cibles/`). `catalog/models.py`, encore généré
   depuis l'ancien schéma, sera revu quand un chantier y touchera.
5. ~~24 V AC~~ **Note hors modèle** pour les PTZ concernées (accord du
   2026-10-15).
6. ~~Note `format-import-demo.md`~~ **Corrigée** le 2026-10-15.
