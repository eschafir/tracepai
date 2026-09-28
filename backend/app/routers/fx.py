import datetime as dt

from typing import Annotated

from fastapi import APIRouter, Query

from app import fx
from app.auth import CurrentUser, DbSession

router = APIRouter(prefix="/fx", tags=["fx"])

Code = Annotated[str, Query(pattern="^[A-Z]{3}$")]


@router.get("/currencies")
def currencies(user: CurrentUser) -> list[str]:
    return fx.currencies()


@router.get("/convert")
def convert(amount: float, db: DbSession, user: CurrentUser, to: Code, date: dt.date | None = None, source: Code = "USD"):
    """An estimate for pre-filling a received amount."""
    rates = fx.Rates(db, {source, to})
    return {"amount": round(rates.usd(amount, source, date) * rates.per_usd(to, date), 2)}
