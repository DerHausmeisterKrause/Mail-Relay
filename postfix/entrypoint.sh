#!/bin/sh
set -eu
mkdir -p /etc/postfix/generated /var/log
touch /var/log/postfix.log

if [ ! -s /certs/tls.crt ] || [ ! -s /certs/tls.key ]; then
  echo "Missing TLS cert/key in /certs. Generate before start." >&2
fi

render_maps() {
  for f in allowed_sender_domains sender_relay transport sasl_passwd; do
    if [ ! -f "/etc/postfix/generated/$f" ]; then
      touch "/etc/postfix/generated/$f"
    fi
  done
  postmap hash:/etc/postfix/generated/allowed_sender_domains || true
  postmap hash:/etc/postfix/generated/sender_relay || true
  postmap hash:/etc/postfix/generated/transport || true
  postmap hash:/etc/postfix/generated/sasl_passwd || true
  chmod 600 /etc/postfix/generated/sasl_passwd* || true
}

render_maps
postfix start

while true; do
  if [ -f /etc/postfix/generated/.reload ]; then
    rm -f /etc/postfix/generated/.reload
    render_maps
    postfix reload
  fi
  sleep 2
done
