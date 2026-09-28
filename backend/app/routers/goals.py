import datetime as dt

from fastapi import APIRouter, HTTPException
from sqlmodel import col, select

from app.auth import CurrentUser, DbSession, check_owned
from app.models import ContributionIn, Entry, Frequency, Goal, GoalBase, Kind, RecurringRule, Transaction, Wallet
from app.recurring import advance, delete_rule, post_due
from app.wallets import check_received

router = APIRouter(prefix="/goals", tags=["goals"])


def get_owned(db: DbSession, user: CurrentUser, goal_id: int) -> Goal:
    goal = db.get(Goal, goal_id)
    if not goal or goal.user_id != user.id:
        raise HTTPException(404, "Goal not found")
    return goal


def linked(db: DbSession, goal: Goal) -> list[Transaction]:
    """The transfers that moved money into or out of the goal, newest first."""
    stmt = select(Transaction).where(Transaction.goal_id == goal.id)
    return db.exec(stmt.order_by(col(Transaction.date).desc(), col(Transaction.id).desc())).all()


def signed(goal: Goal, txn: Transaction) -> float:
    """The transfer's effect on the goal, in the goal wallet's currency."""
    return (txn.to_amount or txn.amount) if txn.to_wallet_id == goal.wallet_id else -txn.amount


def check_linked(db: DbSession, user: CurrentUser, data: Entry):
    """A transaction or recurring item linked to a goal must be a transfer to or from the goal's wallet."""
    goal = db.get(Goal, data.goal_id)
    if not goal or goal.user_id != user.id:
        raise HTTPException(422, "Goal not found")
    if data.kind != Kind.transfer or goal.wallet_id not in (data.wallet_id, data.to_wallet_id):
        wallet = db.get(Wallet, goal.wallet_id) if goal.wallet_id else None
        where = wallet.name if wallet else "the goal's wallet"
        raise HTTPException(422, f"This is money for the goal {goal.name}, so it must be a transfer to or from {where}.")


def months_until(target: dt.date, today: dt.date) -> int:
    """Whole months between today and the target date, and never less than 1."""
    months = (target.year - today.year) * 12 + target.month - today.month - (1 if target.day < today.day else 0)
    return max(1, months)


def progress(db: DbSession, goal: Goal, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    transfers = linked(db, goal)
    saved = round(sum(signed(goal, txn) for txn in transfers), 2)
    remaining = round(max(goal.target_amount - saved, 0), 2)
    months = months_until(goal.target_date, today) if goal.target_date else None
    wallet = db.get(Wallet, goal.wallet_id) if goal.wallet_id else None
    rules = db.exec(select(RecurringRule).where(RecurringRule.goal_id == goal.id)).all()
    return {
        **goal.model_dump(),
        "currency": wallet.currency if wallet else "USD",
        "repeating": [{"rule_id": r.id, "amount": r.amount, "wallet_id": r.wallet_id, "next_date": r.next_date} for r in rules],
        "saved": saved,
        "transfer_count": len(transfers),
        "percent": round(100 * saved / goal.target_amount, 1),
        "remaining": remaining,
        "months_left": months,
        "monthly_needed": round(remaining / months, 2) if months and remaining else None,
    }


@router.get("")
def list_goals(db: DbSession, user: CurrentUser):
    post_due(db, user.id)  # monthly goal transfers that are due count right away
    goals = db.exec(select(Goal).where(Goal.user_id == user.id).order_by(Goal.id)).all()
    return [progress(db, g) for g in goals]


@router.post("")
def create_goal(data: GoalBase, db: DbSession, user: CurrentUser):
    check_owned(db, Wallet, user.id, data.wallet_id)
    goal = Goal.model_validate(data, update={"user_id": user.id})
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return progress(db, goal)


@router.put("/{goal_id}")
def update_goal(goal_id: int, data: GoalBase, db: DbSession, user: CurrentUser):
    goal = get_owned(db, user, goal_id)
    check_owned(db, Wallet, user.id, data.wallet_id)
    if data.wallet_id != goal.wallet_id and linked(db, goal):
        raise HTTPException(422, "Money has already moved into this goal's wallet, so the goal must stay there.")
    goal.sqlmodel_update(data.model_dump())
    db.commit()
    db.refresh(goal)
    return progress(db, goal)


@router.delete("/{goal_id}")
def delete_goal(goal_id: int, db: DbSession, user: CurrentUser):
    """The money really moved, so the transfers stay; they just lose the goal. Its monthly transfers stop."""
    goal = get_owned(db, user, goal_id)
    for txn in linked(db, goal):
        txn.goal_id = None
    for rule in db.exec(select(RecurringRule).where(RecurringRule.goal_id == goal.id)):
        delete_rule(db, rule)
    db.flush()
    db.delete(goal)
    db.commit()
    return {"ok": True}


@router.get("/{goal_id}/contributions")
def list_contributions(goal_id: int, db: DbSession, user: CurrentUser):
    goal = get_owned(db, user, goal_id)
    return [
        {
            "id": txn.id,
            "date": txn.date,
            "amount": signed(goal, txn),
            "note": txn.notes,
            "wallet_id": txn.wallet_id if txn.to_wallet_id == goal.wallet_id else txn.to_wallet_id,
        }
        for txn in linked(db, goal)
    ]


@router.post("/{goal_id}/contributions")
def add_contribution(goal_id: int, data: ContributionIn, db: DbSession, user: CurrentUser):
    goal = get_owned(db, user, goal_id)
    if goal.wallet_id is None:
        raise HTTPException(422, "Choose where this goal's money is kept first.")
    check_owned(db, Wallet, user.id, data.wallet_id)
    if data.wallet_id == goal.wallet_id:
        raise HTTPException(422, "Choose a different wallet from the one this goal is kept in.")
    if data.repeat and data.direction == "out":
        raise HTTPException(422, "Only adding money can repeat.")
    source, destination = (data.wallet_id, goal.wallet_id) if data.direction == "in" else (goal.wallet_id, data.wallet_id)
    txn = Transaction(
        user_id=user.id,
        date=data.date,
        amount=data.amount,
        to_amount=data.received,
        kind=Kind.transfer,
        merchant=goal.name,
        notes=data.note,
        wallet_id=source,
        to_wallet_id=destination,
        goal_id=goal.id,
    )
    check_received(db, txn)
    db.add(txn)
    if data.repeat:
        fields = txn.model_dump(include={"amount", "to_amount", "kind", "merchant", "notes", "wallet_id", "to_wallet_id", "goal_id"})
        db.add(RecurringRule(**fields, user_id=user.id, frequency=Frequency.monthly, next_date=advance(data.date, Frequency.monthly)))
    db.commit()
    return progress(db, goal)


@router.delete("/contributions/{transaction_id}")
def delete_contribution(transaction_id: int, db: DbSession, user: CurrentUser):
    """Removing money from a goal's history deletes its transfer, so the wallet balances go back."""
    txn = db.get(Transaction, transaction_id)
    if not txn or txn.user_id != user.id or txn.goal_id is None:
        raise HTTPException(404, "Contribution not found")
    goal = get_owned(db, user, txn.goal_id)
    db.delete(txn)
    db.commit()
    return progress(db, goal)
