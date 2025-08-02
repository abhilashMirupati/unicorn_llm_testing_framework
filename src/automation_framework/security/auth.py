"""
Authentication & RBAC Helpers
----------------------------

This module encapsulates user authentication, password hashing,
JWT generation and role‑based access control for the dashboard.  It
uses the `passlib` library for secure password hashing (bcrypt) and
`python-jose` for JWT creation and verification.  Users and roles
are loaded from the configuration.

FastAPI dependencies are provided to protect endpoints.  For
example:

    from .security.auth import get_current_user, admin_required

    @app.get("/users", dependencies=[Depends(admin_required)])
    async def list_users():
        ...

See config/config.yaml for example user definitions.  Passwords must
be stored as bcrypt hashes.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
# Conditional import of jose and passlib.  These libraries may not be
# available in constrained environments.  Fallback implementations
# perform minimal encoding/decoding and plaintext password comparison.
try:
    from jose import JWTError, jwt  # type: ignore
    _jose_available = True
except Exception:
    _jose_available = False
    class JWTError(Exception):
        pass
    class jwt:  # type: ignore
        @staticmethod
        def encode(data: dict, secret: str, algorithm: str = "HS256") -> str:
            import base64
            import json
            # Serialize using default=str to handle datetime objects
            payload = json.dumps(data, default=str).encode()
            return base64.urlsafe_b64encode(payload).decode()
        @staticmethod
        def decode(token: str, secret: str, algorithms: list[str]) -> dict:
            import base64
            import json
            try:
                payload = base64.urlsafe_b64decode(token.encode()).decode()
                return json.loads(payload)
            except Exception:
                raise JWTError("Invalid token")

try:
    from passlib.context import CryptContext  # type: ignore
    _passlib_available = True
except Exception:
    _passlib_available = False
    class CryptContext:  # type: ignore
        def __init__(self, *args, **kwargs) -> None:
            pass
        def verify(self, plain: str, hashed: str) -> bool:
            # Fallback: compare plain text if hash looks like plain text
            return plain == hashed


from ..config import Config
from starlette.requests import Request
from ..utils.logger import get_logger


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")


class AuthManager:
    """Manage users, password verification and token creation."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.logger = get_logger(self.__class__.__name__)
        self.secret_key = config.get("security.secret_key") or "changeme"
        self.algorithm = config.get("security.algorithm", "HS256")
        self.expire_minutes = int(config.get("security.access_token_expire_minutes", 60))
        self.users = self._load_users()

    def _load_users(self) -> Dict[str, Dict[str, Any]]:
        users_list = self.config.get("security.users", []) or []
        users: Dict[str, Dict[str, Any]] = {}
        for entry in users_list:
            try:
                username = entry["username"]
                users[username] = {
                    "username": username,
                    "password_hash": entry.get("password_hash", ""),
                    "role": entry.get("role", "viewer"),
                }
            except Exception as exc:
                self.logger.error("Invalid user entry in config: %s", exc)
        return users

    def verify_password(self, plain_password: str, password_hash: str) -> bool:
        # If passlib is available use it; otherwise fall back to naive comparison
        if _passlib_available:
            try:
                return pwd_context.verify(plain_password, password_hash)
            except Exception:
                # Unexpected passlib error
                return False
        else:
            # Without passlib we cannot verify bcrypt.  Log and compare directly.
            self.logger.warning("Passlib unavailable; falling back to plain password comparison")
            return plain_password == password_hash

    def authenticate_user(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        user = self.users.get(username)
        if not user:
            return None
        if not self.verify_password(password, user["password_hash"]):
            return None
        return user

    def create_access_token(self, data: Dict[str, Any], expires_delta: Optional[_dt.timedelta] = None) -> str:
        to_encode = data.copy()
        expire = _dt.datetime.utcnow() + (expires_delta or _dt.timedelta(minutes=self.expire_minutes))
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    async def login_for_access_token(self, form_data: OAuth2PasswordRequestForm = Depends()) -> Dict[str, Any]:
        user = self.authenticate_user(form_data.username, form_data.password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        access_token = self.create_access_token({"sub": user["username"]})
        return {"access_token": access_token, "token_type": "bearer"}

    async def get_current_user(self, token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            username: str = payload.get("sub")  # type: ignore
            if username is None:
                raise credentials_exception
        except JWTError:
            raise credentials_exception
        user = self.users.get(username)
        if user is None:
            raise credentials_exception
        return user

    async def require_admin(self, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        if user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin privileges required")
        return user

# Provide default instances for dependency injection
_global_auth_manager: Optional[AuthManager] = None


def get_auth_manager() -> AuthManager:
    global _global_auth_manager
    if _global_auth_manager is None:
        config = Config()
        _global_auth_manager = AuthManager(config)
    return _global_auth_manager


async def get_current_user(request: Request, token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    """Return the currently authenticated user.

    Tokens are accepted via the standard Authorization header (Bearer)
    or via an `access_token` cookie.  If no valid token is provided a
    401 error is raised.
    """
    # If no token provided via header, try cookie
    if not token:
        token = request.cookies.get("access_token")  # type: ignore[attr-defined]
    auth = get_auth_manager()
    return await auth.get_current_user(token)


async def require_admin(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    auth = get_auth_manager()
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user
