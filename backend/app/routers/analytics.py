import calendar
import datetime as dt
from collections import defaultdict
from collections.abc import Callable
from types import SimpleNamespace

from fastapi import APIRouter
from sqlmodel import col, select

from app import fx
from app.auth import CurrentUser, DbSession
from app.models import Budget, BudgetGroup, Category, CategoryKind, Goal, Kind, RecurringRule, SharedWallet, Transaction, Wallet
from app.recurring import advance
from app.routers.goals import signed
from app.routers.transactions import query_transactions
from app.shared import my_ledgers, shared_with, shares
from app.wallets import wallet_deltas

router = APIRouter(prefix="/analytics", tags=["analytics"])

# Every figure here is in USD. A converter turns a transaction's amount (or part of it) into USD
# using its wallet's currency and the rate on its date.
Usd = Callable[..., float]


def converter(db: DbSession, user: CurrentUser) -> Usd:
    rates, currency_of = fx.user_rates(db, user.id)

    def usd(txn: Transaction, amount: float | None = None) -> float:
        if txn.wallet_id not in currency_of:  # another member's wallet, in a shared expense
            currency_of[txn.wallet_id] = db.get(Wallet, txn.wallet_id).currency
        return rates.usd(txn.amount if amount is None else amount, currency_of[txn.wallet_id], txn.date)

    return usd


SHARED_CATEGORY = -1  # your share of a shared expense in a category you don't have


def spending(db: DbSession, user: CurrentUser, start: dt.date | None = None, end: dt.date | None = None, wallet: int | None = None):
    """Transactions as they count for spending and income: without payments that settle up or pay back a share, and
    with shared expenses cut to your share, including your share of what others paid (all wallets only). A shared
    expense uses the categories of its shared wallet's owner, or of its payer when it isn't in a shared wallet; for
    everyone else it maps to their category with the same name, or "Shared".
    Balances and net worth use query_transactions, since there the whole payment left the payer's wallet."""
    own = [t for t in query_transactions(db, user, start, end, wallet=wallet) if t.settlement_id is None and t.share_payment_id is None]
    others = []
    if not wallet:
        ledger_ids = [ledger.id for ledger in my_ledgers(db, user.id)]
        stmt = select(Transaction).where(col(Transaction.shared_wallet_id).in_(ledger_ids), Transaction.user_id != user.id)
        direct = [t for t in shared_with(db, user.id) if t.user_id != user.id]
        others = [t for t in [*db.exec(stmt), *direct] if (not start or t.date >= start) and (not end or t.date <= end)]

    mine = {c.name.lower(): c.id for c in db.exec(select(Category).where(Category.user_id == user.id))}
    mapping: dict[int, dict[int, int] | None] = {}  # categories' owner -> their category id -> yours; None if they're yours

    def category(txn: Transaction, category_id: int | None) -> int | None:
        owner = db.get(SharedWallet, txn.shared_wallet_id).owner_id if txn.shared_wallet_id else txn.user_id
        if owner not in mapping:
            owned = db.exec(select(Category).where(Category.user_id == owner)).all()
            mapping[owner] = None if owner == user.id else {c.id: mine.get(c.name.lower(), SHARED_CATEGORY) for c in owned}
        table = mapping[owner]
        return category_id if table is None or category_id is None else table.get(category_id, SHARED_CATEGORY)

    out = []
    for txn in own + others:
        if not txn.shared_members:
            out.append(txn)
            continue
        share = shares(txn).get(user.id)
        if not share:
            continue
        out.append(
            SimpleNamespace(
                **txn.model_dump(exclude={"amount", "category_id"}),
                amount=txn.amount * share,
                category_id=category(txn, txn.category_id),
                splits=[SimpleNamespace(category_id=category(txn, s.category_id), amount=s.amount * share) for s in txn.splits],
            )
        )
    return out


def category_amounts(txn: Transaction, usd: Usd) -> list[tuple[int | None, float]]:
    return [(s.category_id, usd(txn, s.amount)) for s in txn.splits] or [(txn.category_id, usd(txn))]


def expense_by_category(txns: list[Transaction], usd: Usd) -> dict[int | None, float]:
    totals = defaultdict(float)
    for txn in txns:
        if txn.kind == Kind.expense:
            for category_id, amount in category_amounts(txn, usd):
                totals[category_id] += amount
    return totals


def month_bounds(month: str | None) -> tuple[dt.date, dt.date]:
    start = dt.date.fromisoformat(f"{month}-01") if month else dt.date.today().replace(day=1)
    return start, start.replace(day=calendar.monthrange(start.year, start.month)[1])


@router.get("/categories")
def categories(db: DbSession, user: CurrentUser, start: dt.date, end: dt.date, wallet: int | None = None):
    cats = {c.id: c for c in db.exec(select(Category).where(Category.user_id == user.id))}
    cats[SHARED_CATEGORY] = Category(id=SHARED_CATEGORY, user_id=user.id, name="Shared", color_slot=8)
    totals = expense_by_category(spending(db, user, start, end, wallet=wallet), converter(db, user))
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
    usd = converter(db, user)
    for txn in spending(db, user, start, end, wallet=wallet):
        if txn.kind != Kind.transfer:
            periods[key(txn.date)][txn.kind.value] += usd(txn)
    return [
        {**p, "income": round(p["income"], 2), "expense": round(p["expense"], 2), "net": round(p["income"] - p["expense"], 2)}
        for p in periods.values()
    ]


def projection(spent: float, fixed: float, upcoming: float, elapsed: int, days: int) -> float:
    """Month-end spending: what's spent, plus recurring charges still due, plus the rest at its current daily pace.
    Recurring charges are kept out of the pace, so rent paid on the 1st doesn't project 30 times over."""
    return spent + upcoming + (spent - fixed) / elapsed * (days - elapsed)


def pace_alert(spent: float, projected: float, limit: float, elapsed: int) -> str | None:
    if spent >= limit:
        return "over"
    if elapsed >= 5 and projected > limit:
        return "pace"
    return None


@router.get("/budgets")
def budgets(db: DbSession, user: CurrentUser, month: str | None = None):
    start, end = month_bounds(month)
    today = dt.date.today()
    in_progress = start <= today <= end
    days_remaining = (end - today).days if in_progress else (0 if today > end else (end - start).days + 1)
    usd = converter(db, user)
    txns = spending(db, user, start, end)
    totals = expense_by_category(txns, usd)
    fixed = expense_by_category([t for t in txns if t.recurring_id], usd)
    upcoming = defaultdict(float)
    if in_progress:
        rates, currency_of = fx.user_rates(db, user.id)
        for rule in db.exec(select(RecurringRule).where(RecurringRule.user_id == user.id, RecurringRule.kind == Kind.expense)):
            date = rule.next_date
            while date <= end:
                if date > today:
                    upcoming[rule.category_id] += rates.usd(rule.amount, currency_of[rule.wallet_id], today)
                date = advance(date, rule.frequency)
    rows = []
    for budget in db.exec(select(Budget).where(Budget.user_id == user.id).order_by(Budget.id)):
        category = db.get(Category, budget.category_id)
        spent = round(totals.get(budget.category_id, 0.0), 2)
        projected = spent
        if in_progress:
            projected = projection(spent, fixed.get(budget.category_id, 0.0), upcoming[budget.category_id], today.day, end.day)
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
                "projected": round(projected, 2),
                "alert": pace_alert(spent, projected, budget.monthly_limit, today.day) if in_progress else None,
            }
        )
    return rows


@router.get("/merchants")
def merchants(db: DbSession, user: CurrentUser, start: dt.date, end: dt.date, limit: int = 8, wallet: int | None = None):
    usd = converter(db, user)
    expenses = [t for t in spending(db, user, start, end, wallet=wallet) if t.kind == Kind.expense]
    largest = sorted(expenses, key=lambda t: -usd(t))[:limit]
    by_merchant = defaultdict(lambda: {"count": 0, "total": 0.0})
    for txn in expenses:
        by_merchant[txn.merchant]["count"] += 1
        by_merchant[txn.merchant]["total"] += usd(txn)
    frequent = sorted(by_merchant.items(), key=lambda kv: (-kv[1]["count"], -kv[1]["total"]))[:limit]
    return {
        "largest": [{"id": t.id, "date": t.date, "merchant": t.merchant, "amount": round(usd(t), 2)} for t in largest],
        "frequent": [{"merchant": m, "count": v["count"], "total": round(v["total"], 2)} for m, v in frequent],
    }


@router.get("/comparison")
def comparison(db: DbSession, user: CurrentUser, month: str | None = None, wallet: int | None = None):
    start, end = month_bounds(month)
    prev_start, prev_end = month_bounds((start - dt.timedelta(days=1)).strftime("%Y-%m"))
    today = dt.date.today()
    usd = converter(db, user)

    def cumulative(first: dt.date, last: dt.date) -> list[float]:
        daily = [0.0] * last.day
        for txn in spending(db, user, first, last, wallet=wallet):
            if txn.kind == Kind.expense:
                daily[txn.date.day - 1] += usd(txn)
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


def balance_history(db: DbSession, user: CurrentUser, dates: list[dt.date], wallet: int | None = None) -> list[dict[int, float]]:
    """Each wallet's USD balance at the end of each date, at that date's rate. Dates must be sorted."""
    rates, currency_of = fx.user_rates(db, user.id)
    wallets = [w for w in db.exec(select(Wallet).where(Wallet.user_id == user.id)) if wallet in (None, w.id)]
    native = {w.id: w.opening_balance for w in wallets}
    txns = sorted(query_transactions(db, user, wallet=wallet), key=lambda t: t.date)
    out, i = [], 0
    for date in dates:
        while i < len(txns) and txns[i].date <= date:
            for wallet_id, delta in wallet_deltas(txns[i]):
                if wallet_id in native:
                    native[wallet_id] += delta
            i += 1
        out.append({wallet_id: rates.usd(amount, currency_of[wallet_id], date) for wallet_id, amount in native.items()})
    return out


@router.get("/balance")
def balance(db: DbSession, user: CurrentUser, wallet: int | None = None):
    dates = sorted({t.date for t in query_transactions(db, user, wallet=wallet)})
    return [
        {"date": date, "balance": round(sum(by_wallet.values()), 2)}
        for date, by_wallet in zip(dates, balance_history(db, user, dates, wallet))
    ]


@router.get("/networth")
def networth(db: DbSession, user: CurrentUser, months: int = 24):
    """Assets (wallets above zero), debts (below zero) and net worth at each month end, and today."""
    today = dt.date.today()
    txns = query_transactions(db, user)
    first = min((t.date for t in txns), default=today)
    dates, month = [today], today.replace(day=1)
    for _ in range(months):
        month_end = month - dt.timedelta(days=1)
        if month_end < first.replace(day=1):
            break
        dates.insert(0, month_end)
        month = month_end.replace(day=1)
    points = []
    for date, by_wallet in zip(dates, balance_history(db, user, dates)):
        assets = sum(v for v in by_wallet.values() if v > 0)
        debts = sum(v for v in by_wallet.values() if v < 0)
        points.append({"date": date, "assets": round(assets, 2), "debts": round(debts, 2), "net": round(assets + debts, 2)})
    return points


@router.get("/summary")
def summary(db: DbSession, user: CurrentUser, month: str | None = None, wallet: int | None = None):
    start, end = month_bounds(month)
    today = dt.date.today()
    in_progress = start <= today <= end
    cutoff = today.day if in_progress else end.day
    prev_start, prev_end = month_bounds((start - dt.timedelta(days=1)).strftime("%Y-%m"))
    prev_cutoff = prev_start.replace(day=min(cutoff, prev_end.day))

    usd = converter(db, user)
    txns = spending(db, user, start, end, wallet=wallet)
    expenses = [t for t in txns if t.kind == Kind.expense]
    income = round(sum(usd(t) for t in txns if t.kind == Kind.income), 2)
    spent = round(sum(usd(t) for t in expenses), 2)
    spent_to_date = sum(usd(t) for t in expenses if t.date.day <= cutoff)
    prev_to_date = sum(
        usd(t) for t in spending(db, user, prev_start, prev_cutoff, wallet=wallet) if t.kind == Kind.expense
    )

    cats = {c.id: c.name for c in db.exec(select(Category).where(Category.user_id == user.id))} | {SHARED_CATEGORY: "Shared"}
    by_category = expense_by_category(txns, usd)
    top_id = max(by_category, key=by_category.get) if by_category else None
    biggest = max(expenses, key=usd) if expenses else None
    visits = defaultdict(int)
    for t in expenses:
        if t.merchant:
            visits[t.merchant] += 1
    visited = max(visits, key=visits.get) if visits else None

    return {
        "month": start.strftime("%Y-%m"),
        "in_progress": in_progress,
        "income": income,
        "expenses": spent,
        "net": round(income - spent, 2),
        "savings_rate": round(100 * (income - spent) / income, 1) if income else None,
        "compared_days": cutoff,
        "change": round(spent_to_date - prev_to_date, 2),
        "change_percent": round(100 * (spent_to_date - prev_to_date) / prev_to_date, 1) if prev_to_date else None,
        "top_category": {
            "name": cats.get(top_id, "Uncategorized"),
            "total": round(by_category[top_id], 2),
            "share": round(100 * by_category[top_id] / spent, 1) if spent else None,
        }
        if by_category
        else None,
        "biggest": {"merchant": biggest.merchant, "amount": round(usd(biggest), 2), "date": biggest.date} if biggest else None,
        "most_visited": {"merchant": visited, "count": visits[visited]} if visited else None,
        "over_budget": [b["name"] for b in budgets(db, user, start.strftime("%Y-%m")) if b["percent"] >= 100],
    }


@router.get("/budget-plan")
def budget_plan(db: DbSession, user: CurrentUser, month: str | None = None):
    """The month's income against what's assigned (zero-based) and against 50/30/20 targets.
    Expenses in categories without a group count as wants; the savings group is money set aside, so it isn't spent."""
    start, end = month_bounds(month)
    usd = converter(db, user)
    txns = spending(db, user, start, end)
    income = sum(usd(t) for t in txns if t.kind == Kind.income)
    spent = expense_by_category(txns, usd)
    categories = db.exec(select(Category).where(Category.user_id == user.id, Category.kind == CategoryKind.expense)).all()
    group_of = {c.id: c.budget_group for c in categories}
    needs = sum(v for cid, v in spent.items() if group_of.get(cid) == BudgetGroup.need)
    wants = sum(v for cid, v in spent.items() if group_of.get(cid) not in (BudgetGroup.need, BudgetGroup.savings))
    assigned = sum(b.monthly_limit for b in db.exec(select(Budget).where(Budget.user_id == user.id)))
    return {
        "month": start.strftime("%Y-%m"),
        "income": round(income, 2),
        "assigned": round(assigned, 2),
        "left_to_assign": round(income - assigned, 2),
        "groups": [
            {"group": "need", "actual": round(needs, 2), "target": round(0.5 * income, 2)},
            {"group": "want", "actual": round(wants, 2), "target": round(0.3 * income, 2)},
            {"group": "savings", "actual": round(income - needs - wants, 2), "target": round(0.2 * income, 2)},
        ],
        "ungrouped": [c.name for c in categories if c.budget_group is None],
    }


@router.get("/year")
def year_review(db: DbSession, user: CurrentUser, year: int | None = None):
    today = dt.date.today()
    year = year or today.year
    start, end = dt.date(year, 1, 1), min(dt.date(year, 12, 31), today)
    usd = converter(db, user)
    txns = spending(db, user, start, end) if start <= end else []
    income = sum(usd(t) for t in txns if t.kind == Kind.income)
    spent = sum(usd(t) for t in txns if t.kind == Kind.expense)
    months = cashflow(db, user, start, end, bucket="month") if txns else []
    busiest = max(months, key=lambda m: m["expense"]) if months else None
    previous = sum(usd(t) for t in spending(db, user, dt.date(year - 1, 1, 1), dt.date(year - 1, 12, 31)) if t.kind == Kind.expense)
    by_category = categories(db, user, start, end) if txns else []
    ranked = merchants(db, user, start, end, limit=5) if txns else {"largest": [], "frequent": []}
    goals = []
    for goal in db.exec(select(Goal).where(Goal.user_id == user.id).order_by(Goal.id)):
        gained = sum(signed(goal, t) for t in txns if t.goal_id == goal.id)
        if gained:
            wallet = db.get(Wallet, goal.wallet_id)
            goals.append({"name": goal.name, "gained": round(gained, 2), "currency": wallet.currency if wallet else "USD"})

    worth = balance_history(db, user, [start - dt.timedelta(days=1), end]) if start <= end else [{}, {}]
    return {
        "year": year,
        "in_progress": year == today.year,
        "income": round(income, 2),
        "expenses": round(spent, 2),
        "net": round(income - spent, 2),
        "savings_rate": round(100 * (income - spent) / income, 1) if income else None,
        "months": months,
        "busiest_month": {"month": busiest["period"], "expense": busiest["expense"]} if busiest and busiest["expense"] else None,
        "previous_expenses": round(previous, 2),
        "change_percent": round(100 * (spent - previous) / previous, 1) if previous else None,
        "categories": [{**c, "share": round(100 * c["total"] / spent, 1) if spent else None} for c in by_category],
        "largest": ranked["largest"],
        "frequent": ranked["frequent"],
        "goals": goals,
        "net_worth_start": round(sum(worth[0].values()), 2),
        "net_worth_end": round(sum(worth[1].values()), 2),
    }
