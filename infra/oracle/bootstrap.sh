#!/usr/bin/env bash
# Provision an Oracle Cloud Free Tier ARM VM (Ubuntu 24.04) for FinView backend.
# Run as the ubuntu user. Idempotent.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/braisntext/FinView.git}"
APP_DIR="$HOME/FinView"
API_DOMAIN="${API_DOMAIN:?set API_DOMAIN (e.g. api-123-45-67-89.nip.io)}"
LETSENCRYPT_EMAIL="${LETSENCRYPT_EMAIL:?set LETSENCRYPT_EMAIL}"

echo "==> apt update + base packages"
sudo apt-get update
sudo apt-get install -y \
    git curl build-essential \
    python3.12 python3.12-venv python3-pip \
    nginx certbot python3-certbot-nginx \
    libpq-dev postgresql-client

echo "==> clone or update repo"
if [ ! -d "$APP_DIR/.git" ]; then
    git clone "$REPO_URL" "$APP_DIR"
else
    git -C "$APP_DIR" pull --ff-only
fi

echo "==> python venv + deps"
cd "$APP_DIR"
if [ ! -d .venv ]; then
    python3.12 -m venv .venv
fi
.venv/bin/pip install --upgrade pip
.venv/bin/pip install .

echo "==> env file (edit /home/ubuntu/FinView/.env.production before starting)"
if [ ! -f .env.production ]; then
    cp infra/oracle/env.production.example .env.production
    chmod 600 .env.production
    echo "!! Edit .env.production with real Neon URL, secrets, frontend URL, then re-run."
    exit 0
fi

echo "==> systemd service"
sudo cp infra/oracle/finview-api.service /etc/systemd/system/finview-api.service
sudo systemctl daemon-reload
sudo systemctl enable finview-api
sudo systemctl restart finview-api

echo "==> nginx reverse proxy"
sudo sed "s/API_DOMAIN/$API_DOMAIN/g" infra/oracle/nginx-finview.conf | \
    sudo tee /etc/nginx/sites-available/finview > /dev/null
sudo ln -sf /etc/nginx/sites-available/finview /etc/nginx/sites-enabled/finview
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx

echo "==> firewall (ufw + iptables)"
sudo ufw allow OpenSSH || true
sudo ufw allow 'Nginx Full' || true
yes | sudo ufw enable || true
# Oracle Ubuntu images ship with iptables blocking inbound — open 80/443
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT || true
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT || true
sudo netfilter-persistent save || true

echo "==> Let's Encrypt cert"
sudo certbot --nginx -d "$API_DOMAIN" \
    --non-interactive --agree-tos -m "$LETSENCRYPT_EMAIL" --redirect

echo "==> done. Test: curl https://$API_DOMAIN/api/health"
