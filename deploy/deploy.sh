#!/usr/bin/env bash
# Deploy one environment of the BL22 mail-in XAS portal on the app VM.
#
#   sudo /SSRL_LOCAL_OM/ht-xas/dev/deploy/deploy.sh dev  [git-ref]
#   sudo /SSRL_LOCAL_OM/ht-xas/prod/deploy/deploy.sh prod [git-ref]
#
# git-ref defaults to origin/main (e.g. a tag or commit to deploy a specific version).
# Updates the checkout, installs the backend, builds the frontend, restarts the service and
# checks that it answers. See deploy/INSTALL.md for the first-time setup.
set -euo pipefail

ENV_NAME=${1:?usage: deploy.sh dev|prod [git-ref]}
REF=${2:-origin/main}
case "$ENV_NAME" in
    prod) BUILD=build ;;
    dev) BUILD=build:dev ;;
    *) echo "environment must be dev or prod" >&2; exit 1 ;;
esac
[ "$(id -u)" -eq 0 ] || { echo "run with sudo" >&2; exit 1; }

BASE=/SSRL_LOCAL_OM/ht-xas
SRC=$BASE/$ENV_NAME
WWW=$BASE/www/$ENV_NAME
SETTINGS=/etc/ht-xas/$ENV_NAME.env
UV=/usr/local/bin/uv

setting() { sed -n "s/^$1=//p" "$SETTINGS" | tail -n 1; }
PORT=$(setting HT_XAS_PORT)
API_PREFIX=$(setting HT_XAS_API_PREFIX)
[ -n "$PORT" ] && [ -n "$API_PREFIX" ] || {
    echo "HT_XAS_PORT and HT_XAS_API_PREFIX must be set in $SETTINGS" >&2
    exit 1
}

# Everything below runs as the service account, with Python, caches and home on local disk.
as_htxas() {
    sudo -u htxas env HOME="$BASE" \
        UV_PYTHON_INSTALL_DIR="$BASE/python" UV_CACHE_DIR="$BASE/cache/uv" \
        npm_config_cache="$BASE/cache/npm" "$@"
}

echo "== $ENV_NAME: code ($REF)"
as_htxas git -C "$SRC" fetch --quiet --tags origin
as_htxas git -C "$SRC" checkout --quiet --detach "$REF"
VERSION=$(as_htxas git -C "$SRC" rev-parse --short HEAD)

echo "== $ENV_NAME: backend"
(cd "$SRC/backend" && as_htxas "$UV" sync --frozen --no-dev --quiet)

echo "== $ENV_NAME: frontend"
(cd "$SRC/frontend" && as_htxas npm ci --no-audit --no-fund --loglevel=error)
(cd "$SRC/frontend" && as_htxas npm run --silent "$BUILD")
as_htxas find "$WWW" -mindepth 1 -delete
as_htxas cp -a "$SRC/frontend/dist/." "$WWW/"

# SELinux labels for new files (code: usr_t, frontend: httpd_sys_content_t).
restorecon -R "$BASE"

echo "== $ENV_NAME: restart"
systemctl restart "ht-xas@$ENV_NAME"
for _ in $(seq 1 30); do
    if curl -fsS "http://127.0.0.1:$PORT$API_PREFIX/health" >/dev/null 2>&1; then
        echo "== $ENV_NAME: deployed $VERSION, backend answers"
        curl -sS "http://127.0.0.1:$PORT$API_PREFIX/health"; echo
        exit 0
    fi
    sleep 1
done
echo "== $ENV_NAME: backend does not answer; see: journalctl -u ht-xas@$ENV_NAME -n 50" >&2
exit 1
