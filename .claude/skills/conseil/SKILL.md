---
name: conseil
description: Réunit plusieurs agents experts (métier, LLM, tests) sur une même question ou un même cadrage, en parallèle, puis fait la synthèse et dégage les décisions à prendre par Quentin. À utiliser pour cadrer un chantier ou arbitrer une conception.
when_to_use: Quand Quentin demande l'avis de plusieurs spécialistes, ou avant de valider un cadrage, un protocole d'évaluation ou un changement de prompt important.
---

# /conseil <question ou fichier de cadrage>

1. **Choisis les experts utiles**, pas tous (2 ou 3 en général) :
   - valeur extraite, notice, règle de plausibilité, annotation →
     `expert-metier` ;
   - prompt, sortie structurée, découpage, évaluation, coût →
     `architecte-llm` ;
   - couverture et cas de test → `expert-tests`.
   Dis à Quentin lesquels tu consultes et pourquoi, en une ligne.
2. **Rédige un seul brief** commun : la question, les fichiers à lire
   (chemins exacts), les contraintes déjà décidées, ce qu'on attend en
   retour. Un agent part de zéro : tout ce qu'il doit savoir est dans le
   brief.
3. **Lance-les en parallèle** (un seul message, plusieurs appels Agent).
4. **Synthétise** pour Quentin (≤ 400 mots) :
   - les points d'accord, à appliquer ;
   - les désaccords entre experts, avec ta recommandation ;
   - les questions que seul Quentin peut trancher.
   Ne recopie pas les rapports bruts.

Les experts ne modifient rien. Rien n'est appliqué avant l'accord de
Quentin sur la synthèse.
