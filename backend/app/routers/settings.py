from typing import Literal

from fastapi import APIRouter
from sqlmodel import SQLModel

from app.auth import CurrentUser, DbSession

router = APIRouter(prefix="/settings", tags=["settings"])

LAYOUTS = ("overview_layout", "year_layout")


class Settings(SQLModel):
    budget_style: Literal["limits", "zero_based", "50_30_20"]
    overview_layout: list[str]
    year_layout: list[str]


class SettingsIn(SQLModel):
    budget_style: Literal["limits", "zero_based", "50_30_20"] | None = None
    overview_layout: list[str] | None = None
    year_layout: list[str] | None = None


def settings_of(user) -> Settings:
    layouts = {key: [p for p in getattr(user, key).split(",") if p] for key in LAYOUTS}
    return Settings(budget_style=user.budget_style, **layouts)


@router.get("")
def get_settings(user: CurrentUser) -> Settings:
    return settings_of(user)


@router.put("")
def update_settings(data: SettingsIn, db: DbSession, user: CurrentUser) -> Settings:
    for key, value in data.model_dump(exclude_none=True).items():
        setattr(user, key, ",".join(value) if key in LAYOUTS else value)
    db.add(user)
    db.commit()
    return settings_of(user)
