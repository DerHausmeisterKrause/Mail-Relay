import json
import os
import subprocess
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
from fastapi import Depends, FastAPI, Header, HTTPException
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
GENERATED = Path("/generated"); GENERATED.mkdir(parents=True, exist_ok=True)
RUNTIME = Path("/runtime"); RUNTIME.mkdir(parents=True, exist_ok=True)
CERT_DIR = Path("/certs"); CERT_DIR.mkdir(parents=True, exist_ok=True)


def ensure_cluster_settings(db: Session):
    row = db.query(ClusterSetting).order_by(desc(ClusterSetting.id)).first()
    if row:
        return row
    row = ClusterSetting(
        node_id=os.getenv("NODE_ID", "node-a"), node_ip=os.getenv("NODE_IP", "10.0.0.11"),
        peer_node_ip=os.getenv("PEER_NODE_IP", "10.0.0.12"), vip_address=os.getenv("VIP_ADDRESS", "10.0.0.50"),
        vrrp_priority=int(os.getenv("VRRP_PRIORITY", "100")), cluster_mode=os.getenv("CLUSTER_MODE", "standalone"),
        master_api_url=os.getenv("MASTER_API_URL", ""), master_api_token=os.getenv("MASTER_API_TOKEN", ""),
        peer_ssh_user=os.getenv("PEER_SSH_USER", "root"),
    )
    db.add(row); db.commit(); db.refresh(row)
    return row


def write_runtime_artifacts(settings: ClusterSetting):
    (RUNTIME / "cluster.json").write_text(json.dumps({
        "node_id": settings.node_id, "node_ip": settings.node_ip, "peer_node_ip": settings.peer_node_ip,
        "vip_address": settings.vip_address, "vrrp_priority": settings.vrrp_priority, "cluster_mode": settings.cluster_mode,
        "master_api_url": settings.master_api_url, "master_api_token": settings.master_api_token,
        "peer_ssh_user": settings.peer_ssh_user,
        "vrrp_interface": os.getenv("VRRP_INTERFACE", "eth0"),
        "vrrp_router_id": int(os.getenv("VRRP_ROUTER_ID", "51")),
        "vrrp_auth_pass": os.getenv("VRRP_AUTH_PASS", "changevrrppass"),
    }, indent=2))
    if settings.ssh_private_key:
        p = RUNTIME / "id_rsa"; p.write_text(settings.ssh_private_key); os.chmod(p, 0o600)
    if settings.ssh_known_hosts:
        (RUNTIME / "known_hosts").write_text(settings.ssh_known_hosts)
    if settings.tls_crt and settings.tls_key:
        (CERT_DIR / "tls.crt").write_text(settings.tls_crt)
        (CERT_DIR / "tls.key").write_text(settings.tls_key)


def get_effective_cluster_settings(db: Session):
    s = ensure_cluster_settings(db)
    return {
        "node_id": s.node_id, "node_ip": s.node_ip, "peer_node_ip": s.peer_node_ip, "vip_address": s.vip_address,
        "vrrp_priority": s.vrrp_priority, "cluster_mode": s.cluster_mode, "master_api_url": s.master_api_url,
        "master_api_token": s.master_api_token, "peer_ssh_user": s.peer_ssh_user,
        "has_tls": bool(s.tls_crt and s.tls_key), "has_ssh_key": bool(s.ssh_private_key),
    }


def init_admin(db: Session):
    if db.query(User).count() == 0:
        db.add(User(username=os.getenv("ADMIN_DEFAULT_USER", "admin"), password_hash=hash_password(os.getenv("ADMIN_DEFAULT_PASSWORD", "Admin123")), role="Admin", must_change_password=os.getenv("ADMIN_FORCE_PASSWORD_CHANGE", "true").lower() == "true"))
        db.commit()


@app.on_event("startup")
def startup():
    db = next(get_db())
    init_admin(db)
    write_runtime_artifacts(ensure_cluster_settings(db))
    threading.Thread(target=sync_from_master_loop, daemon=True).start()
    threading.Thread(target=retention_loop, daemon=True).start()


def sync_from_master_loop():
    interval = int(os.getenv("SYNC_INTERVAL_SECONDS", "5"))
    while True:
        try:
            db = next(get_db())
            cfg = get_effective_cluster_settings(db)
            if cfg["cluster_mode"].lower() != "slave":
                time.sleep(interval); continue
            if not cfg.get("master_api_url") or not cfg.get("master_api_token"):
                time.sleep(interval); continue
            latest = db.query(func.max(ConfigVersion.version)).scalar() or 0
            r = requests.get(f"{cfg['master_api_url']}/config/export", headers={"x-api-token": cfg['master_api_token']}, timeout=3, verify=False)
            if r.ok:
                payload = r.json()
                if payload.get("version", 0) > latest:
                    d = payload.get("data", {})
                    db.query(DomainPolicy).delete(); db.query(RelayRoute).delete()
                    for dm in d.get("domains", []): db.add(DomainPolicy(domain=dm, enabled=True))
                    for rr in d.get("routes", []): db.add(RelayRoute(**rr))
                    db.add(ConfigVersion(version=payload["version"], data=json.dumps(d), created_by="master-sync", applied=False))
                    db.commit(); render_postfix(db); (GENERATED / ".reload").touch()
        except Exception:
            pass
        time.sleep(interval)


def retention_loop():
    while True:
        try:
            db = next(get_db())
            cutoff = datetime.utcnow() - timedelta(days=int(os.getenv("RETENTION_DAYS", "14")))
            db.query(MailLog).filter(MailLog.created_at < cutoff).delete()
            db.query(RejectionLog).filter(RejectionLog.created_at < cutoff).delete()
            db.commit()
        except Exception:
            pass
        time.sleep(3600)


def current_user(creds: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    try:
        payload = decode_token(creds.credentials)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="invalid token") from exc
    u = db.query(User).filter(User.username == payload["sub"]).first()
    if not u: raise HTTPException(status_code=401, detail="user not found")
    return u


def require_role(u: User, roles: list[str]):
    if u.role not in roles: raise HTTPException(status_code=403, detail="insufficient role")


def snapshot_config(db: Session, actor: str):
    domains = [d.domain for d in db.query(DomainPolicy).filter(DomainPolicy.enabled.is_(True)).all()]
    routes = [{"sender_domain": r.sender_domain, "target_host": r.target_host, "target_port": r.target_port, "tls_mode": r.tls_mode, "tls_verify": r.tls_verify, "auth_username": r.auth_username, "auth_password": r.auth_password} for r in db.query(RelayRoute).all()]
    v = (db.query(func.max(ConfigVersion.version)).scalar() or 0) + 1
    db.add(ConfigVersion(version=v, data=json.dumps({"domains": domains, "routes": routes}), created_by=actor))
    db.add(AuditLog(actor=actor, action="config_saved", payload=f"version={v}")); db.commit(); return v


def render_postfix(db: Session):
    domains = [d.domain for d in db.query(DomainPolicy).filter(DomainPolicy.enabled.is_(True)).all()]
    routes = db.query(RelayRoute).all()
    (GENERATED / "allowed_sender_domains").write_text("\n".join(domains) + "\n")
    (GENERATED / "sender_relay").write_text("\n".join([f"@{r.sender_domain} [{r.target_host}]:{r.target_port}" for r in routes]) + "\n")
    (GENERATED / "transport").write_text("\n".join([f"{r.sender_domain} smtp:[{r.target_host}]:{r.target_port}" for r in routes]) + "\n")
    (GENERATED / "sasl_passwd").write_text("\n".join([f"[{r.target_host}]:{r.target_port} {r.auth_username}:{r.auth_password}" for r in routes if r.auth_username]) + "\n")


@app.post("/api/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.username == req.username).first()
    if not u or not verify_password(req.password, u.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")
    return {"token": create_token(u.username, u.role), "role": u.role, "must_change_password": u.must_change_password}

@app.get("/api/config")
def get_config(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"mode": get_effective_cluster_settings(db)["cluster_mode"], "routes": [r.__dict__ for r in db.query(RelayRoute).all()], "domains": [d.__dict__ for d in db.query(DomainPolicy).all()], "latest_version": db.query(func.max(ConfigVersion.version)).scalar() or 0}

@app.post("/api/domains")
def add_domain(req: DomainRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(user, ["Admin", "Operator"]); db.add(DomainPolicy(domain=req.domain, enabled=True)); db.commit(); return {"status": "saved", "version": snapshot_config(db, user.username)}

@app.post("/api/routes")
def add_route(req: RouteRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(user, ["Admin", "Operator"]); db.add(RelayRoute(**req.model_dump())); db.commit(); return {"status": "saved", "version": snapshot_config(db, user.username)}

@app.post("/api/config/test")
def config_test(user: User = Depends(current_user), db: Session = Depends(get_db)):
    render_postfix(db)
    return {"ok": True}

@app.post("/api/config/apply")
def config_apply(user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(user, ["Admin", "Operator"]); render_postfix(db)
    subprocess.run(["/bin/sh", "-c", "touch /generated/.reload"], capture_output=True, text=True)
    db.add(AuditLog(actor=user.username, action="config_applied", payload="reload")); db.commit(); return {"status": "applied"}

@app.get("/api/dashboard")
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    n = datetime.utcnow()
    return {"processed_24h": db.query(MailLog).filter(MailLog.created_at >= n - timedelta(hours=24)).count(), "processed_1h": db.query(MailLog).filter(MailLog.created_at >= n - timedelta(hours=1)).count(), "rejected_16h": db.query(RejectionLog).filter(RejectionLog.created_at >= n - timedelta(hours=16)).count(), "queue_size": 0, "active_node": get_effective_cluster_settings(db)["node_id"], "rejected_last_100": []}

@app.get("/api/config/export")
def export_config(x_api_token: str = Header(default=""), db: Session = Depends(get_db)):
    if x_api_token != os.getenv("API_TOKEN", "bootstrap-token"): raise HTTPException(status_code=403, detail="forbidden")
    latest = db.query(ConfigVersion).order_by(desc(ConfigVersion.version)).first()
    return {"version": 0, "data": {"domains": [], "routes": []}} if not latest else {"version": latest.version, "data": json.loads(latest.data)}

@app.post("/api/sync-lock/acquire")
def acquire_lock(payload: dict, x_api_token: str = Header(default=""), db: Session = Depends(get_db)):
    if x_api_token != os.getenv("API_TOKEN", "bootstrap-token"): raise HTTPException(status_code=403, detail="forbidden")
    if not payload.get("is_vip_owner", False): raise HTTPException(status_code=400, detail="not active")
    node_id = payload.get("node_id", "unknown"); now = datetime.utcnow()
    ex = db.query(ClusterLock).filter(ClusterLock.lock_name == "queue_sync").first()
    if ex and ex.node_id != node_id and (now - ex.heartbeat).total_seconds() < 20:
        db.add(AuditLog(actor=node_id, action="split_brain_detected", payload=json.dumps(payload))); db.commit(); raise HTTPException(status_code=409, detail="lock owned by other node")
    if ex: ex.node_id = node_id; ex.heartbeat = now
    else: db.add(ClusterLock(lock_name="queue_sync", node_id=node_id, heartbeat=now))
    db.commit(); return {"status": "ok"}

@app.get("/api/cluster/settings")
def get_cluster_settings(user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(user, ["Admin", "Operator", "ReadOnly"]); return get_effective_cluster_settings(db)

@app.post("/api/cluster/settings")
def set_cluster_settings(req: ClusterSettingsRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(user, ["Admin"])
    r = ensure_cluster_settings(db)
    for k, v in req.model_dump().items():
        if v is not None: setattr(r, k, v)
    r.updated_at = datetime.utcnow(); write_runtime_artifacts(r)
    db.add(AuditLog(actor=user.username, action="cluster_settings_updated", payload=json.dumps({"node_id": r.node_id, "mode": r.cluster_mode})))
    db.commit(); return {"status": "saved"}

@app.post("/api/smtp-event")
def smtp_event(event: dict, db: Session = Depends(get_db)):
    if event.get("type") == "reject":
        db.add(RejectionLog(sender=event.get("sender"), recipient=event.get("recipient"), client_ip=event.get("client_ip"), reason=event.get("reason", "rejected")))
    else:
        db.add(MailLog(sender=event.get("sender"), recipient=event.get("recipient"), client_ip=event.get("client_ip"), status=event.get("status", "processed"), target=event.get("target"), tls_used=bool(event.get("tls_used", False))))
    db.commit(); return {"status": "ok"}
