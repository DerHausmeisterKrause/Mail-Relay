#!/bin/bash
set -euo pipefail
RUNTIME_JSON=/runtime/cluster.json
INTERVAL="${SYNC_INTERVAL_SECONDS:-5}"
API_TOKEN="${API_TOKEN:-bootstrap-token}"
BACKEND_URL="http://127.0.0.1:8080"
POSTFIX_CONTAINER_NAME="${POSTFIX_CONTAINER_NAME:-mail-relay-postfix-1}"
KEEPALIVED_CONTAINER_NAME="${KEEPALIVED_CONTAINER_NAME:-mail-relay-keepalived-1}"
LOCK_FILE=/tmp/queue-sync.lock
mkdir -p /root/.ssh
load_runtime(){ [ -f "$RUNTIME_JSON" ] || return 1; NODE_ID=$(jq -r '.node_id' "$RUNTIME_JSON"); VIP=$(jq -r '.vip_address' "$RUNTIME_JSON"); PEER=$(jq -r '.peer_node_ip' "$RUNTIME_JSON"); PEER_USER=$(jq -r '.peer_ssh_user // "root"' "$RUNTIME_JSON"); [ -f /runtime/id_rsa ] && cp /runtime/id_rsa /root/.ssh/id_rsa && chmod 600 /root/.ssh/id_rsa; [ -f /runtime/known_hosts ] && cp /runtime/known_hosts /root/.ssh/known_hosts; }
is_vip_owner(){ docker exec "$KEEPALIVED_CONTAINER_NAME" ip -4 addr show 2>/dev/null | grep -q "${VIP}/"; }
acquire_lock(){ curl -fsS -X POST "$BACKEND_URL/api/sync-lock/acquire" -H "content-type: application/json" -H "x-api-token: $API_TOKEN" -d "{\"node_id\":\"$NODE_ID\",\"is_vip_owner\":true}" >/dev/null; }
safe_sync(){ flock -n 9 || return 0; acquire_lock || return 1; docker exec "$POSTFIX_CONTAINER_NAME" postfix stop || true; rsync -aH --delete --numeric-ids /var/spool/postfix/ "${PEER_USER}@${PEER}:/var/spool/postfix/"; docker exec "$POSTFIX_CONTAINER_NAME" postfix start || true; docker exec "$POSTFIX_CONTAINER_NAME" postqueue -f || true; }
exec 9>"$LOCK_FILE"
while true; do if load_runtime && is_vip_owner; then safe_sync || true; fi; sleep "$INTERVAL"; done
