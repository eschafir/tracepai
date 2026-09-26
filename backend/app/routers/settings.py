from typing import Literal

from fastapi import APIRouter
from sqlmodel import SQLModel

from app.auth import CurrentUser, DbSession

router = APIRouter(prefix="/settings", tags=["settings"])


class Settings(SQLModel):
    budget_style: Literal["limits", "zero_based", "50_30_20"]


@router.get("")
def get_settings(user: CurrentUser) -> Settings:
    return Settings(budget_style=user.budget_style)


@router.put("")
def update_settings(data: Settings, db: DbSession, user: CurrentUser) -> Settings:
    user.budget_style = data.budget_style
    db.add(user)
    db.commit()
    return data
