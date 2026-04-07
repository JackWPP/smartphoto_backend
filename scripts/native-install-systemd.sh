#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

UNIT_SOURCE_DIR="${UNIT_SOURCE_DIR:-${ROOT_DIR}/deploy/systemd}"
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "native-install-systemd.sh must run as root because it writes ${SYSTEMD_DIR}." >&2
  exit 1
fi

for unit in smartphoto-api.service smartphoto-worker.service smartphoto-migrate.service; do
  if [[ ! -f "${UNIT_SOURCE_DIR}/${unit}" ]]; then
    echo "Missing systemd unit template: ${UNIT_SOURCE_DIR}/${unit}" >&2
    exit 1
  fi
  install -m 0644 "${UNIT_SOURCE_DIR}/${unit}" "${SYSTEMD_DIR}/${unit}"
done

systemctl daemon-reload
systemctl enable smartphoto-api.service smartphoto-worker.service

echo "Installed SmartPhoto systemd units:"
systemctl list-unit-files 'smartphoto-*.service' --no-pager
