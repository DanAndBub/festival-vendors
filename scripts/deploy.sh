#!/bin/bash
# Deploy Festival Vendor Directory to VPS
#
# Prerequisites (Dan does once):
#   1. Provision VPS (Hetzner CX22 recommended)
#   2. Point domain DNS to VPS IP
#   3. SSH key access configured
#   4. Run VPS setup section below once
#
# Usage: ./deploy.sh <vps_user@vps_ip> <domain>
# Example: ./deploy.sh root@123.45.67.89 trippyvendors.com

set -e

VPS="${1:?Usage: ./deploy.sh <user@host> <domain>}"
DOMAIN="${2:?Usage: ./deploy.sh <user@host> <domain>}"
REMOTE_DIR="/var/www/${DOMAIN}"

echo "=== Deploying to ${VPS} ==="
echo "Domain: ${DOMAIN}"
echo "Remote dir: ${REMOTE_DIR}"

# -----------------------------------------------
# VPS FIRST-TIME SETUP (run with --setup flag)
# -----------------------------------------------
if [ "$3" == "--setup" ]; then
    echo ""
    echo "[SETUP] Configuring VPS for first time..."

    ssh "${VPS}" bash -s "${DOMAIN}" "${REMOTE_DIR}" << 'SETUPEOF'
DOMAIN=$1
REMOTE_DIR=$2

# Install nginx and certbot
apt update && apt install -y nginx certbot python3-certbot-nginx

# Create site directory
mkdir -p ${REMOTE_DIR}

# Nginx config
cat > /etc/nginx/sites-available/${DOMAIN} << NGINXEOF
server {
    listen 80;
    server_name ${DOMAIN} www.${DOMAIN};
    root ${REMOTE_DIR};
    index index.html;

    # Gzip
    gzip on;
    gzip_types text/plain text/css application/json application/javascript;

    # Cache static assets
    location ~* \.(json|css|js|png|jpg|ico|svg)$ {
        expires 1h;
        add_header Cache-Control "public, immutable";
    }

    # SPA fallback
    location / {
        try_files \$uri \$uri/ /index.html;
    }
}
NGINXEOF

# Enable site
ln -sf /etc/nginx/sites-available/${DOMAIN} /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# SSL
certbot --nginx -d ${DOMAIN} -d www.${DOMAIN} --non-interactive --agree-tos --email admin@${DOMAIN} || \
echo "Certbot failed — DNS may not have propagated yet. Run manually: certbot --nginx -d ${DOMAIN}"

echo "[SETUP] VPS setup complete!"
SETUPEOF
    exit 0
fi

# -----------------------------------------------
# DEPLOY (runs every time)
# -----------------------------------------------
echo ""
echo "[DEPLOY] Syncing website files..."

# Sync website directory to VPS
rsync -avz --delete \
    website/index.html \
    website/vendors.json \
    "${VPS}:${REMOTE_DIR}/"

echo ""
echo "[DEPLOY] Done! Site live at https://${DOMAIN}"
