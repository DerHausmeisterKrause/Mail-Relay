# Mail-Relay HA

## Start (Zero Touch)

```bash
git clone <repo>
cd Mail-Relay
docker compose up -d --build
```

Danach alles über die Web-GUI konfigurieren: `https://<node-ip>:8443`.

Hinweis für rootless/restriktive Hosts: SMTP läuft standardmäßig auf Host-Port `2525` (Container-Port `25`).

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


## Port-Mapping (Host)

- `BACKEND_BIND_PORT` (Default `8080`) -> Backend Container `8080`
- `FRONTEND_BIND_PORT` (Default `8443`) -> Frontend Container `8443`
- `SMTP_BIND_PORT` (Default `2525`) -> Postfix Container `25`

Wenn dein Host privilegierte Ports erlaubt, kannst du `SMTP_BIND_PORT=25` setzen.
