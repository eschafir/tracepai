"""Exchange rates to USD, fetched once a day per currency and stored in the FxRate table."""

import bisect
import datetime as dt
import json
import logging
import threading
import urllib.request

from sqlalchemy.dialects.sqlite import insert
from sqlmodel import Session, select

from app.models import FxRate, Wallet

log = logging.getLogger(__name__)

HISTORY_START = "2011-01-01"
# Currencies with daily history from the European Central Bank (api.frankfurter.dev).
ECB = {"AUD", "BRL", "CAD", "CHF", "CNY", "CZK", "DKK", "EUR", "GBP", "HKD", "HUF", "IDR", "ILS", "INR", "ISK", "JPY",
       "KRW", "MXN", "MYR", "NOK", "NZD", "PHP", "PLN", "RON", "SEK", "SGD", "THB", "TRY", "ZAR"}


def get_json(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": "TracepAI"})
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


def fetch(currency: str) -> list[tuple[dt.date, float]]:
    """(date, units per USD) pairs from the source that covers the currency."""
    if currency == "ARS":  # official BNA rate, full daily history
        rows = get_json("https://api.argentinadatos.com/v1/cotizaciones/dolares/oficial")
        return [(dt.date.fromisoformat(r["fecha"]), float(r["venta"])) for r in rows if r.get("venta")]
    if currency in ECB:
        data = get_json(f"https://api.frankfurter.dev/v1/{HISTORY_START}..?base=USD&symbols={currency}")
        return [(dt.date.fromisoformat(day), rates[currency]) for day, rates in data["rates"].items()]
    data = get_json("https://open.er-api.com/v6/latest/USD")  # today's rate only; history builds up day by day
    rate = data["rates"].get(currency)
    return [(dt.date.today(), float(rate))] if rate else []


def currencies() -> list[str]:
    """Every code a wallet can use: all of open.er-api.com's, plus the ones with full history."""
    try:
        codes = set(get_json("https://open.er-api.com/v6/latest/USD")["rates"])
    except Exception as err:
        log.warning("The currency list could not be fetched: %s", err)
        codes = set()
    return sorted(codes | ECB | {"USD", "ARS"})


_checked: dict[str, dt.date] = {}
_lock = threading.Lock()


def refresh(db: Session, currency: str, strict: bool = False):
    """Fetch new rates at most once a day. A failed fetch keeps the stored rates, unless strict and none are stored."""
    today = dt.date.today()
    if currency == "USD" or _checked.get(currency) == today:
        return
    with _lock:
        if _checked.get(currency) == today:
            return
        try:
            rows = fetch(currency)
        except Exception as err:
            log.warning("Exchange rates for %s could not be fetched: %s", currency, err)
            rows = []
        if rows:
            stmt = insert(FxRate).values([{"currency": currency, "date": d, "per_usd": r} for d, r in rows])
            db.exec(stmt.on_conflict_do_update(index_elements=["currency", "date"], set_={"per_usd": stmt.excluded.per_usd}))
            db.commit()
            _checked[currency] = today
    if strict and not db.exec(select(FxRate).where(FxRate.currency == currency)).first():
        raise ValueError(f"No exchange rate was found for {currency}. Check the code and the internet connection.")


class Rates:
    """Converts amounts to USD using the nearest stored rate on or before a date."""

    def __init__(self, db: Session, currencies: set[str]):
        self.db = db
        self.table: dict[str, tuple[list[dt.date], list[float]]] = {}
        for currency in currencies - {"USD"}:
            self.load(currency)

    def load(self, currency: str):
        refresh(self.db, currency)
        rows = self.db.exec(select(FxRate).where(FxRate.currency == currency).order_by(FxRate.date)).all()
        self.table[currency] = ([r.date for r in rows], [r.per_usd for r in rows])

    def per_usd(self, currency: str, date: dt.date | None = None) -> float:
        if currency == "USD":
            return 1.0
        if currency not in self.table:  # e.g. another member's wallet in a shared expense
            self.load(currency)
        dates, values = self.table[currency]
        i = bisect.bisect_right(dates, date or dt.date.today()) - 1
        return values[max(i, 0)]

    def usd(self, amount: float, currency: str, date: dt.date | None = None) -> float:
        return amount / self.per_usd(currency, date)


def user_rates(db: Session, user_id: int) -> tuple[Rates, dict[int, str]]:
    """The rates for a user's wallet currencies, and each wallet's currency."""
    currency_of = {w.id: w.currency for w in db.exec(select(Wallet).where(Wallet.user_id == user_id))}
    return Rates(db, set(currency_of.values())), currency_of
