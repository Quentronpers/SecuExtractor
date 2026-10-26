#!/bin/bash
# Helpers shared by the hook scripts. Neither jq, Python nor Node exist on
# the NAS host: JSON is read with grep/sed, tools run in the dev container.

ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
CONTAINER=dev_catalog

# Prints the value of a top-level-ish string field ("file_path", "command").
json_field() {
  printf '%s' "$1" \
    | grep -o "\"$2\"[[:space:]]*:[[:space:]]*\"\([^\"\\\\]\|\\\\.\)*\"" \
    | head -1 \
    | sed "s/^\"$2\"[[:space:]]*:[[:space:]]*\"//; s/\"\$//"
}

# True when the dev container is running.
container_up() {
  docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$CONTAINER"
}

# True when a file over 300 lines is a grandfathered exception.
size_exception() {
  grep -qxF "file $1" "$ROOT/tests/architecture_debt.txt" 2>/dev/null
}

# True when a module of the pipeline may not import catalog.acquisition
# (only the CLI and the acquisition package itself may).
acquisition_forbidden() {
  case "$1" in
    catalog/acquisition/* | catalog/cli.py) return 1 ;;
    catalog/*.py | demo/*.py) return 0 ;;
  esac
  return 1
}
