---
name: fin-de-lot
description: Clôt un lot de travail — vérification, relecture de conformité, documentation, vault et mémoire en un passage, reprise.md pour la session suivante, puis proposition de commit (jamais sans accord). À utiliser quand le code d'un lot est terminé.
when_to_use: Quand le dernier point d'un lot est codé, ou quand Quentin dit « on clôt », « fin de lot », « prépare le commit ».
---

# /fin-de-lot

Dans cet ordre, sans sauter d'étape :

1. **Vérifier** : `/verifier`. Rouge → on corrige d'abord, la fin de lot
   attend.
2. **Relire** (en parallèle, un seul message) :
   - `relecteur-conformite` sur le diff ;
   - `expert-metier` si le lot touche une règle de plausibilité, un
     prompt ou le jeu de référence ;
   - `architecte-llm` si le lot touche le client modèle, un prompt ou
     l'évaluation.
   Corrige les écarts bloquants, relance `/verifier` sur ce qui a bougé.
   **Dette d'architecture** : tout fichier touché par le lot qui figure
   dans `tests/architecture_debt.txt` en sort dans ce lot. Si c'est
   déraisonnable, le dire à Quentin plutôt que de laisser filer.
3. **Documenter, sur Sonnet** : lance l'agent **documentaliste** avec un
   brief complet, car il part de zéro :
   - chantier et lot (`docs/chantiers/plan-<chantier>.md`), chantier
     terminé ou non ;
   - ce qui a été fait, en quelques lignes, avec les fichiers clés ;
   - les décisions prises et leur raison, les pièges rencontrés ;
   - les chiffres d'évaluation obtenus, avec le chemin du fichier de
     résultats ;
   - ce qui reste, le prochain lot et ce qu'il faudra lire pour
     l'attaquer ;
   - ce qui n'est pas commité.
   Il met à jour les docs du repo, le vault (commit compris), la mémoire
   et écrit `reprise.md`. **`README.md` (anglais, vitrine publique)** suit
   chaque lot : ce qui est construit, les limites levées ou nouvelles, les
   commandes, et les chiffres recopiés des fichiers de résultats, jamais
   arrondis à la main. Toute affirmation sur la méthode doit rester vraie
   dans le code ; un doute → `architecte-llm` relit le README. Une leçon qui vaut hors de SecuExtractor
   (outil, NAS, CI, méthode) va aussi dans `vault/connaissances/` : le
   dire dans le brief.
4. **Proposer le commit** : liste des fichiers, message au format du
   dépôt (`feat: <chantier> <lot> — <ce que ça change>`). **Attendre
   l'accord de Quentin** avant `git commit`, puis avant `git push`.
   Après le push, suivre la CI : `gh run watch --exit-status` (en
   arrière-plan).
5. Suggérer de **repartir dans une nouvelle session** (le contexte relu à
   chaque appel est le premier poste de coût).
