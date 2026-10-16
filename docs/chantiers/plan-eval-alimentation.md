# Chantier eval-alimentation — extraction mesurée du bloc alimentation des caméras IP

> Statut : **validé par Quentin le 2026-10-15** (relu par `expert-metier`
> et `architecte-llm` le même jour). L1, L1 bis et L2 terminés et commités le
> 2026-10-16 (L2 : `8a5e964`) ; L3a (`19a6c76`) et L3b (`fb034a2`)
> terminés et commités ; L3c fait le 2026-10-16, non commité (premier
> passage réel reporté à L4) ; prochain lot : L4. Périmètre de L4 à L6 resserré
> le 2026-10-16 après l'avis de l'agent `recruteur-ia` (ligne de base sans
> LLM, un seul modèle local, README anglais anticipé).
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

Complément vérifié par `architecte-llm` le 2026-10-16 dans le source
d'Ollama (branche `main`) et la documentation de Groq :

- **Ollama `/v1`** : `truncate=true` et `shift=true` par défaut, non
  réglables par requête. `usage.prompt_tokens` vaut `PromptEvalCount` (prompt
  après coupe, cache compris) : un prompt coupé remonte environ le contexte.
  Une génération qui atteint le contexte décale la fenêtre et efface le
  début de la notice, avec `finish_reason=stop`. Repli si les heuristiques de
  `brut.py` ne suffisent pas : `/api/chat` natif avec `num_ctx`,
  `truncate: false`, `shift: false` (Ollama renvoie alors une erreur), au
  prix de la règle « un seul client ».
- **`/api/ps`** d'Ollama expose le `digest` et le `context_length` réel du
  modèle chargé.
- **`reasoning_effort` sur Ollama** : `"none"` donne `think=false` ; qwen3
  ne connaît que vrai/faux, donc `low`, `medium` et `high` donnent tous
  `think=true` : deux conditions d'expérience seulement. Toujours l'envoyer
  explicitement. La réflexion revient dans `message.reasoning`. `num_predict`
  compte les jetons de réflexion : 4096 est court avec réflexion.
- **`json_schema` sur Ollama** : vraie contrainte de grammaire (appliquée
  après la balise de fin de réflexion), `strict` ignoré ; la validation
  Pydantic reste nécessaire.
- **Nom du champ de limite de sortie** : Ollama `/v1` ne lit que
  `max_tokens` (devenu `num_predict`) et ignore `max_completion_tokens` ;
  Groq préfère `max_completion_tokens`.
- **Groq** : `strict` seulement sur gpt-oss-20b et 120b, qwen/qwen3.8-27b et
  muse-spark-open. `reasoning_format=parsed` met la réflexion dans
  `message.reasoning` (`raw` avec du JSON donne un 400) ; pour gpt-oss c'est
  `include_reasoning`, exclusif de `reasoning_format`. En non strict, un
  JSON hors schéma donne un HTTP 400 de code `json_validate_failed`.

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

**Le chantier a réussi** quand ce tableau existe sur le jeu de test pour un
modèle local et un modèle Groq, comparés à une ligne de base sans LLM (un
deuxième modèle local seulement s'il reste du temps avant le 2026-11-15),
rejouable par une commande,
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

### L3a — Client et réponses brutes (fait le 2026-10-16, commit `19a6c76`)
- `catalog/extraction/brut.py` : `RequeteModele` (modèle, version de prompt,
  messages, schéma, température, `max_jetons`, `reasoning_effort`, graine,
  numéro d'exécution, `contexte_jetons`, `empreinte_modele`) dont la clé est
  un SHA-256 sur JSON canonique. `ArchiveBrute` écrit
  `data/extractions/brut/<clé>.json` (écriture atomique, contrôle clé/requête
  à la lecture). `obtenir()` rejoue sans appel si la clé existe ;
  `interpreter()` et `interpreter_essai()` valident hors réseau (pour
  `evaluate` sur le NAS). Motifs d'échec : `aucune_reponse`, `troncature`
  (`finish_reason=length`), `troncature_entree` (`prompt_tokens` ≥ contexte
  − 64), `decalage_contexte` (prompt + completion ≥ contexte),
  `json_malforme`, `schema_invalide`.
- `catalog/extraction/client.py` (réécrit ; c'était un stub Anthropic) :
  `ClientCompatibleOpenAI(url_base, cle_api, champ_max_jetons, transport,
  dormir)`. Format `json_schema` strict. Refus avant envoi si le contexte ne
  tient pas la requête (`ContexteInsuffisant` ; estimation 3 caractères par
  jeton + `max_jetons` + marge). Reprises sur 429, 5xx, erreur réseau et 200
  sans corps : 5 tentatives, `Retry-After` d'abord, sinon 2^n s plafonné à
  120 s. `Retry-After` > 120 s : arrêt net « quota épuisé ». Autre 4xx : arrêt
  sans reprise. Le 400 Groq `json_validate_failed` est archivé comme une
  réponse (`schema_invalide`). Réponse illisible redemandée une fois avec la
  graine + 1 (sinon Ollama rend la même) ; troncature non redemandée ; si le
  nouvel essai tombe en panne de transport, le premier est gardé. Les erreurs
  de transport ne sont jamais archivées : le passage suivant réessaie.
- `tests/test_client.py` et `tests/test_brut.py`, faux transport, aucun
  réseau. 138 tests verts, ruff et mypy propres. `transport_requests`
  (le vrai transport) n'est pas testé : il faudrait simuler `requests`.
- `.gitignore` : `data/extractions/` ignoré, car les réponses brutes
  contiennent le texte des notices (rien n'est redistribué). Les résultats
  publics iront dans `eval/resultats/`.
- Décisions et raisons :
  - l'URL du serveur n'entre pas dans la clé : extraction sur le PC,
    relecture sur le NAS, même fichier ;
  - le contexte réel et le digest du modèle **entrent** dans la clé :
    sinon une réponse tronquée serait rejouée à jamais après un relèvement
    d'`OLLAMA_CONTEXT_LENGTH` ou un nouveau `ollama pull` sous le même nom
    (bloquant relevé par `architecte-llm`) ;
  - le nom du champ de limite de sortie dépend du fournisseur (voir §3).
- Relectures : `relecteur-conformite`, aucun bloquant ; `architecte-llm`,
  trois bloquants corrigés (clé sans contexte ni digest, détection de
  troncature, 400 Groq perdu) et recommandations appliquées (`int(None)` dans
  `usage`, quota, graine changée).
- Tests prévus au départ, tous couverts : JSON valide → objet validé ;
  troncature → échec ; JSON malformé → nouvel essai puis échec ; 429 → attente
  puis réussite ; même clé → réponse rejouée sans appel.

### L3b — Citations et plausibilité (fait le 2026-10-16, commit `fb034a2`)
- `catalog/extraction/citations.py` : `verifier_citation(champ, valeur, page,
  extrait, pages)` rend un motif ou `None`. Motifs : `citation_absente` (ni
  page ni extrait, règle 1), `citation_introuvable`, `citation_autre_page`
  (extrait trouvé sur une autre page envoyée : erreur de numéro, comptée à
  part), `citation_recomposee`, `valeur_hors_extrait`,
  `valeur_non_maximale` (`power_w_peak` alors qu'une valeur plus haute est
  dans l'extrait : « 16 ~ 56W » lu 16). Comparaison sans
  casse, espaces, séparateurs de cellules (`|`) ni coupures de mot.
  Valeurs numériques : nombre délimité suivi de l'unité ; nombres d'une
  plage ou d'une liste qui partagent l'unité (« 10–28 V DC »,
  « 24.7/11.4 W » de Vivotek) ; bornes d'une tension à tolérance
  symétrique ou asymétrique ; A → mA. `V` exclut VA, VAC, « V AC » et
  « AC 24V » (une tension alternative prise pour du continu ferait accepter
  une alimentation 24 V DC qui détruit la caméra). Port faux : pas
  de preuve demandée. Port DC vrai : « DC » écrit (un « 12 V » seul ne
  suffit pas, pour ne pas valider la ligne de tension PoE).
- `catalog/plausibility/rules.py` (règles) et `checker.py`
  (`verifier_plausibilite(valeurs, extraits, pages)` → motifs par clé,
  joints par « ; »). Table reportée dans CLAUDE.md.
- Écarts au §3, constatés sur le corrigé :
  - min ≥ max / 3 au lieu de 0,6 × max : les plages Axis « 10–28 V DC »
    sont légitimes ;
  - pas de plafond de classe quand la notice mentionne un PoE propriétaire
    (High PoE, injecteur constructeur) : axis-08 (High PoE 51 W, mode at
    Class 4) et ipro-04 (injecteur 60 W, 50 W) étaient marqués à tort ;
  - plafonds réels des classes 1 et 2 (3,84 et 6,49 W) ;
  - courant < 20 mA refusé quelle que soit la tension (borne basse).
- Ajouté après relecture `expert-metier` : `valeur_non_maximale` et
  exclusion de l'AC (les deux bloquants) ; norme af avec plus de 12,95 W
  sans at ni bt cités → `norme_insuffisante` ; plafond de 71,3 W sans
  classe citée (« max 90 W » est la capacité du PSE) ; PoH et HDBaseT
  comptés comme PoE propriétaire, ePoE et UPoE non.
- Écartés, le corrigé les contredit : tension 37–57 V `douteux` sans
  condition (vivotek-06 a une vraie entrée « DC 48V ») ; rapport V × I
  resserré à 0,75–1,5 (hik-01 : `power_w_peak` est le maximum PoE, au-dessus
  du DC ; dahua-03 : 36 V × 2,23 A pour 45 W, gardé par le corrigé). Le
  rapport 0,5–2 n'attrape donc ni le courant typique pris pour le maximal
  ni le calibre d'alimentation : limite connue.
- Non traités, notés pour L5 : puissance au PSE ou au PD ; `poe.power_w`
  égal à la typique alors qu'une maximale existe ; classes lues dans tout le
  texte (fiches multi-références) ; « PoE injector » cité comme simple
  accessoire coupe le plafond.
- Contrôle sur les notices réelles, constaté le 2026-10-16 par un script
  hors dépôt (le texte des notices n'est pas versionné) : chaque extrait du
  corrigé est retrouvé dans sa page, et chaque page citée est retenue par le
  découpage. Tests versionnés : chaque valeur du corrigé est justifiée par
  son extrait, sauf dahua-04 `power_w` « 7.4 (pulling stream in 4G) », sans
  unité, mis en `douteux` à dessein ; aucune valeur `sur` du corrigé
  n'échoue la plausibilité.
- **Pour L4** : la `section` du corrigé HTML est le libellé de ligne
  (« Input Voltage »), pas le titre de section du lecteur (« Environmental
  & Electrical ») ; le rappel du découpage devra retrouver la page par
  l'extrait.
- Laissé au runner (L3c) : l'état final (`sur` / `douteux` / `absent`) à
  partir du doute, du motif de citation et des motifs de plausibilité.

### L3c — Prompt, runner et sous-commande `extract` (fait le 2026-10-16, non commité)
- `catalog/extraction/prompts.py` : gabarit système en anglais (les notices
  sont en anglais), `VERSION_PROMPT = "camera-alimentation-v1"` (pas encore
  mesurée). Neuf règles : citation, jamais d'inférence (« faux » est une
  valeur citée), maximum, plages et tolérances, aucune arithmétique hors
  tolérance et A → mA, nombres, multi-références avec suffixe, attributs
  nuls si le port est faux, sorties auxiliaires et calibres non comptés. Une
  consigne par champ, tirée de `eval/GUIDE.md` : c'est la spécification, pas
  un ajustement au corrigé (aucune mesure faite). Message utilisateur :
  « Target reference » puis « === Page N - titre === ». Schéma JSON strict
  bâti sur les 11 cibles (par champ : extrait, page, valeur, doute ; extrait
  avant valeur ; enum nullable en `anyOf`). `ReponseBloc` refuse une clé
  manquante : `schema_invalide`, donc échec (champ non rendu = échec, pas
  `absent`).
- `catalog/extraction/etats.py` : état final, sans modèle. `absent` si la
  valeur est nulle (même avec doute) ; `douteux` si au moins un motif
  (`type_invalide`, motif de citation, motifs de plausibilité,
  `doute_modele`), cumulés par « ; » dans `regle_echouee` ; `sur` sinon.
  `evaluate` le rejouera en L4 (`etats_champs`).
- `catalog/extraction/runner.py` : `ConfigModele`, `Moteur`, `Document`,
  `ResultatBloc`, `construire_requete`, `extraire_document` (sélection des
  pages, rejeu ou appel, interprétation ; troncature, JSON invalide ou appel
  en échec : résultat sans champs avec un motif), `executer_lot` (document lu
  une fois, `sortie/<id>_e<n>.json`).
- `catalog/extraction/ollama.py` : `/api/ps` pour le contexte réel, le
  digest et la part sur GPU ; charge le modèle par `/api/generate` s'il est
  absent ; refuse sans contexte ni digest ; nom sans étiquette → `:latest` ;
  `/api/version`.
- `catalog/evaluation/execution.py` : sous-commande `extract --jeu
  miseaupoint|test [--ids] [--executions] [--fournisseur ollama|groq]
  [--reflexion none|low|medium] [--max-jetons]`, configurée par `LLM_BASE_URL`,
  `LLM_MODEL`, `LLM_API_KEY`. Résultats dans
  `data/extractions/resultats/<date>_<modele>_<prompt>_<reflexion>/` avec
  `execution.json` (écrit au départ, complété à la fin : réglages, empreinte
  du prompt, empreinte de `notices.csv`, commit lu dans `.git` faute de git
  dans le conteneur, version d'Ollama, part sur GPU, contrôle de fin
  `/api/ps` avec `fin_ecart`). Placé côté `catalog.evaluation` parce qu'il lit
  `eval/notices.csv` : l'évaluation dépend de l'extraction, pas l'inverse.
  L'ancien `extract --fabricant` (stub) est retiré de `cli.py` ; l'extraction
  par fabricant reste à écrire (CLAUDE.md, `docs/pipeline.md` §8).
- `catalog/evaluation/notices.py` : `chemin_source(notice, manifeste)`
  retrouve le fichier archivé par empreinte (entrées « remplace » exclues) ;
  les 50 notices le retrouvent. `cible.py` : `verifier_type` remonté depuis
  `evaluation/reference.py`. `brut.py` : motif `echec_appel`, jamais archivé.
- `citations.py` corrigé : une tolérance, symétrique ou asymétrique, n'est
  acceptée que collée à la tension (éventuellement entre parenthèses). Avant,
  « 36 VDC, 2.23 A ± 25% » validait 27/45 et un 27/45 inventé passait en
  `sur`. Le corrigé des 50 notices reste accepté. `eval/GUIDE.md` : règle datée 2026-10-16, une
  sortie d'alimentation pour accessoires (12VDC output Hanwha) n'est pas une
  entrée.
- CLAUDE.md mis à jour (Stack, Commandes, procédure « Extraction sur le
  PC », Structure, exception de la règle 2 pour les tolérances).
  `docs/pipeline.md` aligné.
- Tests : `test_prompts.py`, `test_runner.py` (faux modèle : correcte →
  `sur`, extrait introuvable → `douteux`, valeur nulle → `absent`, clé
  manquante → échec, doute, type invalide, plausibilité, motifs cumulés,
  troncature, JSON malformé, `echec_appel` non archivé, rejeu sans appel,
  lot), `test_ollama.py`, `test_execution.py`, compléments de
  `test_citations.py` et `test_notices.py`. 299 tests verts, ruff et mypy
  propres.
- Contrôles hors tests : pire cas de la mise au point, 16 600 caractères
  envoyés, tient dans un contexte de 16 384 jetons même avec réflexion
  (8 192 jetons de sortie) ; chaîne complète éprouvée contre un faux serveur
  Ollama local (vrai transport HTTP), sorties effacées.
- Relectures : `architecte-llm`, 3 bloquants corrigés (ports faux sans
  citation mis à tort en `douteux` ; tolérance après le courant acceptée à
  tort ; `reasoning_effort="none"` refusé par Groq pour gpt-oss, d'où le
  choix `low`) et recommandations appliquées (enum `anyOf`, clé manquante =
  échec, `execution.json` complet, contrôle de fin `/api/ps`, nom sans
  étiquette, tolérance entre parenthèses, `fin_ecart`). `expert-metier` sur
  le prompt, 2 bloquants corrigés (tolérance alignée sur le guide ;
  attributs de port nuls si port faux) et recommandations appliquées
  (sorties auxiliaires, calibres et capacités de norme non comptés, V × I très
  au-dessus de la puissance → doute, suffixe de référence, typiques
  Basic/24 h, plage sans libellé, « approx. »). `relecteur-conformite`, aucun
  bloquant.
- **Premier passage réel non fait** : Quentin n'était pas sur le PC. Il
  devient la première étape de L4 : 2 ou 3 notices de mise au point (par
  exemple axis-03, hik-01, dahua-02), sans réflexion, avec l'accord de
  Quentin, et un essai de fumée par fournisseur avant tout lot (les clés à
  points et les `anyOf` ne sont pas éprouvés sur un vrai serveur).
- Écart au plan §2 : `docker-compose.yml` ne déclare pas
  `host.docker.internal`, non modifié faute d'accord ; la procédure passe par
  `172.17.0.1` (passerelle du bridge) avec `OLLAMA_HOST=0.0.0.0`.
- **Tranché par Quentin le 2026-10-16** : le guide se contredisait (tolérance
  asymétrique après le courant retenue pour dahua-04, symétrique ignorée pour
  dahua-03). Désormais toute tolérance écrite après un courant est ignorée :
  dahua-04 passe de 10,8 / 15 à 12 / 12 dans le corrigé, avec une note. Raison :
  des bornes trop larges font accepter une alimentation inadaptée, des bornes
  trop étroites ne font que refuser une alimentation qui aurait convenu. Guide,
  prompt et contrôle de citation alignés.
- Reporté : R2 (L5), à température 0 Ollama échantillonne en glouton, la
  graine n'a pas d'effet, 3 exécutions ne mesurent que le non-déterminisme du
  GPU, et le nouvel essai à graine + 1 de `client.py` rend la même sortie (le
  faire à température 0,3 enregistrée, ou le supprimer) ; `--executions`
  vaut 1 par défaut. R4, 8 192 jetons avec réflexion peuvent être courts pour
  qwen3 (troncature comptée échec) : à mesurer. L4 : compter à part les
  sorties incohérentes (extrait non nul avec valeur nulle, doute avec valeur
  nulle), mesurer le tri `douteux` avec et sans `doute_modele`, lire la
  quantification dans `/api/show`. `ReponseBloc` vérifie les clés de
  `CONSIGNES` (un seul bloc) : à généraliser avec un second bloc.
- README anglais (prévu dès la fin de L3c) : pas encore écrit.

### L4 — Évaluation
- **Récupération des notices par un tiers** (décidé le 2026-10-16) :
  sous-commande de `cli.py` (seul module qui importe l'acquisition) qui lit
  `eval/notices.csv`, télécharge chaque notice avec le fetcher existant
  (`robots.txt`, cadence), vérifie l'empreinte SHA-256, signale les
  notices modifiées depuis par le fabricant et écrit le manifeste. Sert
  aussi la copie de `data/sources/` sur le PC. Écrire dans `data/sources/`
  reste soumis à l'accord de Quentin.
- `metriques` (dont bootstrap), `rapport`, sous-commande `evaluate`
  rejouée depuis les réponses brutes. Mesure du **rappel du découpage**
  (la page de chaque valeur du corrigé est-elle sélectionnée ?) : il borne
  tout le reste.
- Première mesure `qwen3:14b` sur la mise au point, puis sur le test.
- **Ligne de base sans LLM** : extraction par expressions régulières sur le
  texte découpé (libellés « max » / « typical », unités W, V, A, classe et
  norme PoE), mesurée avec les mêmes métriques sur les mêmes notices. C'est
  le point de comparaison qui justifie le LLM ; quelques heures, en
  réutilisant l'analyse des nombres de `citations.py`.
- Tests : un cas construit à la main (3 notices, résultats connus) donne
  exactement les métriques attendues ; absent des deux côtés compté juste
  et hors précision ; sous-estimation comptée à part ; bootstrap
  reproductible à graine fixe.

### L5 — Comparaison et itération
- Un modèle local (`qwen3:14b`) contre un gros modèle ouvert sur Groq
  (format strict si disponible). Un deuxième modèle local seulement s'il
  reste du temps. Une ou deux versions du prompt au plus.
- Itérations du prompt sur la mise au point seulement, guidées par
  l'analyse d'erreurs ; le test est mesuré une fois par version retenue.
- Analyse d'erreurs : catégories (unité, base au lieu de maximale, DC pris
  pour PoE, variante voisine, invention, découpage, troncature) avec
  exemples cités.

### L6 — Restitution
- **README en anglais**, écrit dès la fin de L3c, sans chiffres : le
  problème, la méthode, les limites (50 notices, corrigé annoté par un LLM
  et relu sur échantillon, intervalles larges), comment rejouer. Le tableau
  des résultats avec intervalles et les erreurs typiques viennent en L4 et
  L5, recopiés des fichiers de résultats.
- Il dit que seul le chantier d'évaluation est livré, le reste du pipeline
  étant prévu, et assume l'usage de Claude en une ligne de méthode (code
  écrit avec Claude Code ; corrigé annoté par Claude, relu par Quentin ;
  Claude n'est pas un des modèles évalués).
- **Licence MIT** (décidée par Quentin le 2026-10-16 : la valeur est dans
  SecurScope et le catalogue, absents du dépôt) : fichier `LICENSE` ajouté
  au passage en public. **Badge CI** en tête du README au même moment
  (`github.com/Quentronpers/SecuExtractor`, il s'affiche cassé tant que le
  dépôt est privé).
- Avant de passer le dépôt en public : licence, CLAUDE.md corrigé (Stack et
  Structure), décision sur les fichiers `.claude/` versionnés. Passage en
  public avec l'accord de Quentin.
- **Audit avant publication** (demandé par Quentin le 2026-10-16 : dépôt
  sûr et propre, pas une mauvaise vitrine), lancé en parallèle par
  `/conseil`, verdict de chaque agent avant l'accord de Quentin :
  - *sécurité* : secrets, `.env`, chemins et noms internes (NAS, `/volume1`,
    adresses), courriels, dans les fichiers **et tout l'historique git** ;
    aucun PDF, texte de notice ni réponse brute versionné, **à aucun
    commit de l'historique** ; fixtures de `tests/` construites à la main ;
    URL de `eval/notices.csv` sans jeton ni lien signé ; extraits du
    corrigé courts (citation courte, source indiquée) ; contenu de
    `.claude/` (hooks, réglages, liens vers le vault) ;
  - *organisation* (`Explore`) : fichiers morts ou hérités (`schema/`,
    `catalog/models.py`, `review/`, `export/`, dépendance `anthropic`),
    cohérence entre README, CLAUDE.md, `docs/` et le code ;
  - *conformité* (`relecteur-conformite`) : règles de CLAUDE.md sur tout le
    dépôt, pas seulement un diff ;
  - *tests* (`expert-tests`) : couverture des modules publiés ;
  - *méthode* (`architecte-llm`) : chaque affirmation du README vraie dans
    le code, chiffres recopiés des fichiers de résultats ;
  - *vitrine* (`recruteur-ia`) : lecture à 30 s et à 3 min.
  Les écarts sont corrigés puis l'audit est rejoué sur ce qui a changé.
- Vault et portfolio mis à jour (via `/fin-de-lot`).

## 6. Questions ouvertes

1. ~~Groq ou Grok ?~~ **Groq**, confirmé par Quentin le 2026-10-15.
2. ~~Système du PC~~ **Linux**, confirmé le 2026-10-15.
3. ~~Règle de tension~~ **{12, 24, 36, 48} V**, retenu le 2026-10-15 (les
   tensions continues de SecurScope plus 36 V) ; le risque de la tension
   PoE prise pour une entrée DC est couvert par une règle de cohérence
   (§3). Table de CLAUDE.md mise à jour au L3b.
4. ~~Sort du schéma français~~ **Décidé le 2026-10-15** :
   `schema/specifications-equipements.json` n'est plus la référence.
   C'est SecurScope qui fixe, par ses besoins, les champs à extraire ; ce
   projet les reprend dans des fichiers de cibles par famille et par bloc
   (`catalog/extraction/cibles/`). `catalog/models.py`, encore généré
   depuis l'ancien schéma, sera revu quand un chantier y touchera.
5. ~~24 V AC~~ **Note hors modèle** pour les PTZ concernées (accord du
   2026-10-15).
6. ~~Note `format-import-demo.md`~~ **Corrigée** le 2026-10-15.
7. Identifiants du code en anglais : non avant le 2026-11-15
   (recommandation de `recruteur-ia`, 2026-10-16 : sans effet sur la
   décision d'un recruteur avant l'échéance, environ 4 200 lignes) ; à
   reconsidérer en phase 3.
