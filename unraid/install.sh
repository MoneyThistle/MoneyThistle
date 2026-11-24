#!/bin/bash
# Build and start MoneyThistle on an Unraid server.
#
#   1. Copy the whole app folder to the server, e.g. /mnt/user/appdata/moneythistle/src
#      (a share over SMB works: \\TOWER\appdata\moneythistle\src).
#   2. Open the Unraid terminal (>_ icon) and run:
#        bash /mnt/user/appdata/moneythistle/src/unraid/install.sh
#   3. Open http://TOWER:8080 (or the server's Tailscale name/IP) in a browser.
#
# Run it again after copying a newer version: it rebuilds the image and recreates
# the container. Your data and backups are kept.
#
# Settings can be given as variables, e.g.:
#   APP_PASSWORD='secret' PORT=8090 TZ=Europe/Berlin bash install.sh
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
NAME="${NAME:-moneythistle}"
IMAGE="moneythistle:latest"
PORT="${PORT:-8080}"
# Before the rename MoneyThistle was installed as "home-ledger". An install that
# already has its money file there keeps using that folder (nothing is moved).
OLD_NAME="home-ledger"
OLD_APPDATA="/mnt/user/appdata/home-ledger"
if [ -z "${APPDATA:-}" ] && [ ! -d /mnt/user/appdata/moneythistle/data ] && [ -d "$OLD_APPDATA/data" ]; then
  APPDATA="$OLD_APPDATA"
  echo "Using your existing data in $OLD_APPDATA (from when MoneyThistle was called home-ledger)."
fi
APPDATA="${APPDATA:-/mnt/user/appdata/moneythistle}"
DATA="${DATA:-$APPDATA/data}"
BACKUPS="${BACKUPS:-$APPDATA/backups}"
TZ_VALUE="${TZ:-$(cat /etc/timezone 2>/dev/null || echo Etc/UTC)}"

echo "Building the image from $SRC ..."
docker build -t "$IMAGE" "$SRC"

mkdir -p "$DATA" "$BACKUPS"

# Keep the sign-in password from a previous install (under either name) unless a new one is given.
for c in "$NAME" "$OLD_NAME"; do
  if [ -z "${APP_PASSWORD:-}" ] && docker inspect "$c" >/dev/null 2>&1; then
    APP_PASSWORD="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$c" | sed -n 's/^APP_PASSWORD=//p')"
  fi
done
if [ -z "${APP_PASSWORD:-}" ]; then
  read -r -s -p "Password for the first administrator, 8+ characters (empty = create it in the browser): " APP_PASSWORD || true
  echo
fi

for c in "$NAME" "$OLD_NAME"; do
  if docker inspect "$c" >/dev/null 2>&1; then
    echo "Replacing the old container '$c' (data is kept) ..."
    docker stop -t 60 "$c" >/dev/null || true
    docker rm "$c" >/dev/null
  fi
done

ENV_ARGS=(-e TZ="$TZ_VALUE" -e PUID=99 -e PGID=100 -e APP_USERNAME="${APP_USERNAME:-admin}")
[ -n "${APP_PASSWORD:-}" ] && ENV_ARGS+=(-e APP_PASSWORD="$APP_PASSWORD")
[ -n "${WEBDAV_URL:-}" ] && ENV_ARGS+=(-e WEBDAV_URL="$WEBDAV_URL")
[ -n "${WEBDAV_USER:-}" ] && ENV_ARGS+=(-e WEBDAV_USER="$WEBDAV_USER")
[ -n "${WEBDAV_PASSWORD:-}" ] && ENV_ARGS+=(-e WEBDAV_PASSWORD="$WEBDAV_PASSWORD")
[ -n "${CURRENCY_SYMBOL:-}" ] && ENV_ARGS+=(-e CURRENCY_SYMBOL="$CURRENCY_SYMBOL")

# The addresses people can open, shown at the bottom of every page in the app.
HOST="$(hostname)"
LANIP="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}' || true)"
TSIP=""; TSNAME=""
if command -v tailscale >/dev/null 2>&1; then
  TSIP="$(tailscale ip -4 2>/dev/null | head -n1 || true)"
  TSNAME="$(tailscale status --json 2>/dev/null | sed -n 's/.*"DNSName": *"\([^"]*\)\.".*/\1/p' | head -n1 || true)"
fi
URLS="http://$HOST:$PORT/"
[ -n "$LANIP" ] && URLS="$URLS,http://$LANIP:$PORT/"
[ -n "$TSNAME" ] && URLS="$URLS,http://$TSNAME:$PORT/"
[ -n "$TSIP" ] && URLS="$URLS,http://$TSIP:$PORT/"
ENV_ARGS+=(-e APP_URLS="$URLS" -e PUBLIC_PORT="$PORT")
# The server's own folders, shown in the app's Settings instead of /app, /data, /backups.
ENV_ARGS+=(-e HOST_APP_DIR="$SRC" -e HOST_DATA_DIR="$DATA" -e HOST_BACKUP_DIR="$BACKUPS")

docker run -d --name "$NAME" \
  --restart unless-stopped --stop-timeout 60 \
  -p "$PORT:8080" \
  -v "$DATA:/data" -v "$BACKUPS:/backups" -v "$SRC:/app:ro" \
  "${ENV_ARGS[@]}" \
  -l net.unraid.docker.managed=dockerman \
  -l "net.unraid.docker.webui=http://[IP]:[PORT:8080]/" \
  "$IMAGE" >/dev/null

# Let the Unraid Docker tab show and edit it like any other container.
TEMPLATES=/boot/config/plugins/dockerMan/templates-user
if [ -d "$TEMPLATES" ]; then
  sed -e "s#<Name>moneythistle</Name>#<Name>$NAME</Name>#" \
      -e "s#<Config Name=\"Web UI port\"\(.*\)>8080</Config>#<Config Name=\"Web UI port\"\1>$PORT</Config>#" \
      -e "s#/mnt/user/appdata/moneythistle/data</Config>#$DATA</Config>#" \
      -e "s#/mnt/user/appdata/moneythistle/backups</Config>#$BACKUPS</Config>#" \
      -e "s#\(Target=\"APP_URLS\".*\)></Config>#\1>$URLS</Config>#" \
      -e "s#/mnt/user/appdata/moneythistle/src</Config>#$SRC</Config>#" \
      "$SRC/unraid/moneythistle.xml" > "$TEMPLATES/my-$NAME.xml"
  # The template from before the rename would show a stopped "home-ledger" entry.
  [ "$NAME" != "$OLD_NAME" ] && rm -f "$TEMPLATES/my-$OLD_NAME.xml"
fi
# The old image isn't used any more; remove it if nothing else does (frees space).
docker image rm "$OLD_NAME:latest" >/dev/null 2>&1 || true

echo
echo "MoneyThistle is running on port $PORT. Open it at:"
echo "  On your network:  http://$HOST:$PORT/"
[ -n "$LANIP" ] && echo "                    http://$LANIP:$PORT/"
[ -n "$TSNAME" ] && echo "  Over Tailscale:   http://$TSNAME:$PORT/"
[ -n "$TSIP" ] && echo "                    http://$TSIP:$PORT/"
[ -z "$TSIP" ] && echo "  Over Tailscale:   http://<server's Tailscale name or 100.x IP>:$PORT/"
echo "The same addresses are shown at the bottom of every page in the app."
echo "It shows in the Docker tab as '$NAME' (click its icon, then WebUI)."
