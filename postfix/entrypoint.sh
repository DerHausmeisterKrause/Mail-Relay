#!/bin/sh
set -eu
mkdir -p /etc/postfix/generated /var/log
for f in allowed_sender_domains sender_relay transport sasl_passwd; do [ -f "/etc/postfix/generated/$f" ] || touch "/etc/postfix/generated/$f"; done
postmap hash:/etc/postfix/generated/allowed_sender_domains || true
postmap hash:/etc/postfix/generated/sender_relay || true
postmap hash:/etc/postfix/generated/transport || true
postmap hash:/etc/postfix/generated/sasl_passwd || true
chmod 600 /etc/postfix/generated/sasl_passwd* || true
postfix start
while true; do
  if [ -f /etc/postfix/generated/.reload ]; then rm -f /etc/postfix/generated/.reload; postmap hash:/etc/postfix/generated/allowed_sender_domains || true; postmap hash:/etc/postfix/generated/sender_relay || true; postmap hash:/etc/postfix/generated/transport || true; postmap hash:/etc/postfix/generated/sasl_passwd || true; postfix reload; fi
  sleep 2
done
