import secrets
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from pydantic import StringConstraints
from sqlmodel import Session, SQLModel, select

from app.db import get_session
from app.models import Session as UserSession
from app.models import User
from app.seed import start_account

password_hash = PasswordHash.recommended()
router = APIRouter(prefix="/auth", tags=["auth"])
bearer_security = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_session)]


def current_user(
    db: DbSession,
    session_token: Annotated[str | None, Cookie()] = None,
    bearer: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_security)] = None,
) -> User:
    token = bearer.credentials if bearer else session_token
    user_session = db.get(UserSession, token) if token else None
    if not user_session:
        raise HTTPException(401, "Not authenticated")
    user = db.get(User, user_session.user_id)
    if not user:
        raise HTTPException(401, "Not authenticated")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


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
    response.set_cookie("session_token", token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 30)
    return token


@router.post("/login")
def login(creds: Credentials, response: Response, db: DbSession):
    user = db.exec(select(User).where(User.username == creds.username)).first()
    if not user or not password_hash.verify(creds.password, user.password_hash):
        raise HTTPException(401, "Invalid username or password")
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
def logout(
    response: Response,
    db: DbSession,
    session_token: Annotated[str | None, Cookie()] = None,
    bearer: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_security)] = None,
):
    token = bearer.credentials if bearer else session_token
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
def update_profile(data: ProfileUpdate, db: DbSession, user: CurrentUser):
    if data.password:
        if not data.current_password or not password_hash.verify(data.current_password, user.password_hash):
            raise HTTPException(400, "Current password is incorrect.")
        if len(data.password) < 8:
            raise HTTPException(400, "New password must be at least 8 characters.")
        user.password_hash = password_hash.hash(data.password)
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
