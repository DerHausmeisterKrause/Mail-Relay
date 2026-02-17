#!/bin/sh
set -eu
mkdir -p /certs
if [ ! -s /certs/tls.crt ] || [ ! -s /certs/tls.key ]; then
  openssl req -x509 -nodes -newkey rsa:2048 -keyout /certs/tls.key -out /certs/tls.crt -days 365 -subj '/CN=mail-relay.local'
fi
exec nginx -g 'daemon off;'
