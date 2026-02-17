# Mail-Relay HA (Docker Compose, Postfix, VIP Failover, Queue Sync)

Produktionsnahes Docker-Compose-Projekt für ein hochverfügbares SMTP Relay mit 2 Nodes (A/B), VIP-Failover über keepalived, Web-GUI, PostgreSQL, Master/Slave Konfigurations-Sync und strikt einseitigem Queue-Sync (nur Active/VIP-Owner -> Passive).

## Repository Struktur

- `docker-compose.yml`
- `.env.example`
- `backend/` FastAPI API, Auth, Config, Dashboard, Audit, Retention, Sync-Lock
- `frontend/` HTTPS GUI (Nginx + SPA)
- `postfix/` Postfix Runtime + Map Reload Mechanismus
- `db/` PostgreSQL Init Schema
- `keepalived/` VRRP / VIP Failover
- `sync/` Queue Sync Container (Safe Sync mit postfix stop/start + rsync)
- `docs/` Zusatzdokumentation
- `docker/` Platzhalter für Host-spezifische Compose Overlays/Skripte

## Architektur

Jeder Node läuft mit identischem Stack.

- **VIP Owner = Active Node**.
- Nur Active akzeptiert produktiv SMTP über VIP und führt Queue-Sync aus.
- Passive hält persistente Queue-Daten lokal, stellt aber ohne VIP nicht aktiv zu.
- Failover: bei Active-Ausfall wandert VIP auf den anderen Node.

### Services

- `postgres`: Persistente DB (users, routes, domains, logs, audit, locks, versions)
- `backend`: GUI/API, Konfig-Versionierung, Apply/Test, Locking, Slave Pull Sync
- `frontend`: HTTPS GUI auf Port 8443
- `postfix`: SMTP Relay auf Port 25, Queue persistent
- `keepalived`: VIP Verwaltung mit VRRP
- `queue-sync`: erkennt VIP Owner, stoppt kurz Postfix, rsync push zum Peer, startet Postfix

## Schnellstart (je Node)

1. Repo auf **Node A** und **Node B** ausrollen.
2. `.env.example` nach `.env` kopieren und pro Node anpassen:
   - `NODE_ID`, `NODE_IP`, `PEER_NODE_IP`, `VIP_ADDRESS`
   - `VRRP_PRIORITY` (A höher, B niedriger)
   - `CLUSTER_MODE` (A `master`, B `slave`)
   - auf Slave: `MASTER_API_URL`, `MASTER_API_TOKEN`
3. TLS Zertifikate in Volume `certs_data` bereitstellen (`tls.crt`, `tls.key`):
   - temporär via bind mount/volume init Script oder Secret-Handling.
4. SSH Key für Queue Sync unter `sync/keys/id_rsa` + `known_hosts` bereitstellen.
5. Starten:

```bash
docker compose up -d --build
```

GUI: `https://<node-ip>:8443`

Default Login: `admin / Admin123` (Passwortwechsel beim ersten Login)

## SMTP Verhalten

- STARTTLS wird angeboten (`smtpd_tls_security_level=may`) und **nicht** erzwungen.
- Kein Open Relay (`reject_unauth_destination`).
- Relay nur anhand erlaubter Senderdomains + senderabhängiger Route (`sender_dependent_relayhost_maps`, `transport_maps`).
- Bei Zielausfall: Postfix Queue + Retry (`maximal_queue_lifetime`, Backoff Tuning).

## Queue Sync (Active -> Passive only)

Container `queue-sync`:

1. Prüft VIP Besitz über `ip addr`.
2. Nur wenn VIP lokal vorhanden: Lock-Acquire via Backend API (`/api/sync-lock/acquire`).
3. Safe Sync:
   - kurzer Freeze per `postfix stop`
   - `rsync -aH --delete /var/spool/postfix/ root@peer:/var/spool/postfix/`
   - `postfix start`
   - optional `postqueue -f`
4. Passive startet niemals Sync in Gegenrichtung.

### Split-Brain Schutz

- VRRP verhindert doppelte VIP Ownership.
- Zusätzlicher DB-Lock (`cluster_locks`) verhindert parallele Sync-Master.
- Bei Lock-Konflikt wird Sync abgebrochen und als Event protokolliert.

## Konfigurations-Sync Master/Slave

- Master verwaltet Konfiguration über GUI.
- Jede Änderung erzeugt `config_version` Snapshot.
- Slave pollt `MASTER_API_URL/api/config/export` (API Token) im Intervall.
- Slave übernimmt nur neuere Versionen und rendert Postfix Maps lokal.

## GUI Features

- Rollen: Admin / Operator / ReadOnly
- Domains Whitelist
- Sender-based Relay Targets (Host/Port/TLS/Auth)
- `Konfiguration testen` (Dateien validieren ohne Reload)
- `Änderungen übernehmen` (Map-Render + Postfix Reload Trigger)
- Dashboard KPIs + letzte Rejects

## Domain Policy Reject + Logging

- Nicht erlaubte Senderdomains werden SMTP-seitig rejected.
- Mail und Reject Events werden in PostgreSQL erfasst (`mail_logs`, `rejection_logs`).
- Retention Job löscht Daten älter als `RETENTION_DAYS` (Default 14).

## Security

- GUI nur HTTPS (Nginx TLS)
- Passwort Hashing via Argon2/Bcrypt (passlib context)
- Audit Log für Konfig-/Passwort-Aktionen
- optionales Anti-Abuse per Env-Toggles (postscreen/RBL/rate limit, im Betrieb erweiterbar)

## Tests

### SMTP Tests (swaks)

```bash
swaks --to user@target.tld --from sender@allowed-domain.tld --server <VIP> --port 25 --tls
swaks --to user@target.tld --from sender@blocked-domain.tld --server <VIP> --port 25
```

### Failover Test

1. SMTP Last auf VIP schicken.
2. Active Node stoppen (z. B. keepalived/postfix Host down).
3. Prüfen: VIP auf Peer vorhanden.
4. SMTP gegen VIP erneut senden.
5. Queue und Zustellung prüfen.

### Queue Sync Test

1. Zielhost absichtlich unerreichbar konfigurieren.
2. Mehrere Mails senden -> Queue wächst auf Active.
3. Prüfen, dass Queue Inhalte auf Passive erscheinen (Intervall 3-10s).
4. Failover auslösen, Zustellung nach Ziel-Recovery prüfen.

## Restrisiken bei rsync Queue

- Bei abruptem Crash zwischen zwei Sync-Läufen kann ein kleines Delta fehlen (Intervall-Risiko).
- Mit aggressivem Intervall (`SYNC_INTERVAL_SECONDS=3..10`) wird RPO reduziert.
- `postfix stop/start` pro Sync erzeugt sehr kurze SMTP-Unterbrechung zugunsten Konsistenz.
- Vollständige Zero-Loss-Semantik ohne shared storage/synchronous replication ist mit rsync allein nicht garantiert.

## Hinweise

- Für echte Produktion: externes Zertifikatsmanagement, Secrets Vault, Härtung der SSH-Policy, Monitoring/Alerting (Prometheus/Loki), dedizierte log parser für Postfix.
