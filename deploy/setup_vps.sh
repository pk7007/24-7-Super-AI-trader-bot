#!/usr/bin/env bash
# One-time setup of the 24/7 paper + shadow bot on an Ubuntu 22.04/24.04 server (x86_64 or ARM).
# Usage on the server, in the folder where you uploaded bundle.tar.gz:
#   tar xzf bundle.tar.gz -C ~/ && sudo bash ~/india-crypto-ai-bot/deploy/setup_vps.sh
# What it does: installs Docker, enables it at boot, builds the image, starts paper + shadow with
# restart=unless-stopped. It never needs or copies exchange keys. It does not start live trading.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

if [ -f .env ]; then
  echo "WARNING: $APP_DIR/.env exists. Paper/shadow do not need it; delete it unless you know why it is here." >&2
fi

# Small servers (1 GB RAM) need swap to build numpy/pandas/lightgbm wheels reliably.
if [ "$(awk '/MemTotal/ {print $2}' /proc/meminfo)" -lt 2000000 ] && ! swapon --show | grep -q .; then
  echo "Adding 2 GB swap file"
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

if ! command -v docker >/dev/null 2>&1; then
  apt-get update
  apt-get install -y docker.io
fi
if ! docker compose version >/dev/null 2>&1; then
  apt-get install -y docker-compose-v2 || apt-get install -y docker-compose-plugin
fi
systemctl enable --now docker

mkdir -p state data models
# Containers run as uid of user "bot" inside the image; let them write state.
chown -R 1000:1000 state data models 2>/dev/null || true
chmod -R u+rwX,g+rwX state data models

docker compose build
docker compose up -d
sleep 5
docker compose ps
echo
echo "Started. Watch the heartbeat with:  docker compose logs -f --tail 20"
echo "Stop with:  docker compose down      Status:  docker compose ps"
