import datetime as dt

from fastapi import APIRouter, HTTPException

from app import fx
from app.auth import CurrentUser, DbSession

router = APIRouter(prefix="/fx", tags=["fx"])


@router.get("/currencies")
def currencies(user: CurrentUser) -> list[str]:
    return fx.currencies()


@router.get("/convert")
def convert(amount: float, db: DbSession, user: CurrentUser, to: str, date: dt.date | None = None, source: str = "USD"):
    """An estimate for pre-filling a received amount."""
    try:
        rates = fx.Rates(db, {source, to})
        return {"amount": round(rates.usd(amount, source, date) * rates.per_usd(to, date), 2)}
    except (KeyError, IndexError):
        raise HTTPException(404, "No exchange rate is stored for this pair yet.")
