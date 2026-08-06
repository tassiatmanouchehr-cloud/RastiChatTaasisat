# Staging Deployment

Exact steps to bring up RastiChat on a fresh Ubuntu 24.04 VPS that may
already host another site. Every domain below is an example — replace
with your real ones (see `.env.staging.example`).

## 1. Prerequisites on the VPS

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2 nginx certbot git
sudo usermod -aG docker "$USER"   # log out/in for this to take effect
```

DNS: point `chat-staging.rastisi.ir`, `operator-chat-staging.rastisi.ir`,
`platform-chat-staging.rastisi.ir` (A records) at the VPS's public IP
before continuing — `scripts/nginx/issue-certs.sh` refuses to run
otherwise.

## 2. Preflight (read-only — run this first, always)

```bash
git clone <this-repo> /opt/rastichat/app
cd /opt/rastichat/app
scripts/staging/preflight.sh
```

Review the output: existing Docker containers, ports 80/443 usage,
existing Nginx sites/certs, disk/RAM. Nothing is changed by this step.

## 3. Configure

```bash
cp .env.staging.example .env.staging
chmod 600 .env.staging
scripts/generate-secrets.sh   # paste DJANGO_SECRET_KEY/DB_PASSWORD/REDIS_PASSWORD into .env.staging
$EDITOR .env.staging          # fill in domains, CERTBOT_EMAIL, storefront CORS origin
```

See `docs/runbooks/ENVIRONMENT_VARIABLES.md` for what every variable does.

## 4. Nginx + TLS

```bash
sudo scripts/nginx/install-sites.sh .env.staging   # installs the HTTP-only bootstrap config first
sudo scripts/nginx/issue-certs.sh .env.staging      # verifies DNS, then requests real certificates
sudo scripts/nginx/install-sites.sh .env.staging    # re-run: switches to the full HTTPS config now that certs exist
```

## 5. Deploy

```bash
scripts/staging/deploy.sh .env.staging
```

This validates the environment, backs up the database (skipped on a
genuinely first deploy), builds every image, runs migrations once,
starts all services, health-checks the backend, and smoke-tests every
service's port. Stops at the first failing step — see
`docs/runbooks/DEPLOYMENT_ROLLBACK.md` if it does.

## 6. Seed demo data (optional, staging only)

```bash
# Deliberately NOT under /app/media or /app/staticfiles — both of those
# are served publicly by Nginx (see deploy/nginx/sites/backend.conf.template);
# /app/ itself is not.
docker compose -f docker-compose.staging.yml --env-file .env.staging exec backend \
  python manage.py seed_staging_data --yes --output=/app/staging-credentials.txt
docker compose -f docker-compose.staging.yml --env-file .env.staging exec backend \
  cat /app/staging-credentials.txt
# Copy the values out now, then remove the in-container copy — it is never
# re-printed by a later run for accounts that already exist, and it isn't
# needed again after this step:
docker compose -f docker-compose.staging.yml --env-file .env.staging exec backend \
  rm /app/staging-credentials.txt
```

Refuses to run if `ENVIRONMENT=production` — there is no override flag.

## 7. Verify

```bash
scripts/staging/status.sh .env.staging
curl -fsS https://chat-staging.rastisi.ir/api/v1/health/ready/
```

Then run the staging smoke suite (see `e2e/staging-smoke/`):

```bash
cd e2e/staging-smoke
npm install   # first time only — shares @playwright/test with the sibling e2e/ project
SMOKE_BACKEND_URL=https://chat-staging.rastisi.ir \
SMOKE_OPERATOR_URL=https://operator-chat-staging.rastisi.ir \
SMOKE_PLATFORM_URL=https://platform-chat-staging.rastisi.ir \
SMOKE_WIDGET_URL=https://chat-staging.rastisi.ir/widget.js \
SMOKE_WS_URL=wss://chat-staging.rastisi.ir/ws \
SMOKE_PROJECT_KEY=<from seed_staging_data output> \
SMOKE_OWNER_EMAIL=owner@staging.rastichat.local \
SMOKE_OWNER_PASSWORD=<from seed_staging_data output> \
SMOKE_OPERATOR_EMAIL=operator1@staging.rastichat.local \
SMOKE_OPERATOR_PASSWORD=<from seed_staging_data output> \
npx playwright test
```

## 8. Widget embed snippet (for the storefront)

```html
<script src="https://chat-staging.rastisi.ir/widget.js"></script>
<script>
  window.RastiChat.init({
    projectKey: "<Project.public_key>",
    apiBase: "https://chat-staging.rastisi.ir/api/v1",
    wsBase: "wss://chat-staging.rastisi.ir/ws",
  });
</script>
```

Add the storefront's real origin to `CORS_ALLOWED_ORIGINS` in
`.env.staging` before embedding — see "Known limitations" below.

## Load baseline (optional, informational only)

```bash
BASE_URL=https://chat-staging.rastisi.ir \
WS_URL=wss://chat-staging.rastisi.ir/ws \
PROJECT_KEY=<Project.public_key> \
VISITOR_COUNT=50 \
node scripts/staging/load-baseline.mjs
```

See `docs/runbooks/MONITORING_RUNBOOK.md` for what to capture alongside it.

## Known limitations

- CORS/WebSocket-origin allowlists are explicit domain lists
  (`CORS_ALLOWED_ORIGINS`), not wildcard/dynamic — adding a new
  storefront domain requires editing `.env.staging` and restarting the
  backend, not a self-serve step for arbitrary unknown embedding sites.
- Uploaded chat/KB attachments (`/media/...`) use the same
  unguessable-filename access model as local dev, not authenticated
  per-request access control — anyone with the exact URL can view a
  file. Acceptable for the current threat model (matches every existing
  image/voice message), a documented gap if that changes.
- Scenarios 19-20 of the smoke checklist (Redis restart/reconnect,
  container restart persistence) need to restart server-side
  infrastructure and are manual/ops steps — see
  `docs/testing/STAGING_MANUAL_QA.md`.
