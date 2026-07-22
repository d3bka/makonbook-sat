#!/usr/bin/env bash
set -Eeuo pipefail

# -----------------------------------------------------------------------------
# ONE-TIME bootstrap: creates the certificate lineage from scratch, on a host
# where nginx cannot start yet because no certificate exists.
#
# NOT needed for the normal cutover — that reuses the existing certificate by
# copying the certbot_conf volume (DEPLOY.md step 4). Use this only if the
# lineage has to be rebuilt from nothing.
#
# Certbot REPLACES a lineage's name set; it never appends. Every name the
# certificate must keep has to appear in LETSENCRYPT_DOMAINS on every run.
# Omitting one silently drops it — the previous version of this script requested
# only makonbook.uz and www, which would have taken sat-makon.uz off the cert
# and broken the static site's TLS.
# -----------------------------------------------------------------------------

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"

# Every name on the shared SAN certificate. The first entry names the lineage
# directory under /etc/letsencrypt/live/ and must stay makonbook.uz so the paths
# in nginx/default.conf keep resolving.
read -r -a DOMAINS <<< "${LETSENCRYPT_DOMAINS:-makonbook.uz www.makonbook.uz sat-makon.uz www.sat-makon.uz}"
CERT_NAME="${LETSENCRYPT_CERT_NAME:-${DOMAINS[0]}}"

EMAIL="${LETSENCRYPT_EMAIL:-support@makonbook.uz}"
STAGING="${LETSENCRYPT_STAGING:-0}"
# Opt-in only. Forced renewal burns Let's Encrypt rate limits (5 duplicate certs
# per week) and is never needed just to change the domain list.
FORCE_RENEWAL="${LETSENCRYPT_FORCE_RENEWAL:-0}"
# The existing lineage uses an ECDSA key; stated so a rebuild does not silently
# migrate it to RSA.
KEY_TYPE="${LETSENCRYPT_KEY_TYPE:-ecdsa}"
PROD_CONFIG="nginx/default.conf"
BOOTSTRAP_CONFIG="nginx/letsencrypt-bootstrap.conf"
BACKUP_CONFIG="nginx/default.conf.bootstrap-backup"

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

extra_args=()
if [[ "$STAGING" == "1" ]]; then
  extra_args+=(--staging)
fi
if [[ "$FORCE_RENEWAL" == "1" ]]; then
  extra_args+=(--force-renewal)
fi

domain_args=()
for d in "${DOMAINS[@]}"; do
  domain_args+=(-d "$d")
done

echo "Requesting certificate '${CERT_NAME}' for: ${DOMAINS[*]}"

# Request or replace the certificate in the named certbot volume.
docker compose -f "$COMPOSE_FILE" run --rm --entrypoint certbot certbot \
  certonly --webroot -w /var/www/certbot \
  --cert-name "$CERT_NAME" \
  "${extra_args[@]}" \
  --email "$EMAIL" \
  "${domain_args[@]}" \
  --key-type "$KEY_TYPE" \
  --agree-tos \
  --no-eff-email

restore_config
trap - EXIT

docker compose -f "$COMPOSE_FILE" up -d --force-recreate nginx certbot

echo "TLS certificate installed for: ${DOMAINS[*]}"
echo "Open: https://${DOMAINS[0]}"
