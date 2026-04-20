#!/usr/bin/env bash
# Bootstrap a fresh Debian/Ubuntu machine to the state where ci-start.sh and
# ci-test.sh can run. Idempotent — safe to re-run.
set -euo pipefail

cd "$(dirname "$(readlink -f -- "$0")")/../.."

if command -v apt-get >/dev/null; then
    sudo -v
    sudo apt-get update -qq
    pkgs=()
    for p in curl docker.io docker-compose-v2 libimage-exiftool-perl libvips-dev; do
        dpkg -s "$p" >/dev/null 2>&1 || pkgs+=("$p")
    done
    if [ "${#pkgs[@]}" -gt 0 ]; then
        sudo apt-get install -y -qq "${pkgs[@]}"
    fi
fi

if ! id -nG "$USER" | grep -qw docker; then
    sudo usermod -aG docker "$USER"
    echo "added $USER to docker group — log out/in (or 'newgrp docker') for it to take effect"
fi

command -v uv   >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
command -v bun  >/dev/null || [ -d "$HOME/.bun" ] || curl -fsSL https://bun.sh/install | bash
[ -d "$HOME/.nvm" ] || curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash

copy_if_missing() {
    if [ ! -f "$2" ]; then
        cp "$1" "$2"
        echo "created $2 from $1"
    fi
}
copy_if_missing .env.example .env
copy_if_missing frontend/.env.example frontend/.env
copy_if_missing backend/worker/.env.example backend/worker/.env

mkdir -p secrets
[ -f secrets/MAPILLARY_CLIENT_TOKEN ] || echo "placeholder" > secrets/MAPILLARY_CLIENT_TOKEN
[ -f secrets/firebase_credentials ]    || : > secrets/firebase_credentials

docker volume create pics >/dev/null 2>&1 || sudo docker volume create pics >/dev/null

echo "ci-init.sh complete"
