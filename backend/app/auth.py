import datetime as dt
import os
import secrets
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from pydantic import StringConstraints
from sqlmodel import Session, SQLModel, delete, select

from app.db import get_session
from app.models import Session as UserSession
from app.models import User
from app.seed import start_account

password_hash = PasswordHash.recommended()
router = APIRouter(prefix="/auth", tags=["auth"])
bearer_security = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_session)]

SESSION_DAYS = 30
SECURE_COOKIES = os.environ.get("TRACEPAI_SECURE_COOKIES") == "1"  # set when served over HTTPS
LOCKOUT = dt.timedelta(minutes=15)
MAX_FAILED_PER_CLIENT = 5  # per client, so no one can lock the owner out with a few wrong guesses
MAX_FAILED_PER_USERNAME = 50  # from all clients together, since a client behind a proxy may fake its address
ALL_CLIENTS = "*"
# (username, client IP or ALL_CLIENTS) -> failures, time of the first one
_failed_logins: dict[tuple[str, str], tuple[int, dt.datetime]] = {}


def request_token(
    session_token: Annotated[str | None, Cookie()] = None,
    bearer: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_security)] = None,
) -> str | None:
    return bearer.credentials if bearer else session_token


Token = Annotated[str | None, Depends(request_token)]


def current_user(db: DbSession, token: Token) -> User:
    user_session = db.get(UserSession, token) if token else None
    if not user_session:
        raise HTTPException(401, "Not authenticated")
    if user_session.created_at.replace(tzinfo=dt.UTC) < dt.datetime.now(dt.UTC) - dt.timedelta(days=SESSION_DAYS):
        db.delete(user_session)
        db.commit()
        raise HTTPException(401, "Not authenticated")
    user = db.get(User, user_session.user_id)
    if not user:
        raise HTTPException(401, "Not authenticated")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def check_owned(db: Session, model: type[SQLModel], user_id: int, *ids: int | None):
    """Every id given must be one of the user's own rows of that model."""
    for row_id in ids:
        if row_id is None:
            continue
        row = db.get(model, row_id)
        if not row or row.user_id != user_id:
            raise HTTPException(422, f"{model.__name__} not found")


class Credentials(SQLModel):
    username: str
    password: str


class SignUp(SQLModel):
    username: Annotated[str, StringConstraints(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")]
    password: Annotated[str, StringConstraints(min_length=8)]


def start_session(db: Session, response: Response, user: User) -> str:
    token = secrets.token_urlsafe(32)
    db.add(UserSession(token=token, user_id=user.id))
    db.commit()
    response.set_cookie(
        "session_token", token, httponly=True, samesite="lax", secure=SECURE_COOKIES, max_age=60 * 60 * 24 * SESSION_DAYS
    )
    return token


@router.post("/login")
def login(creds: Credentials, request: Request, response: Response, db: DbSession):
    now = dt.datetime.now(dt.UTC)
    client = (creds.username, request.client.host if request.client else "")
    limits = {client: MAX_FAILED_PER_CLIENT, (creds.username, ALL_CLIENTS): MAX_FAILED_PER_USERNAME}
    for old in [k for k, (_, first) in _failed_logins.items() if now - first > LOCKOUT]:
        del _failed_logins[old]
    if any(_failed_logins.get(key, (0, now))[0] >= limit for key, limit in limits.items()):
        raise HTTPException(429, "Too many failed attempts. Try again in 15 minutes.")
    user = db.exec(select(User).where(User.username == creds.username)).first()
    if not user or not password_hash.verify(creds.password, user.password_hash):
        for key in limits:
            failures, since = _failed_logins.get(key, (0, now))
            _failed_logins[key] = (failures + 1, since)
        raise HTTPException(401, "Invalid username or password")
    _failed_logins.pop(client, None)
    token = start_session(db, response, user)
    return {"username": user.username, "token": token}


@router.post("/signup")
def signup(data: SignUp, response: Response, db: DbSession):
    if db.exec(select(User).where(User.username == data.username)).first():
        raise HTTPException(409, "That username is taken. Try another one.")
    user = User(username=data.username, password_hash=password_hash.hash(data.password))
    db.add(user)
    db.flush()
    start_account(db, user)
    token = start_session(db, response, user)
    return {"username": user.username, "token": token}


@router.post("/logout")
def logout(response: Response, db: DbSession, token: Token):
    if token and (user_session := db.get(UserSession, token)):
        db.delete(user_session)
        db.commit()
    response.delete_cookie("session_token")
    return {"ok": True}


class ProfileUpdate(SQLModel):
    display_name: str | None = None
    password: str | None = None
    current_password: str | None = None


@router.get("/me")
def me(user: CurrentUser):
    return {
        "id": user.id,
        "username": user.username,
        "display_name": getattr(user, "display_name", "") or user.username,
    }


@router.put("/profile")
def update_profile(data: ProfileUpdate, db: DbSession, user: CurrentUser, token: Token):
    if data.password:
        if not data.current_password or not password_hash.verify(data.current_password, user.password_hash):
            raise HTTPException(400, "Current password is incorrect.")
        if len(data.password) < 8:
            raise HTTPException(400, "New password must be at least 8 characters.")
        user.password_hash = password_hash.hash(data.password)
        db.exec(delete(UserSession).where(UserSession.user_id == user.id, UserSession.token != token))  # sign out other devices
    if data.display_name is not None:
        user.display_name = data.display_name.strip()
    db.add(user)
    db.commit()
    return {
        "id": user.id,
        "username": user.username,
        "display_name": getattr(user, "display_name", "") or user.username,
    }


@router.get("/users/{username}")
def find_user(username: str, db: DbSession, user: CurrentUser):
    """Looks someone up by username, to share an expense with them."""
    found = db.exec(select(User).where(User.username == username.strip())).first()
    if not found:
        raise HTTPException(404, f"No one is signed up as {username.strip()}.")
    return {"id": found.id, "username": found.username}
