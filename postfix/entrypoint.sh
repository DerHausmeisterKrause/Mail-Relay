#!/bin/sh
set -eu

mkdir -p /etc/postfix/generated /var/log /certs
for f in allowed_sender_domains sender_relay transport sasl_passwd; do
  [ -f "/etc/postfix/generated/$f" ] || touch "/etc/postfix/generated/$f"
done

normalize_allowed_sender_map() {
  in="/etc/postfix/generated/allowed_sender_domains"
  tmp="/etc/postfix/generated/.allowed_sender_domains.tmp"
  awk '
    NF == 0 { next }
    /^#/ { next }
    NF == 1 { print $1 " OK"; next }
    { print $0 }
  ' "$in" > "$tmp"
  mv "$tmp" "$in"
}

ensure_tls_material() {
  if [ ! -s /certs/tls.crt ] || [ ! -s /certs/tls.key ]; then
    openssl req -x509 -nodes -newkey rsa:2048 \
      -keyout /certs/tls.key \
      -out /certs/tls.crt \
      -days 365 \
      -subj '/CN=mail-relay.local' >/dev/null 2>&1
  fi
}

apply_reject_footer() {
  if [ -f /etc/postfix/generated/reject_response_message ]; then
    msg=$(tr '\n' ' ' < /etc/postfix/generated/reject_response_message | sed 's/[[:space:]]\+/ /g' | sed 's/^ //;s/ $//')
    postconf -e "smtpd_reject_footer = $msg" || true
  fi
}

normalize_allowed_sender_map
ensure_tls_material
postmap hash:/etc/postfix/generated/allowed_sender_domains || true
postmap hash:/etc/postfix/generated/sender_relay || true
postmap hash:/etc/postfix/generated/transport || true
postmap hash:/etc/postfix/generated/sasl_passwd || true
chmod 600 /etc/postfix/generated/sasl_passwd* || true
apply_reject_footer

postfix start
while true; do
  if [ -f /etc/postfix/generated/.reload ]; then
    rm -f /etc/postfix/generated/.reload
    normalize_allowed_sender_map
    postmap hash:/etc/postfix/generated/allowed_sender_domains || true
    postmap hash:/etc/postfix/generated/sender_relay || true
    postmap hash:/etc/postfix/generated/transport || true
    postmap hash:/etc/postfix/generated/sasl_passwd || true
    apply_reject_footer
    postfix reload
  fi
  sleep 2
done
