#!/bin/bash
set -euo pipefail

NODE_ID="${NODE_ID:-node-a}"
VIP="${VIP_ADDRESS:?VIP required}"
PEER="${PEER_NODE_IP:?peer required}"
INTERVAL="${SYNC_INTERVAL_SECONDS:-5}"
API_TOKEN="${API_TOKEN:?api token required}"
BACKEND_URL="http://127.0.0.1:8080"
POSTFIX_CONTAINER_NAME="${POSTFIX_CONTAINER_NAME:-mail-relay-postfix-1}"
LOCK_FILE=/tmp/queue-sync.lock

mkdir -p /root/.ssh
if [ -f /keys/id_rsa ]; then
  cp /keys/id_rsa /root/.ssh/id_rsa
  chmod 600 /root/.ssh/id_rsa
fi
if [ -f /keys/known_hosts ]; then
  cp /keys/known_hosts /root/.ssh/known_hosts
fi

is_vip_owner() {
  ip -4 addr show | grep -q "${VIP}/"
}

acquire_lock() {
  curl -fsS -X POST "$BACKEND_URL/api/sync-lock/acquire" \
    -H "content-type: application/json" \
    -H "x-api-token: $API_TOKEN" \
    -d "{\"node_id\":\"$NODE_ID\",\"is_vip_owner\":true}" >/dev/null
}

safe_sync() {
  flock -n 9 || return 0
  if ! acquire_lock; then
    echo "[$(date -Is)] Split-brain or lock conflict. Sync aborted." >&2
    return 1
  fi

  docker exec "$POSTFIX_CONTAINER_NAME" postfix stop || true
  rsync -aH --delete --numeric-ids /var/spool/postfix/ "root@${PEER}:/var/spool/postfix/"
  docker exec "$POSTFIX_CONTAINER_NAME" postfix start || true
  docker exec "$POSTFIX_CONTAINER_NAME" postqueue -f || true
}

exec 9>"$LOCK_FILE"
while true; do
  if is_vip_owner; then
    safe_sync || true
  fi
  sleep "$INTERVAL"
done
