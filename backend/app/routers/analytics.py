import calendar
import datetime as dt
from collections import defaultdict

from fastapi import APIRouter
from sqlmodel import select

from app.auth import CurrentUser, DbSession
from app.models import Budget, Category, Kind, Transaction, Wallet
from app.routers.transactions import query_transactions
from app.wallets import wallet_deltas

router = APIRouter(prefix="/analytics", tags=["analytics"])


def category_amounts(txn: Transaction) -> list[tuple[int | None, float]]:
    return [(s.category_id, s.amount) for s in txn.splits] or [(txn.category_id, txn.amount)]


def expense_by_category(txns: list[Transaction]) -> dict[int | None, float]:
    totals = defaultdict(float)
    for txn in txns:
        if txn.kind == Kind.expense:
            for category_id, amount in category_amounts(txn):
                totals[category_id] += amount
    return totals


def month_bounds(month: str | None) -> tuple[dt.date, dt.date]:
    start = dt.date.fromisoformat(f"{month}-01") if month else dt.date.today().replace(day=1)
    return start, start.replace(day=calendar.monthrange(start.year, start.month)[1])


@router.get("/categories")
def categories(db: DbSession, user: CurrentUser, start: dt.date, end: dt.date, wallet: int | None = None):
    cats = {c.id: c for c in db.exec(select(Category).where(Category.user_id == user.id))}
    totals = expense_by_category(query_transactions(db, user, start, end, wallet=wallet))
    rows = [
        {
            "category_id": cid,
            "name": cats[cid].name if cid in cats else "Uncategorized",
            "color_slot": cats[cid].color_slot if cid in cats else None,
            "total": round(total, 2),
        }
        for cid, total in totals.items()
    ]
    return sorted(rows, key=lambda r: -r["total"])


@router.get("/cashflow")
def cashflow(db: DbSession, user: CurrentUser, start: dt.date, end: dt.date, bucket: str = "day", wallet: int | None = None):
    key = (lambda d: d.isoformat()) if bucket == "day" else (lambda d: d.strftime("%Y-%m"))
    periods = {}
    d = start
    while d <= end:
        periods.setdefault(key(d), {"period": key(d), "income": 0.0, "expense": 0.0})
        d += dt.timedelta(days=1)
    for txn in query_transactions(db, user, start, end, wallet=wallet):
        if txn.kind != Kind.transfer:
            periods[key(txn.date)][txn.kind.value] += txn.amount
    return [
        {**p, "income": round(p["income"], 2), "expense": round(p["expense"], 2), "net": round(p["income"] - p["expense"], 2)}
        for p in periods.values()
    ]


@router.get("/budgets")
def budgets(db: DbSession, user: CurrentUser, month: str | None = None):
    start, end = month_bounds(month)
    today = dt.date.today()
    days_remaining = (end - today).days if start <= today <= end else (0 if today > end else (end - start).days + 1)
    totals = expense_by_category(query_transactions(db, user, start, end))
    rows = []
    for budget in db.exec(select(Budget).where(Budget.user_id == user.id).order_by(Budget.id)):
        category = db.get(Category, budget.category_id)
        spent = round(totals.get(budget.category_id, 0.0), 2)
        rows.append(
            {
                "budget_id": budget.id,
                "category_id": budget.category_id,
                "name": category.name if category else "Uncategorized",
                "color_slot": category.color_slot if category else None,
                "limit": budget.monthly_limit,
                "spent": spent,
                "percent": round(100 * spent / budget.monthly_limit, 1),
                "days_remaining": days_remaining,
            }
        )
    return rows


@router.get("/merchants")
def merchants(db: DbSession, user: CurrentUser, start: dt.date, end: dt.date, limit: int = 8, wallet: int | None = None):
    expenses = [t for t in query_transactions(db, user, start, end, wallet=wallet) if t.kind == Kind.expense]
    largest = sorted(expenses, key=lambda t: -t.amount)[:limit]
    by_merchant = defaultdict(lambda: {"count": 0, "total": 0.0})
    for txn in expenses:
        by_merchant[txn.merchant]["count"] += 1
        by_merchant[txn.merchant]["total"] += txn.amount
    frequent = sorted(by_merchant.items(), key=lambda kv: (-kv[1]["count"], -kv[1]["total"]))[:limit]
    return {
        "largest": [{"id": t.id, "date": t.date, "merchant": t.merchant, "amount": t.amount} for t in largest],
        "frequent": [{"merchant": m, "count": v["count"], "total": round(v["total"], 2)} for m, v in frequent],
    }


@router.get("/comparison")
def comparison(db: DbSession, user: CurrentUser, month: str | None = None, wallet: int | None = None):
    start, end = month_bounds(month)
    prev_start, prev_end = month_bounds((start - dt.timedelta(days=1)).strftime("%Y-%m"))
    today = dt.date.today()

    def cumulative(first: dt.date, last: dt.date) -> list[float]:
        daily = [0.0] * last.day
        for txn in query_transactions(db, user, first, last, wallet=wallet):
            if txn.kind == Kind.expense:
                daily[txn.date.day - 1] += txn.amount
        running, out = 0.0, []
        for amount in daily:
            running += amount
            out.append(round(running, 2))
        return out

    current, previous = cumulative(start, end), cumulative(prev_start, prev_end)
    return [
        {
            "day": day,
            "current": current[day - 1] if day <= len(current) and start.replace(day=day) <= today else None,
            "previous": previous[day - 1] if day <= len(previous) else None,
        }
        for day in range(1, max(len(current), len(previous)) + 1)
    ]


@router.get("/balance")
def balance(db: DbSession, user: CurrentUser, wallet: int | None = None):
    wallets = db.exec(select(Wallet).where(Wallet.user_id == user.id)).all()
    running = sum(w.opening_balance for w in wallets if wallet in (None, w.id))
    daily = defaultdict(float)
    for txn in query_transactions(db, user, wallet=wallet):
        daily[txn.date] += sum(delta for wallet_id, delta in wallet_deltas(txn) if wallet in (None, wallet_id))
    out = []
    for date in sorted(daily):
        running += daily[date]
        out.append({"date": date, "balance": round(running, 2)})
    return out
