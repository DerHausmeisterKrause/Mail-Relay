# Failover Runbook

1. Prüfe VIP auf beiden Nodes (`ip a`), nur ein Node darf VIP halten.
2. Prüfe `queue-sync` Logs auf Active-Only Sync.
3. Prüfe DB lock `cluster_locks` für split-brain detection.
4. Simuliere Ausfall des Active Nodes und verifiziere VIP takeover.
