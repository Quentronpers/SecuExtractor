#!/bin/bash
# PreToolUse (Bash): before a `git commit`, checks the staged files with the
# project linters and types (stands in for pre-commit, which cannot run on
# the host). Exit 2 blocks the commit and returns the problems to Claude.
. "$(dirname "$0")/lib.sh"

input=$(cat)
command=$(json_field "$input" command)
case "$command" in
  "git commit"* | *"&& git commit"* | *"; git commit"*) ;;
  *) exit 0 ;;
esac
case "$command" in
  *"--no-verify"*)
    echo "--no-verify interdit : corriger plutôt les contrôles." >&2
    exit 2 ;;
esac

staged=$(git -C "$ROOT" diff --cached --name-only --diff-filter=ACMR \
  | grep -E '\.py$' | tr '\n' ' ')
[ -z "${staged// }" ] && exit 0

if ! container_up; then
  echo "Conteneur $CONTAINER arrêté : impossible de contrôler le commit." \
    "Le démarrer (docker compose up -d dev) puis recommencer." >&2
  exit 2
fi

problems=$(docker exec "$CONTAINER" sh -c "cd /app \
  && ruff format --check -q $staged \
  && ruff check -q $staged \
  && mypy" 2>&1) && exit 0
printf 'Commit bloqué, contrôles en échec sur les fichiers indexés :\n%s\n' \
  "$problems" >&2
exit 2
