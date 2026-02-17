#!/usr/bin/env bash
set -euo pipefail
FILES=(
  ".env.example" "README.md" "backend/app/main.py" "backend/app/models.py" "backend/app/schemas.py"
  "db/init.sql" "docker-compose.yml" "frontend/Dockerfile" "frontend/src/app.js" "frontend/src/index.html"
  "keepalived/Dockerfile" "keepalived/entrypoint.sh" "sync/queue-sync.sh"
)
if ! git diff --name-only --diff-filter=U | grep -q .; then echo "No unresolved merge conflicts found."; exit 0; fi
for f in "${FILES[@]}"; do
  if [ -n "$(git ls-files -u -- "$f")" ]; then git checkout --ours -- "$f"; git add "$f"; echo "resolved: $f"; fi
done
REMAINING="$(git diff --name-only --diff-filter=U || true)"
[ -z "$REMAINING" ] || { echo "$REMAINING"; exit 2; }
echo "All known conflicts resolved and staged."
