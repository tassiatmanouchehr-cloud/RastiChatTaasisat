#!/bin/bash
# Full deploy flow: validate -> backup (if a stack is already running) ->
# build -> migrate -> deploy -> health check -> smoke test -> done.
# Stops at the first failing step rather than pressing on — see
# docs/runbooks/DEPLOYMENT_ROLLBACK.md for what to do when a step fails.
#
# Usage: scripts/staging/deploy.sh [path-to-env-file] [path-to-compose-file]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${1:-$REPO_ROOT/.env.staging}"
export ENV_FILE
COMPOSE_FILE="${2:-$REPO_ROOT/docker-compose.staging.yml}"
COMPOSE="docker compose -f $COMPOSE_FILE --env-file $ENV_FILE"

echo "=== Step 1/7: Validate environment ==="
if [ ! -f "$ENV_FILE" ]; then
  echo "Env file not found: $ENV_FILE" >&2
  exit 1
fi
# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a
# `config --quiet` exercises every ${VAR:?...} required-variable guard in
# the compose file (secrets, domains, ...) without starting anything.
$COMPOSE config --quiet
echo "Environment OK."
echo

MEDIA_HOST_PATH="${MEDIA_HOST_PATH:-/opt/rastichat/media}"
STATIC_HOST_PATH="${STATIC_HOST_PATH:-/opt/rastichat/staticfiles}"
BACKUP_DIR="${BACKUP_DIR:-/opt/rastichat/backups}"
mkdir -p "$MEDIA_HOST_PATH" "$STATIC_HOST_PATH" "$BACKUP_DIR"

GIT_SHA="$(cd "$REPO_ROOT" && git rev-parse HEAD 2>/dev/null || echo unknown)"
echo "Deploying commit: ${GIT_SHA}"
echo

echo "=== Step 2/7: Backup (skipped if this is the first-ever deploy) ==="
if $COMPOSE ps db --status running 2>/dev/null | grep -q db; then
  "$REPO_ROOT/scripts/staging/backup.sh" "$ENV_FILE" "$COMPOSE_FILE"
else
  echo "No running 'db' service found — nothing to back up yet (first deploy)."
fi
echo

echo "=== Step 3/7: Build images (GIT_SHA=${GIT_SHA}) ==="
$COMPOSE build \
  --build-arg GIT_SHA="$GIT_SHA" \
  --build-arg NEXT_PUBLIC_API_BASE_URL="${NEXT_PUBLIC_API_BASE_URL:?NEXT_PUBLIC_API_BASE_URL must be set}" \
  --build-arg NEXT_PUBLIC_WS_BASE_URL="${NEXT_PUBLIC_WS_BASE_URL:?NEXT_PUBLIC_WS_BASE_URL must be set}"
# Also tag each image with the immutable git SHA (in addition to the
# moving :${IMAGE_TAG:-staging} tag docker-compose.staging.yml itself
# uses) — this is what scripts/staging/rollback.sh retags back onto the
# moving tag to roll back to a previous build WITHOUT needing to rebuild
# or check out old source.
for image in rastichat-backend rastichat-operator-dashboard rastichat-platform-dashboard rastichat-widget; do
  docker tag "${image}:${IMAGE_TAG:-staging}" "${image}:${GIT_SHA}"
done
echo

echo "=== Step 4/7: Run migrations (one-off, before any replica starts on the new image) ==="
$COMPOSE up -d db redis
echo "Waiting for db/redis to report healthy..."
for i in $(seq 1 30); do
  db_health="$($COMPOSE ps db --format '{{.Health}}' 2>/dev/null || echo '')"
  redis_health="$($COMPOSE ps redis --format '{{.Health}}' 2>/dev/null || echo '')"
  if [ "$db_health" = "healthy" ] && [ "$redis_health" = "healthy" ]; then
    break
  fi
  sleep 2
  if [ "$i" -eq 30 ]; then
    echo "db/redis did not become healthy within 60s — aborting before touching migrations." >&2
    exit 1
  fi
done
$COMPOSE run --rm backend migrate
echo

echo "=== Step 5/7: Deploy services ==="
$COMPOSE up -d
echo

echo "=== Step 6/7: Health check ==="
BACKEND_PORT="${BACKEND_PORT:-8100}"
healthy=0
for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${BACKEND_PORT}/api/v1/health/ready/" >/dev/null 2>&1; then
    healthy=1
    break
  fi
  sleep 2
done
if [ "$healthy" -ne 1 ]; then
  echo "Backend did not become ready within 60s after deploy." >&2
  echo "Run scripts/staging/status.sh to inspect, and scripts/staging/rollback.sh if needed." >&2
  exit 1
fi
echo "Backend is ready."
echo

echo "=== Step 7/7: Smoke test ==="
OPERATOR_PORT="${OPERATOR_PORT:-3100}"
PLATFORM_PORT="${PLATFORM_PORT:-3101}"
WIDGET_PORT="${WIDGET_PORT:-8180}"
smoke_failed=0
for check in \
  "backend:http://127.0.0.1:${BACKEND_PORT}/api/v1/health/ready/" \
  "operator-dashboard:http://127.0.0.1:${OPERATOR_PORT}/" \
  "platform-dashboard:http://127.0.0.1:${PLATFORM_PORT}/" \
  "widget:http://127.0.0.1:${WIDGET_PORT}/widget.js"
do
  name="${check%%:*}"; url="${check#*:}"
  code="$(curl -fsS -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || echo ERR)"
  if [ "$code" = "ERR" ] || [ "${code:0:1}" = "5" ]; then
    echo "  ✗ ${name} (${url}) -> ${code}"
    smoke_failed=1
  else
    echo "  ✓ ${name} (${url}) -> ${code}"
  fi
done
if [ "$smoke_failed" -ne 0 ]; then
  echo "Smoke test FAILED — see docs/runbooks/DEPLOYMENT_ROLLBACK.md." >&2
  exit 1
fi
echo

echo "############################################################"
echo "# Deployment successful: ${GIT_SHA}"
echo "# $(date -Iseconds)"
echo "############################################################"
