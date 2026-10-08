#!/usr/bin/env bash
# Abre a mesa em HTTPS para a Phantom injetar a carteira.
# Sem DOMAIN, usa o IPv4 público com nip.io, que aponta de volta para esta VPS.
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "erro: rode como root." >&2
  exit 1
fi

IP="${IP:-$(hostname -I | awk '{print $1}')}"
DOMAIN="${DOMAIN:-${IP}.nip.io}"
SITE=/etc/nginx/sites-available/lastro

if [[ ! "$IP" =~ ^[0-9]+(\.[0-9]+){3}$ ]]; then
  echo "erro: não achei um IPv4 público em hostname -I." >&2
  exit 1
fi

apt-get update
apt-get install -y nginx certbot python3-certbot-nginx

cat > "$SITE" <<EOF
server {
    listen 80;
    server_name ${IP};
    return 301 https://${DOMAIN}\$request_uri;
}

server {
    listen 80;
    server_name ${DOMAIN};
    location / {
        proxy_pass http://127.0.0.1:4181;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
ln -sf "$SITE" /etc/nginx/sites-enabled/lastro
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --register-unsafely-without-email --redirect

echo "HTTPS no ar: https://${DOMAIN}/"
echo "Assessoria: https://${DOMAIN}/reino"
