#!/bin/bash
# Status line: model, context size of the last request, session cost and
# branch — to see when it is time to hand over to a fresh session.
input=$(cat)
field() {
  printf '%s' "$input" | grep -o "\"$1\"[[:space:]]*:[[:space:]]*[^,}]*" \
    | head -1 | sed 's/^[^:]*:[[:space:]]*//; s/"//g'
}

model=$(field display_name)
cost=$(field total_cost_usd)
size=$(field context_window_size)
transcript=$(field transcript_path)
[ -z "$size" ] && size=200000

used=0
if [ -f "$transcript" ]; then
  usage=$(tail -n 40 "$transcript" | grep -o '"usage":{[^}]*}' | tail -1)
  for key in input_tokens cache_creation_input_tokens cache_read_input_tokens
  do
    n=$(printf '%s' "$usage" | grep -o "\"$key\":[0-9]*" | cut -d: -f2)
    used=$((used + ${n:-0}))
  done
fi

pct=$((used * 100 / size))
flag=""
[ "$pct" -ge 50 ] && flag=" ⚠ penser à reprise.md"
branch=$(git -C "${CLAUDE_PROJECT_DIR:-.}" branch --show-current 2>/dev/null)
printf '%s · ctx %sk (%s%%)%s · %.2f $ · %s' \
  "$model" "$((used / 1000))" "$pct" "$flag" "${cost:-0}" "$branch"
