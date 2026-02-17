#!/bin/sh
set -eu
envsubst < /etc/keepalived/keepalived.conf.template > /etc/keepalived/keepalived.conf
exec keepalived --dont-fork --log-console
