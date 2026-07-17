#!/usr/bin/env bash
set -Eeuo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
DOMAIN="${LETSENCRYPT_DOMAIN:-makonbook.uz}"
WWW_DOMAIN="${LETSENCRYPT_WWW_DOMAIN:-www.makonbook.uz}"
EMAIL="${LETSENCRYPT_EMAIL:-}"
STAGING="${LETSENCRYPT_STAGING:-0}"
PROD_CONFIG="nginx/default.prod.conf"
BOOTSTRAP_CONFIG="nginx/letsencrypt-bootstrap.conf"
BACKUP_CONFIG="nginx/default.prod.conf.bootstrap-backup"

if [[ -z "$EMAIL" ]]; then
  echo "LETSENCRYPT_EMAIL is required in .env or the shell." >&2
  exit 1
fi

if [[ ! -f "$PROD_CONFIG" || ! -f "$BOOTSTRAP_CONFIG" ]]; then
  echo "Missing Nginx production/bootstrap configuration." >&2
  exit 1
fi

restore_config() {
  if [[ -f "$BACKUP_CONFIG" ]]; then
    mv -f "$BACKUP_CONFIG" "$PROD_CONFIG"
  fi
}
trap restore_config EXIT

cp "$PROD_CONFIG" "$BACKUP_CONFIG"
cp "$BOOTSTRAP_CONFIG" "$PROD_CONFIG"

# Start the application and an HTTP-only Nginx so ACME can validate the domain.
docker compose -f "$COMPOSE_FILE" up -d web telegram-bot nginx

staging_arg=()
if [[ "$STAGING" == "1" ]]; then
  staging_arg=(--staging)
fi

# Request or replace the certificate in the named certbot volume.
docker compose -f "$COMPOSE_FILE" run --rm --entrypoint certbot certbot \
  certonly --webroot -w /var/www/certbot \
  "${staging_arg[@]}" \
  --email "$EMAIL" \
  -d "$DOMAIN" -d "$WWW_DOMAIN" \
  --rsa-key-size 4096 \
  --agree-tos \
  --no-eff-email \
  --force-renewal

restore_config
trap - EXIT

docker compose -f "$COMPOSE_FILE" up -d --force-recreate nginx certbot

echo "TLS certificate installed. Open: https://$DOMAIN"
