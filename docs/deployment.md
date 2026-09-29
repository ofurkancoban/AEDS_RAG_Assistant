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

Deploy is manual and separate from CI - `.github/workflows/tests.yml` runs
`pytest` and a frontend `tsc --noEmit` + `npm run build` on every push and
PR against `main`, but does not deploy. A push that fails CI is a signal to
fix it before running `deploy.sh`, not something CI blocks by itself.

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
0 2 * * *    scripts/update_catalog.py       - refreshes the course catalog cache
0 3 * * *    scripts/source_refresh.py       - checks source documents for changes, notifies on drift
30 3 * * *   scripts/maintenance.py          - backs up app.db and data/chroma, prunes old checkpoints/history
0 5 * * 0    scripts/eval_and_notify.py      - mines new regression cases from admin review decisions, then runs the golden-set quality eval and alerts on regression (Sundays only)
*/15 * * * * scripts/system_health_check.py  - checks VPS disk/memory/load, alerts on breach and on recovery
```

All log to `data/backups/<script>.log`. `system_health_check.py` checks the
shared VPS host itself (disk/memory/load), not just this app - a separate
concern from every other alert in this project, which is about the
application. `eval_and_notify.py` runs weekly
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

If `BACKUP_ENCRYPTION_KEY` is set (see `.env.example`), snapshots are
written as `*.db.enc` / `*.tar.gz.enc` - readable only with that key, which
matters once backups leave the VPS (e.g. copied to a laptop or another
host), since the plaintext copy on the VPS itself is no more or less
exposed than `app.db` already is. To restore one:

```
python -c "
from cryptography.fernet import Fernet
data = Fernet(b'<key>').decrypt(open('<file>.enc', 'rb').read())
open('<file>', 'wb').write(data)
"
```

Existing pre-encryption backups already in `data/backups/` are left as-is;
this only applies to snapshots written after the key is set. Losing the key
means losing every encrypted backup - keep it somewhere other than the VPS
itself.

## Load testing

`scripts/load_test.py` fires concurrent requests at a running instance and
reports latency percentiles and error rate:

```
PYTHONPATH=. python scripts/load_test.py --url http://localhost:8000
PYTHONPATH=. python scripts/load_test.py --url https://aeds-rag-assistant.ofurkan.co \
    --concurrency 20 --requests 200
```

Defaults to `GET /health` - cheap, unauthenticated, not rate limited. `--chat`
instead hits `POST /chat` with a real question, which spends real LLM budget
and counts against the real per-client rate limiter exactly like a genuine
user would; read the script's own docstring before pointing `--chat` at the
production URL, and keep `--requests` small there.
