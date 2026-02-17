from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Boolean, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="Admin")
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ConfigVersion(Base):
    __tablename__ = "config_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    data: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    applied: Mapped[bool] = mapped_column(Boolean, default=False)


class DomainPolicy(Base):
    __tablename__ = "domain_policies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    domain: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class RelayRoute(Base):
    __tablename__ = "relay_routes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sender_domain: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    target_host: Mapped[str] = mapped_column(String(255), nullable=False)
    target_port: Mapped[int] = mapped_column(Integer, default=25)
    tls_mode: Mapped[str] = mapped_column(String(32), default="opportunistic")
    tls_verify: Mapped[bool] = mapped_column(Boolean, default=False)
    auth_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    auth_password: Mapped[str | None] = mapped_column(String(255), nullable=True)


class MailLog(Base):
    __tablename__ = "mail_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sender: Mapped[str | None] = mapped_column(String(255))
    recipient: Mapped[str | None] = mapped_column(String(255))
    client_ip: Mapped[str | None] = mapped_column(String(64))
    helo: Mapped[str | None] = mapped_column(String(255))
    rdns: Mapped[str | None] = mapped_column(String(255))
    target: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="unknown")
    smtp_code: Mapped[str | None] = mapped_column(String(32))
    smtp_text: Mapped[str | None] = mapped_column(Text)
    tls_used: Mapped[bool] = mapped_column(Boolean, default=False)
    subject: Mapped[str | None] = mapped_column(String(998))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RejectionLog(Base):
    __tablename__ = "rejection_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sender: Mapped[str | None] = mapped_column(String(255))
    recipient: Mapped[str | None] = mapped_column(String(255))
    client_ip: Mapped[str | None] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(255))
    payload: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ClusterSetting(Base):
    __tablename__ = "cluster_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    node_id: Mapped[str] = mapped_column(String(64), nullable=False)
    node_ip: Mapped[str] = mapped_column(String(64), nullable=False)
    peer_node_ip: Mapped[str] = mapped_column(String(64), nullable=False)
    vip_address: Mapped[str] = mapped_column(String(64), nullable=False)
    vrrp_priority: Mapped[int] = mapped_column(Integer, default=100)
    cluster_mode: Mapped[str] = mapped_column(String(32), default="standalone")
    master_api_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    master_api_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tls_crt: Mapped[str | None] = mapped_column(Text, nullable=True)
    tls_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    ssh_private_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    ssh_known_hosts: Mapped[str | None] = mapped_column(Text, nullable=True)
    peer_ssh_user: Mapped[str] = mapped_column(String(64), default="root")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ClusterLock(Base):
    __tablename__ = "cluster_locks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lock_name: Mapped[str] = mapped_column(String(64), nullable=False)
    node_id: Mapped[str] = mapped_column(String(64), nullable=False)
    heartbeat: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("lock_name", name="uq_lock_name"),)
