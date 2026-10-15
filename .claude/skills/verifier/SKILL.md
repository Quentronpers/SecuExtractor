---
name: verifier
description: Vérifie le travail en cours (ruff, mypy, pytest) via l'agent lanceur-tests, sans charger les longues sorties dans le contexte. À utiliser après chaque étape de code et avant toute proposition de commit. Argument facultatif — cibles (fichiers, dossiers de tests).
when_to_use: Automatiquement après chaque étape de code terminée, avant d'annoncer qu'une modification marche, et quand Quentin demande « ça passe ? » ou « lance les tests ».
---

# /verifier

1. Détermine les cibles : l'argument s'il y en a un, sinon toute la
   suite (quelques secondes).
2. Si le conteneur `dev_catalog` est arrêté, démarre-le d'abord
   (`docker compose up -d dev`, avec l'accord de Quentin).
3. Lance l'agent **lanceur-tests** avec ces cibles.
4. Rapporte son verdict tel quel, en une ou deux lignes si c'est vert.
5. Si c'est rouge : corrige les échecs causés par le travail en cours,
   puis relance `/verifier` sur les seules cibles en échec. Un échec
   préexistant, sans lien avec le lot, se signale sans se corriger.

Ne jamais déclarer « tests verts » sans le verdict de l'agent.
L'évaluation sur le jeu de référence (qui appelle l'API, donc coûte)
n'en fait pas partie : elle se lance à part, avec l'accord de Quentin.
