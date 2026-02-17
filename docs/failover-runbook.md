# Failover Runbook

1. `ip a` auf beiden Nodes prüfen.
2. VIP muss genau auf einem Node sichtbar sein.
3. Bei Störung keepalived Logs prüfen.
4. Queue-Sync Logs prüfen (`docker compose logs -f queue-sync`).
5. Backend Lock Zustand in DB prüfen (`cluster_locks`).
