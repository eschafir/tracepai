import datetime as dt

from fastapi import APIRouter, HTTPException
from sqlmodel import col, or_, select

from app.auth import CurrentUser, DbSession
from app.models import RecurringRule, Split, Transaction, TransactionIn, TransactionOut
from app.recurring import advance, post_due

router = APIRouter(prefix="/transactions", tags=["transactions"])


def get_owned(db: DbSession, user: CurrentUser, transaction_id: int) -> Transaction:
    txn = db.get(Transaction, transaction_id)
    if not txn or txn.user_id != user.id:
        raise HTTPException(404, "Transaction not found")
    return txn


def query_transactions(
    db: DbSession,
    user: CurrentUser,
    start: dt.date | None = None,
    end: dt.date | None = None,
    category: int | None = None,
    tag: str | None = None,
    q: str | None = None,
    wallet: int | None = None,
) -> list[Transaction]:
    post_due(db, user.id)
    stmt = select(Transaction).where(Transaction.user_id == user.id)
    if start:
        stmt = stmt.where(Transaction.date >= start)
    if end:
        stmt = stmt.where(Transaction.date <= end)
    if category:
        split_txns = select(Split.transaction_id).where(Split.category_id == category)
        stmt = stmt.where(or_(Transaction.category_id == category, col(Transaction.id).in_(split_txns)))
    if tag:
        stmt = stmt.where(col(Transaction.tags).contains(tag))
    if q:
        stmt = stmt.where(or_(col(Transaction.merchant).icontains(q), col(Transaction.notes).icontains(q)))
    if wallet:
        stmt = stmt.where(or_(Transaction.wallet_id == wallet, Transaction.to_wallet_id == wallet))
    return db.exec(stmt.order_by(col(Transaction.date).desc(), col(Transaction.id).desc())).all()


def apply(txn: Transaction, data: TransactionIn):
    txn.sqlmodel_update(data.model_dump(exclude={"splits", "repeat", "recurring_id"}))
    txn.splits = [Split(**s.model_dump()) for s in data.splits]
    if txn.splits:
        txn.category_id = None


@router.get("")
def list_transactions(
    db: DbSession,
    user: CurrentUser,
    start: dt.date | None = None,
    end: dt.date | None = None,
    category: int | None = None,
    tag: str | None = None,
    q: str | None = None,
    wallet: int | None = None,
) -> list[TransactionOut]:
    return query_transactions(db, user, start, end, category, tag, q, wallet)


@router.post("")
def create_transaction(data: TransactionIn, db: DbSession, user: CurrentUser) -> TransactionOut:
    txn = Transaction(user_id=user.id, date=data.date, amount=data.amount, wallet_id=data.wallet_id)
    apply(txn, data)
    if data.repeat:
        rule = RecurringRule(
            **data.model_dump(include={"wallet_id", "to_wallet_id", "amount", "kind", "merchant", "category_id", "notes", "tags"}),
            user_id=user.id,
            frequency=data.repeat,
            next_date=advance(data.date, data.repeat),
        )
        db.add(rule)
        db.flush()
        txn.recurring_id = rule.id
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


@router.put("/{transaction_id}")
def update_transaction(transaction_id: int, data: TransactionIn, db: DbSession, user: CurrentUser) -> TransactionOut:
    txn = get_owned(db, user, transaction_id)
    apply(txn, data)
    db.commit()
    db.refresh(txn)
    return txn


@router.delete("/{transaction_id}")
def delete_transaction(transaction_id: int, db: DbSession, user: CurrentUser):
    db.delete(get_owned(db, user, transaction_id))
    db.commit()
    return {"ok": True}
