#!/usr/bin/env bash
set -euo pipefail

REPO_NAME="${1:-reposense-mcp}"

echo "Initializing git..."

git init
git add .
git commit -m "Initial MCP scaffold"

echo "Creating GitHub repository..."

gh repo create "$REPO_NAME" --public --source=. --remote=origin --push

echo "Setting branch protection (require CI)..."

gh api \
  -X PUT \
  repos/:owner/"$REPO_NAME"/branches/main/protection \
  -f required_status_checks.strict=true \
  -f required_status_checks.contexts[]="test" \
  -f enforce_admins=true \
  -f required_pull_request_reviews.required_approving_review_count=1 \
  -f restrictions=null || true

echo "✅ GitHub repo ready."