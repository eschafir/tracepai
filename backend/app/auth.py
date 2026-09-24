import secrets
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pwdlib import PasswordHash
from sqlmodel import Session, SQLModel, select

from app.db import get_session
from app.models import Session as UserSession
from app.models import User

password_hash = PasswordHash.recommended()
router = APIRouter(prefix="/auth", tags=["auth"])

DbSession = Annotated[Session, Depends(get_session)]


def current_user(db: DbSession, session_token: Annotated[str | None, Cookie()] = None) -> User:
    user_session = db.get(UserSession, session_token) if session_token else None
    if not user_session:
        raise HTTPException(401, "Not authenticated")
    return db.get(User, user_session.user_id)


CurrentUser = Annotated[User, Depends(current_user)]


class Credentials(SQLModel):
    username: str
    password: str


@router.post("/login")
def login(creds: Credentials, response: Response, db: DbSession):
    user = db.exec(select(User).where(User.username == creds.username)).first()
    if not user or not password_hash.verify(creds.password, user.password_hash):
        raise HTTPException(401, "Invalid username or password")
    token = secrets.token_urlsafe(32)
    db.add(UserSession(token=token, user_id=user.id))
    db.commit()
    response.set_cookie("session_token", token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 30)
    return {"username": user.username}


@router.post("/logout")
def logout(response: Response, db: DbSession, session_token: Annotated[str | None, Cookie()] = None):
    if session_token and (user_session := db.get(UserSession, session_token)):
        db.delete(user_session)
        db.commit()
    response.delete_cookie("session_token")
    return {"ok": True}


@router.get("/me")
def me(user: CurrentUser):
    return {"username": user.username}
