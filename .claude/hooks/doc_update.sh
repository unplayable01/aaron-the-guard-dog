#!/usr/bin/env bash
# Stop hook: if anything in src/ or batch/ changed since the last docs run,
# start the doc-writer agent (Haiku) headless in the background. Returns
# immediately so the main session never waits on documentation.

# The Haiku session fires Stop hooks too - don't let it trigger itself.
[ -n "$CLAUDE_DOC_AGENT" ] && exit 0

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DOCS="$ROOT/docs"
STAMP="$DOCS/.last_documented"
LOCK="$DOCS/.doc_agent.lock"
LOG="$DOCS/.doc_agent.log"
mkdir -p "$DOCS"

# A run is already in progress (ignore locks older than 30 min - a crashed run).
find "$LOCK" -mmin +30 -delete 2>/dev/null
[ -f "$LOCK" ] && exit 0

if [ -f "$STAMP" ]; then
  CHANGED=$(cd "$ROOT" && find src batch -type f \( -name '*.py' -o -name '*.bat' -o -name '*.vbs' \) -newer "$STAMP" 2>/dev/null)
  MODE="update"
else
  CHANGED=$(cd "$ROOT" && find src batch -type f \( -name '*.py' -o -name '*.bat' -o -name '*.vbs' \) 2>/dev/null)
  MODE="full"
fi
[ -z "$CHANGED" ] && exit 0

FILES=$(echo "$CHANGED" | tr '\n' ' ')
TODAY=$(date +%Y-%m-%d)

if [ "$MODE" = "full" ]; then
  PROMPT="Today is $TODAY. Generate the complete documentation set in docs/ from scratch by reading every file in src/ and batch/ (plus misc/code_description.txt and misc/requirements.txt for context). Start CHANGELOG.md with a single entry for today summarising the current feature set."
else
  PROMPT="Today is $TODAY. These files changed since the last documentation run: $FILES. Re-read them, update only the affected parts of docs/, and add a CHANGELOG.md entry for today. If nothing user-visible changed, make no edits."
fi

if [ -n "$DOC_AGENT_DRYRUN" ]; then
  echo "mode=$MODE files=$FILES"
  exit 0
fi

# Stamp before launching: anything edited while Haiku is working will be
# newer than the stamp and picked up on the next run instead of lost.
touch "$STAMP"
touch "$LOCK"

(
  cd "$ROOT" || exit 1
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') $MODE: $FILES" >> "$LOG"
  CLAUDE_DOC_AGENT=1 claude -p "$PROMPT" \
    --agent doc-writer --model haiku \
    --allowedTools "Read" "Glob" "Grep" "Edit(docs/**)" \
    >> "$LOG" 2>&1
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') finished (exit $?)" >> "$LOG"
  rm -f "$LOCK"
) </dev/null >/dev/null 2>&1 &
disown

exit 0
