# Deployment reference

Not read by any code - this documents how the VPS is actually set up, for
rebuilding it if it is ever lost, and so this knowledge doesn't live only in
one person's shell history.

## Deploying a code change

`scripts/deploy.sh` from the repo root. Builds the frontend with the correct
API base, syncs backend and frontend to the server, runs the DB migration,
restarts the app, and waits for `/health` before declaring success. See the
script itself for what it does and does not touch (it never touches
`data/` or `.env` on the server).

## Process manager (pm2)

The backend runs under pm2, started once by hand rather than from a tracked
config file:

```
pm2 start .venv/bin/python \
  --name AEDSRAGAssistant \
  --interpreter none \
  -- -m uvicorn api.main:app --host 0.0.0.0 --port 8001 --forwarded-allow-ips 127.0.0.1
pm2 save
```

`--interpreter none` matters: pm2 defaults to treating the script as
Node.js otherwise. `deploy.sh` only ever calls `pm2 restart AEDSRAGAssistant`
- if the process doesn't exist yet (a fresh host), start it with the command
above first.

## Reverse proxy (nginx)

See `docs/nginx-aeds-rag-assistant.conf` - a reference copy of
`/etc/nginx/sites-available/aeds-rag-assistant`. Its `location ~ ^/(...)`
list must include every path prefix `api/main.py` serves; a path missing
from it silently falls through to serving `index.html` instead of an API
response (this shipped once already, for `/version`).

## Scheduled jobs (crontab, all UTC)

```
0 2 * * *   scripts/update_catalog.py    - refreshes the course catalog cache
0 3 * * *   scripts/source_refresh.py    - checks source documents for changes, notifies on drift
30 3 * * *  scripts/maintenance.py       - backs up app.db and data/chroma, prunes old checkpoints/history
0 5 * * 0   scripts/eval_and_notify.py   - runs the golden-set quality eval, alerts on regression (Sundays only)
```

All log to `data/backups/<script>.log`. `eval_and_notify.py` runs weekly
rather than daily specifically because it spends real LLM quota against
whichever provider is live (see its own docstring) - Sunday 05:00 UTC is
chosen as a low-traffic hour so a full day's OpenRouter budget being spent
on the eval doesn't compete with real users, and the daily budget resets
before Monday classes regardless.

## Backups

`scripts/maintenance.py` (see crontab above) snapshots both `data/sqlite`
and `data/chroma` nightly into `data/backups/`, keeping the last 14 of each.
These backups live on the same disk as the data they protect - they cover a
bad migration or an accidental delete, not a full disk failure. Copy
`data/backups/` off the VPS periodically for that.
