#!/bin/bash
# PostToolUse (Edit|Write|MultiEdit): formats the edited file, lints it and
# checks its size. Exit 2 sends the problems back to Claude to fix at once.
. "$(dirname "$0")/lib.sh"

input=$(cat)
file=$(json_field "$input" file_path)
case "$file" in "$ROOT"/*) rel=${file#"$ROOT"/} ;; *) exit 0 ;; esac
[ -f "$file" ] || exit 0
case "$rel" in catalog/*.py | demo/*.py | tests/*.py | eval/*.py) ;; *) exit 0 ;; esac

problems=""
if container_up; then
  out=$(docker exec "$CONTAINER" sh -c "cd /app \
    && ruff check -q --fix --exit-zero '$rel' >/dev/null \
    && ruff format -q '$rel' \
    && ruff check -q '$rel'" 2>&1) || problems="$out"
fi

lines=$(wc -l < "$file")
if [ "$lines" -gt 300 ] && ! size_exception "$rel"; then
  problems="$problems
$rel fait $lines lignes (limite 300, CLAUDE.md) : scinder le module, ou
demander à Quentin de l'ajouter à tests/architecture_debt.txt."
fi

if acquisition_forbidden "$rel" \
  && grep -qE '^[[:space:]]*(from|import)[[:space:]]+catalog\.acquisition' "$file"
then
  problems="$problems
$rel importe catalog.acquisition : seul catalog/cli.py le peut (CLAUDE.md)."
fi

[ -z "$problems" ] && exit 0
printf 'Contrôle automatique de %s (formatage déjà appliqué) :\n%s\n' \
  "$rel" "$problems" >&2
exit 2
