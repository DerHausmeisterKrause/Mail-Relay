import json
import os
import subprocess
import threading
import time
import requests
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from .db import get_db
from .models import User, DomainPolicy, RelayRoute, ConfigVersion, MailLog, RejectionLog, AuditLog, ClusterLock
from .auth import verify_password, hash_password, create_token, decode_token
from .schemas import LoginRequest, PasswordChangeRequest, RouteRequest, DomainRequest, ConfigSyncRequest

app = FastAPI(title="Mail Relay HA API")
security = HTTPBearer()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

GENERATED = Path("/generated")
GENERATED.mkdir(parents=True, exist_ok=True)


def sync_from_master_loop():
    mode = os.getenv("CLUSTER_MODE", "master").lower()
    if mode != "slave":
        return
    master_url = os.getenv("MASTER_API_URL", "")
    token = os.getenv("MASTER_API_TOKEN", "")
    interval = int(os.getenv("SYNC_INTERVAL_SECONDS", "5"))
    if not master_url or not token:
        return
    while True:
        try:
            db = next(get_db())
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
                    Path("/generated/.reload").touch()
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


def init_admin(db: Session):
    if db.query(User).count() == 0:
        user = os.getenv("ADMIN_DEFAULT_USER", "admin")
        pwd = os.getenv("ADMIN_DEFAULT_PASSWORD", "Admin123")
        force = os.getenv("ADMIN_FORCE_PASSWORD_CHANGE", "true").lower() == "true"
        db.add(User(username=user, password_hash=hash_password(pwd), role="Admin", must_change_password=force))
        db.commit()


@app.on_event("startup")
def startup():
    db = next(get_db())
    init_admin(db)
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
    routes = [
        {
            "sender_domain": r.sender_domain,
            "target_host": r.target_host,
            "target_port": r.target_port,
            "tls_mode": r.tls_mode,
            "tls_verify": r.tls_verify,
            "auth_username": r.auth_username,
            "auth_password": r.auth_password,
        }
        for r in db.query(RelayRoute).all()
    ]
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
    sender_map = "\n".join([f"@{r.sender_domain} [{r.target_host}]:{r.target_port}" for r in routes]) + "\n"
    transport_map = "\n".join([f"{r.sender_domain} smtp:[{r.target_host}]:{r.target_port}" for r in routes]) + "\n"
    sasl_map = "\n".join([f"[{r.target_host}]:{r.target_port} {r.auth_username}:{r.auth_password}" for r in routes if r.auth_username]) + "\n"

    (GENERATED / "sender_relay").write_text(sender_map)
    (GENERATED / "transport").write_text(transport_map)
    (GENERATED / "sasl_passwd").write_text(sasl_map)


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
    routes = db.query(RelayRoute).all()
    domains = db.query(DomainPolicy).all()
    return {
        "mode": os.getenv("CLUSTER_MODE", "master"),
        "routes": [r.__dict__ for r in routes],
        "domains": [d.__dict__ for d in domains],
        "latest_version": db.query(func.max(ConfigVersion.version)).scalar() or 0,
    }


@app.post("/api/routes")
def add_route(req: RouteRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(user, ["Admin", "Operator"])
    db.add(RelayRoute(**req.model_dump()))
    db.commit()
    v = snapshot_config(db, user.username)
    return {"status": "saved", "version": v}


@app.post("/api/domains")
def add_domain(req: DomainRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(user, ["Admin", "Operator"])
    db.add(DomainPolicy(domain=req.domain, enabled=True))
    db.commit()
    v = snapshot_config(db, user.username)
    return {"status": "saved", "version": v}


@app.post("/api/config/test")
def config_test(user: User = Depends(current_user), db: Session = Depends(get_db)):
    render_postfix(db)
    checks = {
        "domains": (GENERATED / "allowed_sender_domains").exists(),
        "sender_relay": (GENERATED / "sender_relay").exists(),
        "transport": (GENERATED / "transport").exists(),
    }
    return {"ok": all(checks.values()), "checks": checks}


@app.post("/api/config/apply")
def config_apply(user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(user, ["Admin", "Operator"])
    render_postfix(db)
    result = subprocess.run(["/bin/sh", "-c", "touch /generated/.reload"], capture_output=True, text=True)
    latest = db.query(ConfigVersion).order_by(desc(ConfigVersion.version)).first()
    if latest:
        latest.applied = True
    db.add(AuditLog(actor=user.username, action="config_applied", payload=result.stdout + result.stderr))
    db.commit()
    return {"status": "applied"}


@app.get("/api/dashboard")
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    now = datetime.utcnow()
    p24 = db.query(MailLog).filter(MailLog.created_at >= now - timedelta(hours=24)).count()
    p1 = db.query(MailLog).filter(MailLog.created_at >= now - timedelta(hours=1)).count()
    r16 = db.query(RejectionLog).filter(RejectionLog.created_at >= now - timedelta(hours=16)).count()
    rejected = db.query(RejectionLog).order_by(desc(RejectionLog.created_at)).limit(100).all()
    return {
        "processed_24h": p24,
        "processed_1h": p1,
        "rejected_16h": r16,
        "queue_size": 0,
        "active_node": os.getenv("NODE_ID"),
        "rejected_last_100": [
            {"sender": r.sender, "recipient": r.recipient, "reason": r.reason, "created_at": r.created_at.isoformat()} for r in rejected
        ],
    }


@app.get("/api/logs")
def logs(user: User = Depends(current_user), db: Session = Depends(get_db), status: str | None = None):
    q = db.query(MailLog)
    if status:
        q = q.filter(MailLog.status == status)
    rows = q.order_by(desc(MailLog.created_at)).limit(500).all()
    return [{
        "sender": r.sender, "recipient": r.recipient, "ip": r.client_ip, "status": r.status,
        "target": r.target, "tls": r.tls_used, "timestamp": r.created_at.isoformat()
    } for r in rows]


@app.get("/api/config/export")
def export_config(x_api_token: str = Header(default=""), db: Session = Depends(get_db)):
    expected = os.getenv("API_TOKEN", "")
    if not expected or x_api_token != expected:
        raise HTTPException(status_code=403, detail="forbidden")
    latest = db.query(ConfigVersion).order_by(desc(ConfigVersion.version)).first()
    if not latest:
        return {"version": 0, "data": {"domains": [], "routes": []}}
    return {"version": latest.version, "data": json.loads(latest.data)}


@app.post("/api/cluster/mode")
def cluster_mode(req: ConfigSyncRequest, user: User = Depends(current_user)):
    require_role(user, ["Admin"])
    return {"status": "stored_in_env", "mode": req.mode, "master_api_url": req.master_api_url}


@app.post("/api/sync-lock/acquire")
def acquire_lock(payload: dict, x_api_token: str = Header(default=""), db: Session = Depends(get_db)):
    if x_api_token != os.getenv("API_TOKEN", ""):
        raise HTTPException(status_code=403, detail="forbidden")
    node_id = payload.get("node_id", "unknown")
    is_vip_owner = payload.get("is_vip_owner", False)
    if not is_vip_owner:
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


@app.post("/api/smtp-event")
def smtp_event(event: dict, db: Session = Depends(get_db)):
    typ = event.get("type", "mail")
    if typ == "reject":
        db.add(RejectionLog(sender=event.get("sender"), recipient=event.get("recipient"), client_ip=event.get("client_ip"), reason=event.get("reason", "rejected")))
    else:
        db.add(MailLog(
            sender=event.get("sender"), recipient=event.get("recipient"), client_ip=event.get("client_ip"),
            helo=event.get("helo"), rdns=event.get("rdns"), target=event.get("target"), status=event.get("status", "processed"),
            smtp_code=event.get("smtp_code"), smtp_text=event.get("smtp_text"), tls_used=bool(event.get("tls_used", False)),
            subject=event.get("subject"),
        ))
    db.commit()
    return {"status": "ok"}
