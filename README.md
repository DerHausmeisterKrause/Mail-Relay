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
- Mail Tracking & Suche (Filter nach Sender, Empfänger, IP, Status, Ziel) + CSV Export
- Dashboard mit letzten Rejects
- Einstellungen zentral über einen ⚙ Button (Cluster, Node, VIP, Peer Test)
- Node/Cluster: NODE_ID, NODE_IP, PEER_NODE_IP, VIP, VRRP Priority
- Mode: standalone/master/slave
- Master API URL/Token (für slave)
- TLS Zertifikat/Key
- SSH Key + known_hosts + Peer SSH User für Queue Sync
- Failure Antwort für nicht verarbeitbare Mails (manuell einstellbar)

## Architektur

- Postfix SMTP Relay mit optionalem STARTTLS
- keepalived VIP Failover (Active = VIP Owner)
- queue-sync nur Active -> Passive via rsync+SSH
- PostgreSQL für Config/Logs/Audit
- FastAPI Backend + HTTPS Frontend

- Frontend benötigt Schreibzugriff auf `certs_data` beim ersten Start, um Bootstrap-Zertifikate zu erzeugen.

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




## Runtime-Netzwerkmodus (wichtig)

Zur Vermeidung des Host-Fehlers `ip_unprivileged_port_start ... permission denied` laufen die Services standardmäßig mit `network_mode: host`.
Dadurch entfallen Docker Port-Publishings und der Stack startet auch auf restriktiven Hosts zuverlässiger.

Erreichbarkeit nach Start:
- GUI: `https://<HOST-IP>:8443`
- SMTP: `<HOST-IP>:25`
- Backend API: `http://<HOST-IP>:8080`


## Benutzerverwaltung
- In der Web-GUI gibt es jetzt den Bereich **Benutzerverwaltung** (nur Admin): Benutzer anlegen, Rollen (Admin/Operator/ReadOnly) ändern und Passwörter zurücksetzen.
- Beim Passwort-Reset wird `must_change_password` gesetzt, damit der Nutzer beim nächsten Login ein neues Passwort setzen muss.

## Postfix Start-Stabilität
- Der Postfix-Entrypoint normalisiert `allowed_sender_domains` automatisch in gültige `check_sender_access`-Map-Einträge (`<domain> OK`).
- Falls noch keine TLS-Dateien vorhanden sind, werden Start-Zertifikate im Postfix-Container erzeugt, damit der Dienst nicht in einen Restart-Loop läuft.
