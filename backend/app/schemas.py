from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str


class RouteRequest(BaseModel):
    sender_domain: str
    target_host: str
    target_port: int = 25
    tls_mode: str = "opportunistic"
    tls_verify: bool = False
    auth_username: str | None = None
    auth_password: str | None = None


class DomainRequest(BaseModel):
    domain: str


class ConfigSyncRequest(BaseModel):
    mode: str
    master_api_url: str | None = None
    master_api_token: str | None = None
