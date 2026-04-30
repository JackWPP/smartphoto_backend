#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

UNIT_SOURCE_DIR="${UNIT_SOURCE_DIR:-${ROOT_DIR}/deploy/systemd}"
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"
APP_ROOT="${APP_ROOT:-$ROOT_DIR}"
SHARED_ROOT="${SHARED_ROOT:-${APP_ROOT}/shared}"
SERVICE_USER="${SERVICE_USER:-smartphoto}"
SERVICE_GROUP="${SERVICE_GROUP:-${SERVICE_USER}}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "native-install-systemd.sh must run as root because it writes ${SYSTEMD_DIR}." >&2
  exit 1
fi

if [[ ! -d "$APP_ROOT" ]]; then
  echo "Missing APP_ROOT directory: ${APP_ROOT}" >&2
  exit 1
fi

if [[ ! -d "$SHARED_ROOT" ]]; then
  mkdir -p "$SHARED_ROOT"
fi

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --create-home --home-dir "$APP_ROOT" --shell /sbin/nologin "$SERVICE_USER"
fi

chown -R "$SERVICE_USER:$SERVICE_GROUP" "$APP_ROOT" "$SHARED_ROOT" 2>/dev/null || true

render_unit() {
  local source="$1"
  local target="$2"
  sed \
    -e "s#__APP_ROOT__#${APP_ROOT}#g" \
    -e "s#__SHARED_ROOT__#${SHARED_ROOT}#g" \
    -e "s#__SERVICE_USER__#${SERVICE_USER}#g" \
    -e "s#__SERVICE_GROUP__#${SERVICE_GROUP}#g" \
    "$source" > "$target"
}

for unit in smartphoto-api.service smartphoto-worker.service smartphoto-migrate.service; do
  if [[ ! -f "${UNIT_SOURCE_DIR}/${unit}" ]]; then
    echo "Missing systemd unit template: ${UNIT_SOURCE_DIR}/${unit}" >&2
    exit 1
  fi
  render_unit "${UNIT_SOURCE_DIR}/${unit}" "${SYSTEMD_DIR}/${unit}"
  chmod 0644 "${SYSTEMD_DIR}/${unit}"
done

systemctl daemon-reload
systemctl enable smartphoto-api.service smartphoto-worker.service

echo "Installed SmartPhoto systemd units:"
systemctl list-unit-files 'smartphoto-*.service' --no-pager
