# Mail-Relay HA

## Start (Zero Touch)

```bash
git clone <repo>
cd Mail-Relay
docker compose up -d --build
```

Danach alles über die Web-GUI konfigurieren: `https://<node-ip>:8443`.

## GUI-first Konfiguration

In der GUI konfigurierbar:
- Node/Cluster: NODE_ID, NODE_IP, PEER_NODE_IP, VIP, VRRP Priority
- Mode: standalone/master/slave
- Master API URL/Token (für slave)
- TLS Zertifikat/Key
- SSH Key + known_hosts + Peer SSH User für Queue Sync

## Architektur

- Postfix SMTP Relay mit optionalem STARTTLS
- keepalived VIP Failover (Active = VIP Owner)
- queue-sync nur Active -> Passive via rsync+SSH
- PostgreSQL für Config/Logs/Audit
- FastAPI Backend + HTTPS Frontend

## Queue Sync Sicherheit

- VIP ownership check
- DB lock (`cluster_locks`) gegen split-brain
- Safe sync: postfix stop -> rsync -> postfix start
- niemals Passive -> Active sync

## Troubleshooting

- Merge-Konflikte schnell lösen:
```bash
./scripts/resolve_merge_conflicts.sh
```
- Für Web-PR Merge ist `.gitattributes` mit `merge=ours` für Konfliktdateien gesetzt.
