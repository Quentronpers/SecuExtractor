#!/bin/bash
# SessionStart: puts the hand-over note, the git state and the container
# state into Claude's context, so a fresh session starts where the last
# one ended.
. "$(dirname "$0")/lib.sh"
cat > /dev/null

echo "## État au démarrage (hook SessionStart)"
echo "Branche : $(git -C "$ROOT" branch --show-current)"
echo '```'
git -C "$ROOT" log --oneline -5
git -C "$ROOT" status --short | head -20
echo '```'

if ! container_up; then
  echo "**Conteneur $CONTAINER arrêté** : \`docker compose up -d dev\`" \
    "(hooks de lint et vérifications inopérants sans lui)."
fi

if [ -f "$ROOT/reprise.md" ]; then
  echo
  echo "## reprise.md (note de passage de la session précédente)"
  echo "Supprimer le fichier une fois assimilé."
  echo
  cat "$ROOT/reprise.md"
fi
exit 0
