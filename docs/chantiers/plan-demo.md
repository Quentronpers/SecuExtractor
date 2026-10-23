# Chantier demo — démo publique de l'extraction, déployée sur Scaleway

> Statut : **validé par Quentin le 2026-10-23**, après relecture le même
> jour par `architecte-llm`, `expert-tests` et une relecture vitrine. L1
> fait le 2026-10-23 : point d'arrêt franchi.

## 1. Le besoin

Un visiteur (client, partenaire, lecteur du README) ouvre un lien et voit le
pipeline mesuré tourner : il choisit une des 50 notices du jeu et compare
l'extraction au corrigé, ou il dépose sa propre notice et voit les 11 champs
d'alimentation sortir avec leur citation et leur état (`sur`, `douteux`,
`absent`). Le coût et la durée de chaque appel sont tracés.

Livrables : démo en ligne, traçage des coûts, coût d'une notice en euros,
vidéo de 3 minutes.

## 2. Décisions

| Décision | Pourquoi |
|---|---|
| **Un module `demo/` dans ce dépôt**, pas de copie ni de second dépôt (Quentin, 2026-10-23). À l'exécution, la démo importe `catalog.extraction`, `catalog.reading` et `catalog.plausibility`, jamais `catalog.acquisition` ni `catalog.evaluation`. | La démo fait tourner le code mesuré, pas une copie qui divergera. |
| **Exception au principe « pas de serveur web »** de `CLAUDE.md`, limitée à `demo/`. | Le pipeline reste un producteur d'artefact ; la démo est une vitrine isolée. |
| **Réglages des fournisseurs déplacés** de `catalog.evaluation.execution` vers `catalog.extraction` (`URLS`, `MAX_JETONS`, choix `max_tokens` / `max_completion_tokens`, refus de `--reflexion none` pour gpt-oss) (Quentin, 2026-10-23). | La démo ne doit pas les recopier. Simple déplacement : aucun chiffre publié ne change, les tests existants le gardent. |
| **Interface Streamlit, en anglais** (Quentin, 2026-10-23 ; anglais comme le README). | Déjà en dépendance, le plus rapide à écrire. Risque : la WebSocket de Streamlit, que la documentation de Scaleway ne mentionne pas. L1 la vérifie avant tout le reste. |
| **Hébergement Scaleway Serverless Containers**, 0 à 1 instance, ressources minimales, sessions inactives coupées après 15 minutes. **Alerte de facturation** à 1 €. | Gratuit à l'échelle d'une démo (200 000 vCPU-s et 400 000 Go-s offerts par mois), en France, s'éteint sans visiteur. Un onglet resté ouvert garde la WebSocket et empêche l'extinction : la coupure d'inactivité borne la consommation, L1 le vérifie. Scaleway n'a pas de plafond de dépense. |
| **Modèle de la démo : `openai/gpt-oss-120b` sur le compte Groq gratuit de Quentin, réservé à la démo** (Quentin, 2026-10-23). Mode souverain (Scaleway Generative APIs, mesuré le 2026-10-23 : 93,2 %, non départagé de Groq) documenté et réglable par variables, pas exposé dans la démo. | Le palier gratuit de Groq ne peut pas produire de facture. Limites relevées le 2026-10-23 (sources publiques, à confirmer dans le compte en L1) : 30 requêtes par minute, 1 000 par jour, 8 000 jetons par minute, 200 000 par jour. |
| **Jeu de 50 : résultats précalculés, sans les PDF** (Quentin, 2026-10-23). `demo/donnees/jeu.json`, versionné, porte par notice son jeu (`miseaupoint` ou `test`), les 11 champs (valeur, état, page, citation de 300 caractères au plus, règle échouée), le corrigé et l'adresse de la notice chez le fabricant. Aucun appel au modèle. | `CLAUDE.md` interdit de redistribuer les documents téléchargés. Valeurs et citations courtes sont déjà publiques dans les rapports. |
| **Le jeu de 50 montre les erreurs** : filtre « errors only » (les erreurs de Groq et ce que le tri en a fait) et bandeau des chiffres globaux, avec le coût projeté pour 50 000 notices. | Une démo qui cache ses erreurs ne convainc pas un lecteur technique ; la méthode du projet est de les publier. |
| **Notice déposée : extraction en direct**, PDF seulement, au plus 10 Mo et 60 pages (`server.maxUploadSize=10`). Lecture par `pdfplumber` dans un sous-processus borné en temps (30 s) et en mémoire. Texte envoyé plafonné à environ 3 500 jetons d'entrée, refus clair au-delà. Archive brute **en mémoire** : rien n'est écrit sur disque, ni le fichier ni la réponse. | Une page de tableau dense dépasserait seule la limite de 8 000 jetons par minute. Un PDF piégé (bombe de décompression) ne doit pas bloquer l'instance. |
| **Contenu déposé non fiable** : référence saisie validée (lettres, chiffres, `-_./ `, 40 caractères au plus) ; valeurs et citations affichées en texte brut, jamais en Markdown ; avertissement : le texte part chez Groq (États-Unis), avec un lien vers sa politique de conservation. | Le schéma strict et le contrôle des citations bornent l'injection de prompt : le pire cas est une valeur fausse mais citée. Le Markdown ouvrirait la porte à un pixel de suivi. |
| **Document hors sujet** (facture, notice d'enregistreur, PDF scanné sans texte) : PDF sans texte refusé sans appel au modèle ; sinon les champs sortent `absent` et un message le dit. | Le refus d'inventer est la propriété que la démo doit rendre visible. |
| **Appels sérialisés** par un verrou : un seul appel au modèle à la fois ; le visiteur suivant voit « waiting ». Attente sur un 429 abandonnée au-delà de 20 s. | À environ 4 400 jetons par notice, la limite par minute tient une notice toutes les 33 s ; sans verrou, deux visiteurs provoquent un 429 et le client actuel peut attendre jusqu'à 10 minutes. |
| **Quota** : 40 notices déposées par jour (heure de Paris) et 3 par session, compteur en mémoire protégé par le verrou. Un refus ou un 429 ne consomme pas le quota (Quentin, 2026-10-23). Quota atteint ou 429 → message clair et renvoi vers le jeu de 50. | Groq reste le vrai plafond ; le compteur évite de buter sur son 429, la limite par session empêche un seul visiteur de tout consommer. |
| **Traçage Langfuse Cloud** (offre gratuite, 50 000 unités par mois, région UE), **montré** : capture du tableau de bord dans le README et dans la vidéo (Quentin, 2026-10-23). Liste fermée de ce qui part : modèle, fournisseur, durée, jetons d'entrée et de sortie, nombre d'essais, coût équivalent, issue (`motif_echec` seul), nombres de champs `sur`, `douteux`, `absent`. **Ni texte, ni référence, ni citation, ni `detail_echec`.** | `detail_echec` reprend du texte de la notice (erreur de validation, corps HTTP). Le taux de `douteux` suivi en production prépare la réponse à « sans corrigé, comment savez-vous que c'est juste ? ». |
| **Coût en euros équivalents** : somme de l'`usage` de **tous** les essais d'une notice (une réponse redemandée est facturée deux fois), échecs compris, au tarif payant du fournisseur ; tarifs en dollars et taux de change datés et sourcés dans `demo/donnees/tarifs.json`. Coût réel de la démo : 0 €. | `ResultatBloc.usage` ne porte que l'essai retenu. |
| **Dépendances** : Playwright déplacé dans un groupe `acquisition` ; groupe `demo` pour ce que la démo ajoute (Langfuse) (Quentin, 2026-10-23). **Image à part** (`demo/Dockerfile`), `COPY` sélectifs (`catalog/`, `demo/`, `pyproject.toml`, `uv.lock`), jamais `COPY . .`. | Image légère, démarrage à froid court. `.dockerignore` n'exclut pas `data/extractions/brut/` : un `COPY . .` depuis le NAS embarquerait le texte des notices. |
| **Déploiement par GitHub Actions**, à la main (`workflow_dispatch`), après succès de `ci.yml` ; image étiquetée par le SHA du commit, retour en arrière par redéploiement d'une étiquette ; clé Scaleway limitée au registre et au conteneur, dans un environnement GitHub protégé. ruff et mypy couvrent `demo/` en CI. | CI/CD traçable et réversible. |

**Exclu** : choix du modèle par le visiteur, mode souverain dans la démo
publique, notices HTML déposées, compte utilisateur, base de données,
relecture et correction des champs (interface de relecture prévue dans
`catalog/review/`, autre chantier), autres blocs que l'alimentation, résultat
de qwen3 à côté de Groq, nom de domaine propre.

## 3. Modules et interfaces

```
catalog/extraction/fournisseurs.py   réglages déplacés depuis evaluation/execution
demo/
  app.py          Streamlit : onglets « Reference set » et « Your datasheet »
  vues.py         lignes du tableau (fonctions pures, testées sans Streamlit)
  service.py      extraire_pdf(octets, reference, moteur) -> ResultatBloc
  lecture.py      lecture du PDF en sous-processus borné
  archive.py      ArchiveBrute en mémoire
  quota.py        compteur du jour et de la session, horloge injectée
  trace.py        métadonnées vers Langfuse (désactivé sans clé)
  couts.py        coût équivalent en euros
  donnees/jeu.json, donnees/tarifs.json
  Dockerfile
scripts/precalcul_demo.py   rejoue les réponses brutes Groq (règles finales)
                            et écrit jeu.json ; tourne sur le NAS, hors CI
```

- `service.extraire_pdf` réutilise `extraire_document`, `charger_cible` et
  `ClientCompatibleOpenAI` sans les modifier ; le faux service s'injecte par
  attribut de module (`service.extraire_pdf`), jamais par `from … import`.
- Le précalcul passe par `catalog.evaluation.rejeu` (déjà testé).
- `tests/test_architecture.py` parcourt aussi `demo/` (limites de taille,
  règle d'import) et gagne un test en sous-processus : importer `demo.app`
  ne charge ni `catalog.acquisition` ni `catalog.evaluation`
  (`sys.modules`). `mypy` (`packages`) et ruff incluent `demo`.

## 4. Comment on mesure

- **Fidélité du jeu de 50** : pour chaque jeu séparément, les métriques
  recalculées depuis `jeu.json` et le corrigé redonnent les **effectifs
  entiers** du rapport publié (test : rapport `_rejeu-regles` du
  2026-10-20, 385 cases ; mise au point : rapport du 2026-10-19, 165
  cases), et `empreinte_corriges` est égale à celle du rapport. Le test
  casse dès qu'une règle change sans que `jeu.json` soit régénéré.
- **Équivalence du dépôt** : un PDF fabriqué par `tests/fabrique_pdf.py` et
  une réponse enregistrée à la main ; le même faux `appeler` passe par
  `lire_document` + `extraire_document` d'un côté, par `extraire_pdf` de
  l'autre. Égalité de `champs`, `incoherents`, `pages`, `cle_brute`,
  `motif_echec` (pas `document` ni `sha256`).
- **Exploitation**, trois chiffres relevés après mise en ligne et notés
  dans le plan : démarrage à froid, durée médiane d'une notice déposée,
  facture Scaleway du premier mois (attendu : 0 €).

## 5. Lots

| Lot | Livrable | Tests attendus (sans réseau ni modèle) |
|---|---|---|
| **L1 — Essai Scaleway** | Page Streamlit minimale déployée à la main. On mesure : WebSocket, démarrage à froid, extinction avec et sans onglet ouvert, coupure d'inactivité, délai maximal d'une requête, gratuité du registre. On confirme les limites Groq dans le compte et la façon dont Groq compte `max_completion_tokens` dans la limite par minute. **Point d'arrêt** : WebSocket instable ou démarrage à froid au-delà de 15 s → on repasse ce plan (repli : FastAPI et une page HTML). | Aucun ; constats écrits dans le journal du lot. |
| **L2 — Réglages et dépendances** | Réglages déplacés dans `catalog/extraction/fournisseurs.py` ; groupes `acquisition` et `demo` dans `pyproject.toml` ; `demo/` couvert par ruff, mypy et le test d'architecture. | Tests existants inchangés et verts ; règle d'import de `demo` (AST et `sys.modules`). |
| **L3 — Précalcul du jeu de 50** | Script de précalcul et `jeu.json`. | Fidélité par jeu (effectifs, empreinte du corrigé) ; 50 notices, 15 et 35, identifiants uniques ; 11 champs chacune ; citation tronquée à 300 caractères sans perdre la règle ; corrigé de `jeu.json` égal au corrigé versionné. |
| **L4 — Service d'extraction d'un PDF déposé** | `service.py`, `lecture.py`, `archive.py`, `quota.py`. | Équivalence (§4) ; rien n'est écrit dans `data/extractions/` (chemin qui lève) ; 10 Mo acceptés, un octet de plus refusé ; 60 pages acceptées, 61 refusées ; signature `%PDF` valide mais fichier corrompu → message ; PDF sans texte → aucun appel ; texte trop long → refus ; échec d'appel → échec, jamais 11 `absent` ; sous-processus de lecture interrompu au-delà du délai. Quota avec horloge injectée : 40e accepté, 41e refusé ; changement de jour à minuit heure de Paris ; refus et 429 ne consomment pas ; 3 par session ; 41 appels concurrents → 40 acceptés ; fixture qui remet le compteur à zéro. |
| **L5 — Interface** | `app.py`, `vues.py` : jeu de 50 (notice, tableau valeur / état / citation / page / corrigé / juste ou faux, filtre des erreurs, bandeau, lien vers la notice) ; dépôt (avertissement, attente, résultat, durée, coût). | `vues.py` sans Streamlit : lignes, juste ou faux, filtre, échappement du texte. `AppTest` : les deux onglets s'affichent, choix d'une notice, message de quota ; `st.cache_*` vidé entre les tests. Le dépôt lui-même n'est pas piloté par `AppTest` (`file_uploader` non pris en charge). |
| **L6 — Traçage et coût** | `trace.py`, `couts.py`, `tarifs.json`. | Coût sur un `usage` connu, somme des essais ; `usage` sans champ de jetons → `None`, pas 0 ; tarifs datés et sourcés ; charge envoyée à un faux Langfuse : seulement les clés de la liste fermée, et ni référence, ni citation, ni page, ni `detail_echec` contenant du texte ; trace désactivée sans clé, sans import réseau. |
| **L7 — Image, CI/CD, mise en ligne** | `demo/Dockerfile`, workflow de déploiement, README (« Try it live », choix Groq / Scaleway en une ligne, capture Langfuse), mise en ligne, trois chiffres d'exploitation. | La construction de l'image est une étape de CI, pas un test ; `AppTest` et ruff, mypy, pytest dans l'image. |

## 6. Vidéo (3 minutes, en anglais, enregistrée par Quentin)

1. Le problème : ressaisir une fiche prend 2,5 à 5 minutes, 50 000
   références à remplir.
2. Le jeu de référence : 50 notices annotées, le chiffre (92,2 % des cases
   justes, 97,9 % des valeurs sûres), le filtre des erreurs.
3. Une erreur de Groq rattrapée en `douteux` par une règle, choisie dans le
   jeu précalculé.
4. Un dépôt en direct, puis un document hors sujet refusé.
5. Le coût d'une notice et le tableau de bord Langfuse.
6. En une phrase : Groq pour la démo publique, Scaleway à Paris pour un
   client, même justesse mesurée.

## 7. Journal

### L1 — essai Scaleway (2026-10-23)

Page Streamlit minimale (`python:3.13-slim`, `streamlit==1.50.0`, image de
796 Mo), envoyée au registre privé `rg.fr-par.scw.cloud/secuextractor`,
déployée par l'API dans l'espace de conteneurs `secuextractor` (fr-par) :
0 à 1 instance, 1 024 Mo, 560 mvCPU, port 8080, délai de requête 300 s.
Conteneur et image d'essai supprimés ensuite ; les deux espaces sont gardés.

- **Déploiement** : prêt 30 s après l'appel `deploy`.
- **WebSocket** : poignée de main `101` ; Streamlit envoie un ping à 30 s et
  ferme à 60 s sans pong (`1000 ping timed out`). Avec pong, la connexion
  tient jusqu'au **délai de requête du conteneur** : coupure TCP à 301 s
  pour 300 s réglées. Le délai se règle jusqu'à 15 minutes au moins
  (documentation contradictoire : 900 s ou 60 minutes). Essai de Quentin
  dans un navigateur : le compteur avance sans « Connecting ».
- **Démarrage à froid** : 4,46 s puis 4,13 s sur `/_stcore/health`, après
  plus de 15 minutes sans requête ; 0,06 s ensuite. Seuil d'arrêt (15 s)
  loin. Extinction documentée : 15 minutes sans requête.
- **Onglet ouvert** : le navigateur se reconnecte après chaque coupure, donc
  l'instance ne s'éteint pas tant qu'un onglet reste ouvert. Ordre de
  grandeur d'un mois allumé (560 mvCPU, 1 Go) : environ 1,45 million de
  vCPU-s et 2,6 millions de Go-s, soit 12 à 15 € au-delà du palier gratuit.
  La coupure d'inactivité doit donc **fermer la page côté navigateur**
  (script de l'interface après 15 minutes sans action), pas seulement
  arrêter le script Streamlit : à vérifier dans un navigateur en L5.
- **Groq** (en-têtes de réponse du compte) : 1 000 requêtes par jour et
  8 000 jetons par minute confirmés. `max_completion_tokens=8192` n'est pas
  réservé d'avance : un appel de 74 jetons d'entrée passe avec ce réglage.
  Groq rejette en 403 l'agent utilisateur par défaut de `urllib` ; le client
  du projet (`requests`) n'est pas concerné.
- **Registre** : privé facturé 0,027 € par Go et par mois ; public gratuit
  jusqu'à 75 Go. L'image ne contient que du code public : décision à
  prendre en L7.
