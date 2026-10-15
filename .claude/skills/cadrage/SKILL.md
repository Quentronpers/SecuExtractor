---
name: cadrage
description: Ouvre un nouveau chantier — rédige son plan dans docs/chantiers/plan-<nom>.md, découpé en lots livrables, le fait relire par les experts utiles et le soumet à la validation de Quentin avant toute ligne de code. À utiliser quand Quentin lance une nouvelle étape d'envergure du pipeline.
model: opus
effort: high
when_to_use: Quand Quentin dit « on lance un chantier », « il faut cadrer », « ouvre un chantier », ou demande un plan avant de coder une étape qui touche plusieurs modules (lecture, extraction, évaluation, relecture, export).
---

# /cadrage <nom du chantier>

1. **Comprendre** : lis `CLAUDE.md`, `docs/pipeline.md`, les plans
   existants dans `docs/chantiers/`, et cherche l'existant
   (`mcp__rag__search`, scope vault puis code `project: "SecuExtractor"`).
   Pose à Quentin les questions qui changent la conception, et seulement
   celles-là.
2. **Rédiger** `docs/chantiers/plan-<nom>.md` :
   - le besoin, dit comme Quentin le dirait ;
   - ce qui est décidé et pourquoi, ce qui est exclu ;
   - les modules touchés et leurs interfaces, dans le respect de la
     frontière de l'acquisition et des règles d'extraction ;
   - **comment on mesure** : quelle métrique sur le jeu de référence
     prouve que le chantier a marché ;
   - les **lots** (L1, L2…) : chacun livrable seul, testable, d'une
     taille qui tient dans une session ;
   - pour chaque lot, les tests attendus (sans appel réseau ni API).
3. **Faire relire** : `/conseil` avec les experts pertinents sur le plan.
   Intègre ce qui fait consensus, garde les désaccords pour Quentin.
4. **Soumettre** : résumé en quelques lignes, questions ouvertes. Rien
   n'est codé avant le « validé » de Quentin ; on note alors la date de
   validation en tête du plan et on propose le commit `docs: cadrage …`.
