#!/bin/bash
# PreToolUse (Edit|Write|MultiEdit): enforces the « ce que tu ne fais pas
# sans me demander » list of CLAUDE.md. Blocks what is forbidden outright,
# asks Quentin for what needs his approval.
. "$(dirname "$0")/lib.sh"

input=$(cat)
file=$(json_field "$input" file_path)
case "$file" in "$ROOT"/*) rel=${file#"$ROOT"/} ;; *) exit 0 ;; esac

ask() {
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse",'
  printf '"permissionDecision":"ask","permissionDecisionReason":"%s"}}\n' "$1"
  exit 0
}

case "$rel" in
  *.env | *.env.*)
    echo "Les fichiers .env contiennent des secrets : ne pas les modifier." >&2
    exit 2 ;;
esac

if acquisition_forbidden "$rel" && printf '%s' "$input" \
  | grep -qE '(from|import)[[:space:]]+catalog\.acquisition'; then
  echo "Frontière : seul catalog/cli.py importe catalog.acquisition. Le" \
    "pipeline lit data/sources/ sans savoir d'où viennent les documents." >&2
  exit 2
fi

case "$rel" in
  data/sources/*_manuels.json) ;;
  data/sources/*)
    ask "Document archivé ou manifeste : le modifier rend des citations invérifiables." ;;
  pyproject.toml | uv.lock | Dockerfile | docker-compose.yml)
    ask "Dépendances, outillage ou conteneur : à faire avec l'accord de Quentin." ;;
  tests/architecture_debt.txt)
    ask "Dette d'architecture : la liste ne doit que rétrécir, l'allonger demande l'accord de Quentin." ;;
  eval/reference/*)
    ask "Jeu de référence annoté : la vérité terrain ne se modifie qu'avec Quentin." ;;
esac
exit 0
