#!/usr/bin/env bash
# LAUNCH-001 controlled production deployment for the Radar services.
#
# Independent of the FDA pipeline worktree: this script never touches /srv/medradar/app,
# /srv/medradar/.venv, medradar-web.service, medradar-data-*.service or the FDA data/data
# snapshots. It installs a release tree, a dedicated virtualenv, a dedicated data directory and
# three systemd units, and it can be rolled back by swapping the release directory back.
#
# Usage:  sudo bash deploy/scripts/deploy_radar.sh <tarball> <commit-sha>
set -euo pipefail

TARBALL="${1:?usage: deploy_radar.sh <tarball> <commit-sha>}"
SHA="${2:?usage: deploy_radar.sh <tarball> <commit-sha>}"
ROOT=/srv/medradar
RADAR_ROOT="$ROOT/radar"
APP="$RADAR_ROOT/app"
RELEASE="$RADAR_ROOT/releases/$SHA"
VENV="$ROOT/radar-venv"
DATA="$ROOT/data/radar"
BACKUP="$DATA/backups"
ENVFILE=/etc/medradar/radar-alpha.env
SERVICE_USER=medradar
UNIT_SRC="$(cd "$(dirname "$0")/.." && pwd)/systemd"

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

if [ "$(id -u)" -ne 0 ]; then
  echo "run as root" >&2
  exit 1
fi

log "release $SHA: staging"
mkdir -p "$RADAR_ROOT/releases" "$DATA" "$BACKUP" /etc/medradar
if [ ! -d "$RELEASE" ]; then
  mkdir -p "$RELEASE"
  tar -xzf "$TARBALL" -C "$RELEASE"
fi
chown -R "$SERVICE_USER":"$SERVICE_USER" "$RADAR_ROOT" "$DATA"
chmod 0750 "$DATA" "$BACKUP"

log "virtualenv"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --quiet --upgrade pip wheel >/dev/null
# Editable install: the release directory is the code, so a directory swap is a deploy and a
# rollback is the same operation in reverse. The module path is verified below.
"$VENV/bin/python" -m pip install --quiet -e "$RELEASE" >/dev/null
INSTALLED=$("$VENV/bin/python" -c 'import medradar, pathlib; print(pathlib.Path(medradar.__file__).resolve().parent)')
log "installed medradar from $INSTALLED"
case "$INSTALLED" in
  "$RELEASE"/*) : ;;
  *) echo "ERROR: venv resolves medradar from $INSTALLED, not $RELEASE" >&2; exit 1 ;;
esac

log "swap release into $APP"
systemctl stop medradar-radar-scheduler.service medradar-radar-web.service 2>/dev/null || true
rm -rf "$RADAR_ROOT/app.previous"
if [ -d "$APP" ]; then mv "$APP" "$RADAR_ROOT/app.previous"; fi
ln -sfn "$RELEASE" "$APP"
# A symlink keeps the venv's editable path valid across releases, so rollback is a relink.
chown -h "$SERVICE_USER":"$SERVICE_USER" "$APP"

log "data directory"
if [ ! -f "$DATA/radar.db" ]; then
  runuser -u "$SERVICE_USER" -- env HOME="$ROOT" MEDRADAR_RADAR_DIR="$DATA" \
    "$VENV/bin/python" -m medradar radar init
fi

log "systemd units"
install -m 0644 "$UNIT_SRC/medradar-radar-scheduler.service" /etc/systemd/system/
install -m 0644 "$UNIT_SRC/medradar-radar-web.service" /etc/systemd/system/
install -m 0644 "$UNIT_SRC/medradar-radar-backup.service" /etc/systemd/system/
install -m 0644 "$UNIT_SRC/medradar-radar-backup.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now medradar-radar-scheduler.service medradar-radar-web.service
systemctl enable --now medradar-radar-backup.timer

log "waiting for the web service"
for _ in $(seq 1 60); do
  if curl -sf -o /dev/null http://127.0.0.1:8791/api/radar/health; then
    log "web is up on 127.0.0.1:8791"
    break
  fi
  sleep 1
done

log "state"
systemctl --no-pager --lines=0 status medradar-radar-scheduler.service medradar-radar-web.service || true
printf '%s\n' "$SHA" > "$RADAR_ROOT/DEPLOYED_SHA"
chown "$SERVICE_USER":"$SERVICE_USER" "$RADAR_ROOT/DEPLOYED_SHA"
log "deployed $SHA"
