# Mail-Relay HA (Docker Compose, Postfix, VIP Failover, Queue Sync)

## TL;DR Zero-Touch Start

```bash
git clone <repo>
cd Mail-Relay
docker compose up -d --build
```

Danach läuft ein Bootstrap-Setup automatisch:
- Default Admin ist verfügbar (`admin / Admin123`, Passwortwechsel beim ersten Login)
- Selbstsigniertes TLS-Zertifikat wird automatisch erstellt (für ersten Zugriff)
- Cluster Runtime-Konfiguration wird in `/runtime` erzeugt
- **Alle weiteren Einstellungen erfolgen in der Web-GUI** (kein manuelles Kopieren von SSH-Keys oder TLS-Dateien nötig)

GUI: `https://<node-ip>:8443`

---

## Architektur

Zwei identische Nodes mit:
- Postfix Relay
- keepalived (VIP Owner = Active Node)
- Queue Sync (nur Active -> Passive)
- PostgreSQL
- FastAPI Backend + HTTPS Frontend

### Persistenz
- `postfix_queue` (Mail Queue)
- `postgres_data` (DB)
- `certs_data` (TLS)
- `runtime_data` (Cluster Runtime Config + SSH Keys für Sync)

---

## Konfiguration ausschließlich über Web-GUI

In der GUI gibt es einen Bereich **Cluster / Node / TLS / SSH**.
Dort konfigurierst du alles, was früher per `.env`/Datei nötig war:

- `NODE_ID`, `NODE_IP`, `PEER_NODE_IP`, `VIP_ADDRESS`
- `VRRP_PRIORITY`
- `cluster_mode`: `standalone`, `master`, `slave`
- bei `slave`: `MASTER_API_URL`, `MASTER_API_TOKEN`
- TLS Zertifikat/Key (optional Replace des Bootstrap-Zertifikats)
- SSH Private Key + `known_hosts` für Queue-Sync zum Peer
- Peer SSH User

> Wichtig: Master/Slave ist **optional**. Beide Nodes können standalone laufen oder nur ein Node als Slave konfiguriert werden.

---

## SMTP / Relay Verhalten

- STARTTLS angeboten, nicht erzwungen
- Kein Open Relay (`reject_unauth_destination`)
- Sender Domain Policy + senderabhängige Relay-Routen
- Robuste Queue/Retry-Parameter

---

## Queue Sync Design (Active -> Passive only)

`queue-sync` liest Runtime-Daten aus `/runtime/cluster.json` (von Backend geschrieben).

Ablauf je Zyklus:
1. VIP lokal vorhanden? (nur dann Active)
2. Split-Brain Lock via Backend API
3. kurzer Freeze: `postfix stop`
4. `rsync` Queue zum Peer (SSH mit GUI-verwaltetem Key)
5. `postfix start`

Es gibt **niemals** Passive -> Active Sync.

---

## Failover

- Fällt Active aus, übernimmt Peer den VIP
- Neuer VIP-Owner wird Active und verarbeitet lokale Queue
- Queue-Daten sind bis zum letzten erfolgreichen Sync auf Peer gespiegelt

Restrisiko: Delta zwischen zwei Sync-Intervallen (`SYNC_INTERVAL_SECONDS`).

---

## Sicherheit

- HTTPS-only GUI
- Passwort Hashing mit Argon2/Bcrypt
- Audit Logging bei Konfig-Änderungen
- Split-Brain Schutz über VRRP + DB Lock

---

## Smoke Tests

```bash
# allowed sender domain
swaks --to user@target.tld --from sender@allowed-domain.tld --server <VIP> --port 25 --tls

# blocked sender domain
swaks --to user@target.tld --from sender@blocked-domain.tld --server <VIP> --port 25
```
