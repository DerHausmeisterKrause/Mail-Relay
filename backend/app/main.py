import json
import os
import subprocess
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
from fastapi import Depends, FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from .auth import create_token, decode_token, hash_password, verify_password
from .db import get_db
from .models import AuditLog, ClusterLock, ClusterSetting, ConfigVersion, DomainPolicy, MailLog, RelayRoute, RejectionLog, User
from .schemas import ClusterSettingsRequest, DomainRequest, LoginRequest, PasswordChangeRequest, RouteRequest

app = FastAPI(title="Mail Relay HA API")
security = HTTPBearer()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

GENERATED = Path("/generated")
GENERATED.mkdir(parents=True, exist_ok=True)
RUNTIME = Path("/runtime")
RUNTIME.mkdir(parents=True, exist_ok=True)
CERT_DIR = Path("/certs")


def ensure_cluster_settings(db: Session):
    row = db.query(ClusterSetting).order_by(desc(ClusterSetting.id)).first()
    if row:
        return row
    row = ClusterSetting(
        node_id=os.getenv("NODE_ID", "node-a"),
        node_ip=os.getenv("NODE_IP", "10.0.0.11"),
        peer_node_ip=os.getenv("PEER_NODE_IP", "10.0.0.12"),
        vip_address=os.getenv("VIP_ADDRESS", "10.0.0.50"),
        vrrp_priority=int(os.getenv("VRRP_PRIORITY", "100")),
        cluster_mode=os.getenv("CLUSTER_MODE", "standalone"),
        master_api_url=os.getenv("MASTER_API_URL", ""),
        master_api_token=os.getenv("MASTER_API_TOKEN", ""),
        peer_ssh_user=os.getenv("PEER_SSH_USER", "root"),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def write_runtime_artifacts(settings: ClusterSetting):
    runtime_json = {
        "node_id": settings.node_id,
        "node_ip": settings.node_ip,
        "peer_node_ip": settings.peer_node_ip,
        "vip_address": settings.vip_address,
        "vrrp_priority": settings.vrrp_priority,
        "cluster_mode": settings.cluster_mode,
        "master_api_url": settings.master_api_url,
        "master_api_token": settings.master_api_token,
        "peer_ssh_user": settings.peer_ssh_user,
        "vrrp_interface": os.getenv("VRRP_INTERFACE", "eth0"),
        "vrrp_router_id": int(os.getenv("VRRP_ROUTER_ID", "51")),
        "vrrp_auth_pass": os.getenv("VRRP_AUTH_PASS", "changevrrppass"),
    }
    (RUNTIME / "cluster.json").write_text(json.dumps(runtime_json, indent=2))

    if settings.ssh_private_key:
        key = RUNTIME / "id_rsa"
        key.write_text(settings.ssh_private_key)
        os.chmod(key, 0o600)
    if settings.ssh_known_hosts:
        (RUNTIME / "known_hosts").write_text(settings.ssh_known_hosts)

    if settings.tls_crt and settings.tls_key:
        (CERT_DIR / "tls.crt").write_text(settings.tls_crt)
        (CERT_DIR / "tls.key").write_text(settings.tls_key)


def get_effective_cluster_settings(db: Session) -> dict:
    row = ensure_cluster_settings(db)
    return {
        "node_id": row.node_id,
        "node_ip": row.node_ip,
        "peer_node_ip": row.peer_node_ip,
        "vip_address": row.vip_address,
        "vrrp_priority": row.vrrp_priority,
        "cluster_mode": row.cluster_mode,
        "master_api_url": row.master_api_url,
        "master_api_token": row.master_api_token,
        "peer_ssh_user": row.peer_ssh_user,
        "has_tls": bool(row.tls_crt and row.tls_key),
        "has_ssh_key": bool(row.ssh_private_key),
    }


def init_admin(db: Session):
    if db.query(User).count() == 0:
        db.add(
            User(
                username=os.getenv("ADMIN_DEFAULT_USER", "admin"),
                password_hash=hash_password(os.getenv("ADMIN_DEFAULT_PASSWORD", "Admin123")),
                role="Admin",
                must_change_password=os.getenv("ADMIN_FORCE_PASSWORD_CHANGE", "true").lower() == "true",
            )
        )
        db.commit()


def sync_from_master_loop():
    interval = int(os.getenv("SYNC_INTERVAL_SECONDS", "5"))
    while True:
        try:
            db = next(get_db())
            cfg = get_effective_cluster_settings(db)
            if (cfg.get("cluster_mode") or "standalone").lower() != "slave":
                time.sleep(interval)
                continue
            master_url = cfg.get("master_api_url") or ""
            token = cfg.get("master_api_token") or ""
            if not master_url or not token:
                time.sleep(interval)
                continue
            latest_local = db.query(func.max(ConfigVersion.version)).scalar() or 0
            r = requests.get(f"{master_url}/config/export", headers={"x-api-token": token}, timeout=3, verify=False)
            if r.ok:
                data = r.json()
                if data.get("version", 0) > latest_local:
                    payload = data.get("data", {})
                    db.query(DomainPolicy).delete()
                    db.query(RelayRoute).delete()
                    for d in payload.get("domains", []):
                        db.add(DomainPolicy(domain=d, enabled=True))
                    for rr in payload.get("routes", []):
                        db.add(RelayRoute(**rr))
                    db.add(ConfigVersion(version=data["version"], data=json.dumps(payload), created_by="master-sync", applied=False))
                    db.commit()
                    render_postfix(db)
                    (GENERATED / ".reload").touch()
        except Exception:
            pass
        time.sleep(interval)


def retention_loop():
    days = int(os.getenv("RETENTION_DAYS", "14"))
    while True:
        try:
            db = next(get_db())
            cutoff = datetime.utcnow() - timedelta(days=days)
            db.query(MailLog).filter(MailLog.created_at < cutoff).delete()
            db.query(RejectionLog).filter(RejectionLog.created_at < cutoff).delete()
            db.commit()
        except Exception:
            pass
        time.sleep(3600)


@app.on_event("startup")
def startup():
    db = next(get_db())
    init_admin(db)
    settings = ensure_cluster_settings(db)
    write_runtime_artifacts(settings)
    threading.Thread(target=sync_from_master_loop, daemon=True).start()
    threading.Thread(target=retention_loop, daemon=True).start()


def current_user(creds: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    try:
        payload = decode_token(creds.credentials)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="invalid token") from exc
    user = db.query(User).filter(User.username == payload["sub"]).first()
    if not user:
        raise HTTPException(status_code=401, detail="user not found")
    return user


def require_role(user: User, roles: list[str]):
    if user.role not in roles:
        raise HTTPException(status_code=403, detail="insufficient role")


def snapshot_config(db: Session, actor: str):
    domains = [d.domain for d in db.query(DomainPolicy).filter(DomainPolicy.enabled.is_(True)).all()]
    routes = [{"sender_domain": r.sender_domain, "target_host": r.target_host, "target_port": r.target_port, "tls_mode": r.tls_mode, "tls_verify": r.tls_verify, "auth_username": r.auth_username, "auth_password": r.auth_password} for r in db.query(RelayRoute).all()]
    last = db.query(func.max(ConfigVersion.version)).scalar() or 0
    entry = ConfigVersion(version=last + 1, data=json.dumps({"domains": domains, "routes": routes}), created_by=actor)
    db.add(entry)
    db.add(AuditLog(actor=actor, action="config_saved", payload=entry.data))
    db.commit()
    return entry.version


def render_postfix(db: Session):
    domains = [d.domain for d in db.query(DomainPolicy).filter(DomainPolicy.enabled.is_(True)).all()]
    routes = db.query(RelayRoute).all()
    (GENERATED / "allowed_sender_domains").write_text("\n".join(domains) + "\n")
    (GENERATED / "sender_relay").write_text("\n".join([f"@{r.sender_domain} [{r.target_host}]:{r.target_port}" for r in routes]) + "\n")
    (GENERATED / "transport").write_text("\n".join([f"{r.sender_domain} smtp:[{r.target_host}]:{r.target_port}" for r in routes]) + "\n")
    (GENERATED / "sasl_passwd").write_text("\n".join([f"[{r.target_host}]:{r.target_port} {r.auth_username}:{r.auth_password}" for r in routes if r.auth_username]) + "\n")


@app.post("/api/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")
    return {"token": create_token(user.username, user.role), "role": user.role, "must_change_password": user.must_change_password}


@app.post("/api/change-password")
def change_password(req: PasswordChangeRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(req.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="invalid old password")
    user.password_hash = hash_password(req.new_password)
    user.must_change_password = False
    db.add(AuditLog(actor=user.username, action="password_changed", payload=None))
    db.commit()
    return {"status": "ok"}


@app.get("/api/config")
def get_config(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {
        "mode": get_effective_cluster_settings(db).get("cluster_mode", "standalone"),
        "routes": [r.__dict__ for r in db.query(RelayRoute).all()],
        "domains": [d.__dict__ for d in db.query(DomainPolicy).all()],
        "latest_version": db.query(func.max(ConfigVersion.version)).scalar() or 0,
    }


@app.post("/api/routes")
def add_route(req: RouteRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(user, ["Admin", "Operator"])
    db.add(RelayRoute(**req.model_dump()))
    db.commit()
    return {"status": "saved", "version": snapshot_config(db, user.username)}


@app.post("/api/domains")
def add_domain(req: DomainRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(user, ["Admin", "Operator"])
    db.add(DomainPolicy(domain=req.domain, enabled=True))
    db.commit()
    return {"status": "saved", "version": snapshot_config(db, user.username)}


@app.post("/api/config/test")
def config_test(user: User = Depends(current_user), db: Session = Depends(get_db)):
    render_postfix(db)
    return {"ok": True, "checks": {"domains": (GENERATED / "allowed_sender_domains").exists(), "sender_relay": (GENERATED / "sender_relay").exists(), "transport": (GENERATED / "transport").exists()}}


@app.post("/api/config/apply")
def config_apply(user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(user, ["Admin", "Operator"])
    render_postfix(db)
    subprocess.run(["/bin/sh", "-c", "touch /generated/.reload"], capture_output=True, text=True)
    latest = db.query(ConfigVersion).order_by(desc(ConfigVersion.version)).first()
    if latest:
        latest.applied = True
    db.add(AuditLog(actor=user.username, action="config_applied", payload="reload requested"))
    db.commit()
    return {"status": "applied"}


@app.get("/api/dashboard")
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    now = datetime.utcnow()
    return {
        "processed_24h": db.query(MailLog).filter(MailLog.created_at >= now - timedelta(hours=24)).count(),
        "processed_1h": db.query(MailLog).filter(MailLog.created_at >= now - timedelta(hours=1)).count(),
        "rejected_16h": db.query(RejectionLog).filter(RejectionLog.created_at >= now - timedelta(hours=16)).count(),
        "queue_size": 0,
        "active_node": get_effective_cluster_settings(db).get("node_id"),
        "rejected_last_100": [{"sender": r.sender, "recipient": r.recipient, "reason": r.reason, "created_at": r.created_at.isoformat()} for r in db.query(RejectionLog).order_by(desc(RejectionLog.created_at)).limit(100).all()],
    }


@app.get("/api/config/export")
def export_config(x_api_token: str = Header(default=""), db: Session = Depends(get_db)):
    if x_api_token != os.getenv("API_TOKEN", "bootstrap-token"):
        raise HTTPException(status_code=403, detail="forbidden")
    latest = db.query(ConfigVersion).order_by(desc(ConfigVersion.version)).first()
    return {"version": 0, "data": {"domains": [], "routes": []}} if not latest else {"version": latest.version, "data": json.loads(latest.data)}


@app.post("/api/sync-lock/acquire")
def acquire_lock(payload: dict, x_api_token: str = Header(default=""), db: Session = Depends(get_db)):
    if x_api_token != os.getenv("API_TOKEN", "bootstrap-token"):
        raise HTTPException(status_code=403, detail="forbidden")
    node_id = payload.get("node_id", "unknown")
    if not payload.get("is_vip_owner", False):
        raise HTTPException(status_code=400, detail="not active")
    existing = db.query(ClusterLock).filter(ClusterLock.lock_name == "queue_sync").first()
    now = datetime.utcnow()
    if existing and existing.node_id != node_id and (now - existing.heartbeat).total_seconds() < 20:
        db.add(AuditLog(actor=node_id, action="split_brain_detected", payload=json.dumps(payload)))
        db.commit()
        raise HTTPException(status_code=409, detail="lock owned by other node")
    if existing:
        existing.node_id = node_id
        existing.heartbeat = now
    else:
        db.add(ClusterLock(lock_name="queue_sync", node_id=node_id, heartbeat=now))
    db.commit()
    return {"status": "ok"}


@app.get("/api/cluster/settings")
def get_cluster_settings(user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(user, ["Admin", "Operator", "ReadOnly"])
    return get_effective_cluster_settings(db)


@app.post("/api/cluster/settings")
def set_cluster_settings(req: ClusterSettingsRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(user, ["Admin"])
    row = ensure_cluster_settings(db)
    row.node_id = req.node_id
    row.node_ip = req.node_ip
    row.peer_node_ip = req.peer_node_ip
    row.vip_address = req.vip_address
    row.vrrp_priority = req.vrrp_priority
    row.cluster_mode = req.cluster_mode
    row.master_api_url = req.master_api_url
    row.master_api_token = req.master_api_token
    row.peer_ssh_user = req.peer_ssh_user
    row.tls_crt = req.tls_crt or row.tls_crt
    row.tls_key = req.tls_key or row.tls_key
    row.ssh_private_key = req.ssh_private_key or row.ssh_private_key
    row.ssh_known_hosts = req.ssh_known_hosts or row.ssh_known_hosts
    row.updated_at = datetime.utcnow()
    write_runtime_artifacts(row)
    db.add(AuditLog(actor=user.username, action="cluster_settings_updated", payload=json.dumps({"node_id": req.node_id, "mode": req.cluster_mode, "tls_updated": bool(req.tls_crt and req.tls_key), "ssh_updated": bool(req.ssh_private_key)})))
    db.commit()
    return {"status": "saved", "note": "settings applied; keepalived/queue-sync read runtime config automatically"}


@app.post("/api/smtp-event")
def smtp_event(event: dict, db: Session = Depends(get_db)):
    if event.get("type", "mail") == "reject":
        db.add(RejectionLog(sender=event.get("sender"), recipient=event.get("recipient"), client_ip=event.get("client_ip"), reason=event.get("reason", "rejected")))
    else:
        db.add(MailLog(sender=event.get("sender"), recipient=event.get("recipient"), client_ip=event.get("client_ip"), helo=event.get("helo"), rdns=event.get("rdns"), target=event.get("target"), status=event.get("status", "processed"), smtp_code=event.get("smtp_code"), smtp_text=event.get("smtp_text"), tls_used=bool(event.get("tls_used", False)), subject=event.get("subject")))
    db.commit()
    return {"status": "ok"}
