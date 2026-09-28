import calendar
import datetime as dt
import threading
from collections import defaultdict
from statistics import median

from sqlmodel import Session, select

from app.categorize import normalize
from app.models import Frequency, Kind, RecurringRule, Transaction


def advance(date: dt.date, frequency: Frequency) -> dt.date:
    if frequency == Frequency.weekly:
        return date + dt.timedelta(days=7)
    if frequency == Frequency.yearly:
        year, month = date.year + 1, date.month
    else:
        year, month = (date.year + 1, 1) if date.month == 12 else (date.year, date.month + 1)
    return date.replace(year=year, month=month, day=min(date.day, calendar.monthrange(year, month)[1]))


# Pages load several endpoints in parallel and each calls post_due, so posting is serialized to keep two requests
# from posting the same due date: by this lock within a process, and by locking the rule rows (FOR UPDATE, which
# SQLite ignores) across processes. A request that waited then sees the new next_date and has nothing to post.
_posting = threading.Lock()


def post_due(db: Session, user_id: int, today: dt.date | None = None):
    today = today or dt.date.today()
    with _posting:
        due = select(RecurringRule).where(RecurringRule.user_id == user_id, RecurringRule.next_date <= today)
        rules = db.exec(due.with_for_update().execution_options(populate_existing=True)).all()
        for rule in rules:
            while rule.next_date <= today:
                fields = rule.model_dump(exclude={"id", "user_id", "frequency", "next_date", "price_seen"})
                db.add(Transaction(**fields, user_id=user_id, date=rule.next_date, recurring_id=rule.id))
                rule.next_date = advance(rule.next_date, rule.frequency)
        if rules:
            db.commit()


def delete_rule(db: Session, rule: RecurringRule):
    """The transactions a rule already added really happened, so they stay and only lose the link."""
    for txn in db.exec(select(Transaction).where(Transaction.recurring_id == rule.id)):
        txn.recurring_id = None
    db.flush()
    db.delete(rule)


def suggestions(db: Session, user_id: int) -> list[dict]:
    covered = {normalize(r.merchant) for r in db.exec(select(RecurringRule).where(RecurringRule.user_id == user_id))}
    groups = defaultdict(list)
    for txn in db.exec(
        select(Transaction).where(Transaction.user_id == user_id, Transaction.kind != Kind.transfer).order_by(Transaction.date)
    ):
        key = normalize(txn.merchant)
        if key and key not in covered:
            groups[(txn.wallet_id, key)].append(txn)

    found = []
    for (_, key), txns in groups.items():
        if len(txns) < 3:
            continue
        typical = median(t.amount for t in txns)
        if any(abs(t.amount - typical) > 0.1 * typical for t in txns):
            continue
        gaps = [(b.date - a.date).days for a, b in zip(txns, txns[1:])]
        if all(25 <= g <= 35 for g in gaps):
            frequency = Frequency.monthly
        elif all(6 <= g <= 8 for g in gaps):
            frequency = Frequency.weekly
        else:
            continue
        last = txns[-1]
        found.append(
            {
                "merchant": last.merchant,
                "amount": round(typical, 2),
                "kind": last.kind,
                "wallet_id": last.wallet_id,
                "category_id": last.category_id,
                "frequency": frequency,
                "next_date": advance(last.date, frequency),
                "occurrences": len(txns),
            }
        )
    return sorted(found, key=lambda s: s["next_date"])


def price_changes(db: Session, user_id: int, today: dt.date | None = None) -> list[dict]:
    """Expense items whose latest real charge (last 45 days, same wallet and merchant) differs from the saved amount."""
    today = today or dt.date.today()
    rules = db.exec(select(RecurringRule).where(RecurringRule.user_id == user_id, RecurringRule.kind == Kind.expense)).all()
    recent = db.exec(
        select(Transaction).where(
            Transaction.user_id == user_id, Transaction.kind == Kind.expense, Transaction.date >= today - dt.timedelta(days=45)
        )
    ).all()
    found = []
    for rule in rules:
        key = normalize(rule.merchant)
        matches = [t for t in recent if t.wallet_id == rule.wallet_id and key and normalize(t.merchant) == key]
        if not matches:
            continue
        # A charge the item didn't post itself (an import, a manual entry) is the best evidence of the real price.
        latest = max(matches, key=lambda t: (t.date, t.recurring_id != rule.id, t.id))
        if abs(latest.amount - rule.amount) > max(0.01 * rule.amount, 0.5) and latest.amount != rule.price_seen:
            found.append({"rule_id": rule.id, "merchant": rule.merchant, "wallet_id": rule.wallet_id,
                          "old": rule.amount, "new": latest.amount, "date": latest.date})
    return found
