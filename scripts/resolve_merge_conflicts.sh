#!/usr/bin/env bash
set -euo pipefail

# Resolve recurring merge conflicts for Mail-Relay by preferring the current branch version (ours)
# for the known high-churn generated/project-bootstrap files.

FILES=(
  ".env.example"
  "README.md"
  "backend/app/main.py"
  "backend/app/models.py"
  "backend/app/schemas.py"
  "db/init.sql"
  "docker-compose.yml"
  "frontend/Dockerfile"
  "frontend/src/app.js"
  "frontend/src/index.html"
  "keepalived/Dockerfile"
  "keepalived/entrypoint.sh"
  "sync/queue-sync.sh"
)

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Not inside a git repository." >&2
  exit 1
fi

if ! git diff --name-only --diff-filter=U | grep -q .; then
  echo "No unresolved merge conflicts found."
  exit 0
fi

echo "Resolving known conflict files by taking current branch version (ours)..."
for f in "${FILES[@]}"; do
  if git ls-files -u -- "$f" >/dev/null 2>&1 && [ -n "$(git ls-files -u -- "$f")" ]; then
    git checkout --ours -- "$f"
    git add "$f"
    echo "  resolved: $f"
  fi
done

# Check if any unresolved conflicts remain
REMAINING="$(git diff --name-only --diff-filter=U || true)"
if [ -n "$REMAINING" ]; then
  echo
  echo "Some conflicts are still unresolved (manual review needed):"
  echo "$REMAINING"
  exit 2
fi

echo
echo "All merge conflicts resolved and staged for known files."
echo "Next steps:"
echo "  git status"
echo "  git commit -m 'Resolve merge conflicts'"
