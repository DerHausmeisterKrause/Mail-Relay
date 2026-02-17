#!/bin/sh
set -eu
RUNTIME=/runtime/cluster.json
while [ ! -f "$RUNTIME" ]; do sleep 2; done
render(){
  VIP=$(jq -r '.vip_address' "$RUNTIME")
  IFACE=$(jq -r '.vrrp_interface' "$RUNTIME")
  RID=$(jq -r '.vrrp_router_id' "$RUNTIME")
  PRIO=$(jq -r '.vrrp_priority' "$RUNTIME")
  PASS=$(jq -r '.vrrp_auth_pass' "$RUNTIME")
  cat > /etc/keepalived/keepalived.conf <<CFG
vrrp_script chk_backend { script "/scripts/check_backend.sh"; interval 2; timeout 1; rise 2; fall 2; }
vrrp_instance VI_1 {
  state BACKUP
  interface $IFACE
  virtual_router_id $RID
  priority $PRIO
  advert_int 1
  authentication { auth_type PASS; auth_pass $PASS }
  virtual_ipaddress { $VIP/24 dev $IFACE }
  track_script { chk_backend }
}
CFG
}
render
keepalived --dont-fork --log-console &
PID=$!
LAST=""
while true; do SUM=$(sha256sum "$RUNTIME"|awk '{print $1}'); if [ "$SUM" != "$LAST" ]; then LAST="$SUM"; render; kill -HUP "$PID" || true; fi; sleep 3; done
