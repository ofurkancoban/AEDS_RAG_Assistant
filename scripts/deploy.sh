#!/usr/bin/env bash
# Deploys this repo's backend and frontend to the production VPS in one step.
#
# Exists because a manual scp of individual files once missed setting
# VITE_API_BASE_URL at frontend build time, shipping a build that pointed at
# http://localhost:8000 in every visitor's browser instead of the production
# API - a class of bug a single scripted build/deploy path removes entirely.
#
# Usage: scripts/deploy.sh

set -euo pipefail

VPS_HOST="158.220.124.164"
VPS_APP_DIR="/root/AEDS_RAG_Assistant"
VPS_WEB_ROOT="/var/www/aeds-rag-assistant"
PM2_APP_NAME="AEDSRAGAssistant"
HEALTH_URL="https://aeds-rag-assistant.ofurkan.co/health"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> Building frontend (same-origin API base, proxied by nginx)"
(cd frontend && VITE_API_BASE_URL='' npm run build)

if grep -q 'localhost:8000' frontend/dist/assets/*.js 2>/dev/null; then
  echo "Refusing to deploy: built frontend still references localhost:8000" >&2
  exit 1
fi

echo "==> Syncing backend source to VPS"
# Excludes: local venv/caches, and anything under data/ - that directory holds
# the VPS's own production database, vector store and ingested documents;
# overwriting it with the local dev copy would destroy live data.
rsync -az --delete \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '.git' \
  --exclude '.env' \
  --exclude 'data/' \
  --exclude 'frontend/node_modules' \
  --exclude 'frontend/dist' \
  --exclude 'frontend_classic' \
  --exclude '*.log' \
  --exclude '.pytest_cache' \
  ./ "root@${VPS_HOST}:${VPS_APP_DIR}/"

echo "==> Syncing frontend build to VPS web root"
rsync -az --delete frontend/dist/ "root@${VPS_HOST}:${VPS_WEB_ROOT}/"
ssh "root@${VPS_HOST}" "chown -R www-data:www-data ${VPS_WEB_ROOT}"

echo "==> Installing dependencies and running DB migration on VPS"
ssh "root@${VPS_HOST}" "cd ${VPS_APP_DIR} && .venv/bin/pip install -q -r requirements.txt && .venv/bin/python -c 'from db.models import init_db; init_db()'"

echo "==> Restarting pm2"
ssh "root@${VPS_HOST}" "source ~/.nvm/nvm.sh 2>/dev/null; pm2 restart ${PM2_APP_NAME}"

echo "==> Waiting for the app to come back healthy (cold start reloads the local embedding model, can take a minute or two)"
for i in $(seq 1 24); do
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$HEALTH_URL" || true)"
  if [ "$code" = "200" ]; then
    echo "==> Healthy after ${i} check(s)."
    exit 0
  fi
  sleep 5
done

echo "Deploy finished but /health did not return 200 within 2 minutes - check pm2 logs on the VPS:" >&2
echo "  ssh root@${VPS_HOST} \"source ~/.nvm/nvm.sh 2>/dev/null; pm2 logs ${PM2_APP_NAME} --lines 50 --nostream\"" >&2
exit 1
