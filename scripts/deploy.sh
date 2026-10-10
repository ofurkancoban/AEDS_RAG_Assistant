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

# docs/nginx-aeds-rag-assistant.conf is documentation, not something this
# script deploys - nginx itself is edited by hand on the VPS. It drifted
# silently out of sync with the live config for a long time (missing both
# the security headers block and the rate-limit line entirely) before that
# was noticed by chance. A non-fatal warning here, on every deploy, is a
# much shorter feedback loop than "notice by chance" for something that
# only matters at VPS-rebuild time.
echo "==> Checking docs/nginx-aeds-rag-assistant.conf against the live nginx config"
live_nginx_conf="$(ssh "root@${VPS_HOST}" "cat /etc/nginx/sites-available/aeds-rag-assistant" 2>/dev/null || true)"
local_nginx_conf="$(awk '/^server \{/{found=1} found' docs/nginx-aeds-rag-assistant.conf)"
if [ -z "$live_nginx_conf" ]; then
  echo "    could not read the live nginx config over SSH, skipping the comparison"
elif [ "$live_nginx_conf" != "$local_nginx_conf" ]; then
  echo "    WARNING: docs/nginx-aeds-rag-assistant.conf has drifted from the live VPS config." >&2
  echo "    Update it by hand: ssh root@${VPS_HOST} 'cat /etc/nginx/sites-available/aeds-rag-assistant'" >&2
else
  echo "    in sync"
fi

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
  --exclude 'frontend_backup_*' \
  --exclude '*.log' \
  --exclude '.pytest_cache' \
  ./ "root@${VPS_HOST}:${VPS_APP_DIR}/"

echo "==> Syncing frontend build to VPS web root"
rsync -az --delete frontend/dist/ "root@${VPS_HOST}:${VPS_WEB_ROOT}/"
ssh "root@${VPS_HOST}" "chown -R www-data:www-data ${VPS_WEB_ROOT}"

echo "==> Installing dependencies and running DB migration on VPS"
ssh "root@${VPS_HOST}" "cd ${VPS_APP_DIR} && .venv/bin/pip install -q -r requirements.txt && .venv/bin/python -c 'from db.models import init_db; init_db()'"

# Model choice lives in config.py (the default) and the admin panel (a live
# override) - not in .env. A model line there silently outranks the code
# default, and kept a withdrawn OpenRouter model in production for days
# after the code had moved on. Removed here, with a dated backup of the file
# first, and only when such a line exists.
echo "==> Removing OpenRouter model lines from the VPS .env (model choice is config.py + admin panel)"
ssh "root@${VPS_HOST}" "cd ${VPS_APP_DIR} && if grep -qE '^(OPENROUTER_MODEL|OPENROUTER_FALLBACK_MODEL)=' .env; then cp .env .env.bak-\$(date +%Y%m%d%H%M%S) && sed -i -E '/^(OPENROUTER_MODEL|OPENROUTER_FALLBACK_MODEL)=/d' .env && echo '    removed (backup saved next to .env)'; else echo '    none present'; fi"

# Before the restart, so a cleared admin-panel value takes effect with it
# (the running app caches its effective config).
echo "==> Checking the configured OpenRouter models still exist"
ssh "root@${VPS_HOST}" "cd ${VPS_APP_DIR} && PYTHONPATH=. .venv/bin/python scripts/check_llm_models.py --fix" || \
  echo "    WARNING: a configured model is still unavailable - see above, and switch it in the admin panel." >&2

# The app holds the embedding model and the reranker in memory, about
# 2.9 GB steady with a 3.2 GB peak. The ceiling is a safety net against a
# leak on a box with no swap, not a budget: pm2 restarts the app past it.
PM2_MAX_MEMORY="4500M"

echo "==> Restarting pm2 (memory ceiling ${PM2_MAX_MEMORY})"
ssh "root@${VPS_HOST}" "source ~/.nvm/nvm.sh 2>/dev/null; pm2 restart ${PM2_APP_NAME} --max-memory-restart ${PM2_MAX_MEMORY} && pm2 save"

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
