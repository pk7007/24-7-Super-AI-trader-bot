#!/usr/bin/env bash
# Build deploy/bundle.tar.gz for upload to a server. Run from Git Bash on this PC:
#   bash deploy/make_bundle.sh               # code only (fresh paper/shadow accounts on the server)
#   bash deploy/make_bundle.sh --with-state  # also carry the current paper/shadow state for continuity
# Never includes .env, git history, data caches, or lock files.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
NAME="$(basename "$PWD")"
OUT="deploy/bundle.tar.gz"

items=(bot tests requirements.txt Dockerfile docker-compose.yml .dockerignore SAFETY_RULES.md
       DEPLOYMENT.md KNOWN_LIMITATIONS.md deploy/setup_vps.sh)
if [ "${1:-}" = "--with-state" ]; then
  items+=(state/paper state/shadow)
fi

cd ..
tar czf "$NAME/$OUT" \
  --exclude='.env' --exclude='.env.*' --exclude='*.lock' --exclude='__pycache__' --exclude='*.pyc' \
  --exclude='*.tmp' "${items[@]/#/$NAME/}"
cd "$NAME"

if tar tzf "$OUT" | grep -E '(^|/)\.env$'; then
  echo "ABORT: a .env file got into the bundle" >&2; rm -f "$OUT"; exit 1
fi
echo "Wrote $OUT ($(du -h "$OUT" | cut -f1)), $(tar tzf "$OUT" | wc -l) entries, no .env"
