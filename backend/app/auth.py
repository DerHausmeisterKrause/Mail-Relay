import os
from datetime import datetime, timedelta, timezone
from jose import jwt
from passlib.context import CryptContext

JWT_SECRET = os.getenv("JWT_SECRET", "changeme")
ALGO = "HS256"
pwd_ctx = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)


def hash_password(password: str) -> str:
    return pwd_ctx.hash(password)


def create_token(sub: str, role: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=12)
    return jwt.encode({"sub": sub, "role": role, "exp": exp}, JWT_SECRET, algorithm=ALGO)


def decode_token(token: str):
    return jwt.decode(token, JWT_SECRET, algorithms=[ALGO])
