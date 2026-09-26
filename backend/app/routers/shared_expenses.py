import datetime as dt

from fastapi import APIRouter, HTTPException
from sqlmodel import SQLModel, select

from app.auth import CurrentUser, DbSession
from app.models import Kind, SharePayment, Transaction, User, Wallet
from app.shared import delete_payment, share_payments, shared_with, shares, usernames

router = APIRouter(prefix="/shared-expenses", tags=["shared expenses"])


def item(db: DbSession, txn: Transaction) -> dict:
    """A shared expense as both sides see it: who paid, each person's share, and whether they paid it back."""
    split = shares(txn)
    names = usernames(db, [txn.user_id, *split])
    paid = {p.user_id: p for p in share_payments(db, txn)}
    return {
        "id": txn.id,
        "date": txn.date,
        "merchant": txn.merchant,
        "amount": txn.amount,
        "currency": db.get(Wallet, txn.wallet_id).currency,
        "paid_by": {"id": txn.user_id, "username": names[txn.user_id]},
        "shares": [
            {
                "user_id": uid,
                "username": names[uid],
                "percent": round(fraction * 100, 2),
                "amount": round(txn.amount * fraction, 2),
                "payment": {
                    "id": paid[uid].id,
                    "date": paid[uid].date,
                    "recorded_by": db.exec(select(Transaction.user_id).where(Transaction.share_payment_id == paid[uid].id)).all(),
                }
                if uid in paid
                else None,
            }
            for uid, fraction in split.items()
        ],
    }


def get_shared(db: DbSession, user: CurrentUser, transaction_id: int) -> Transaction:
    txn = db.get(Transaction, transaction_id)
    if not txn or txn.shared_wallet_id is not None or not txn.shared_members or user.id not in (txn.user_id, *shares(txn)):
        raise HTTPException(404, "Shared expense not found")
    return txn


def get_payment(db: DbSession, user: CurrentUser, payment_id: int) -> tuple[SharePayment, Transaction]:
    """Only the person who paid the expense and the person paying back can see or change a payment."""
    payment = db.get(SharePayment, payment_id)
    txn = payment and db.get(Transaction, payment.transaction_id)
    if not payment or user.id not in (txn.user_id, payment.user_id):
        raise HTTPException(404, "Payment not found")
    return payment, txn


def record(db: DbSession, user: CurrentUser, payment: SharePayment, txn: Transaction, wallet_id: int):
    """The payment in one of the user's own wallets: it moves the balance but isn't spending or income."""
    wallet = db.get(Wallet, wallet_id)
    if not wallet or wallet.user_id != user.id:
        raise HTTPException(404, "Wallet not found")
    currency = db.get(Wallet, txn.wallet_id).currency
    if wallet.currency != currency:
        raise HTTPException(422, f"Choose a wallet in {currency}, the currency of this expense.")
    if db.exec(select(Transaction).where(Transaction.share_payment_id == payment.id, Transaction.user_id == user.id)).first():
        raise HTTPException(409, "You already recorded this payment in one of your wallets.")
    paying = payment.user_id == user.id
    other = db.get(User, txn.user_id if paying else payment.user_id)
    what = txn.merchant or "a shared expense"
    db.add(
        Transaction(
            user_id=user.id,
            date=payment.date,
            amount=round(txn.amount * shares(txn)[payment.user_id], 2),
            kind=Kind.expense if paying else Kind.income,
            merchant=f"Paid {other.username} back for {what}" if paying else f"{other.username} paid back for {what}",
            wallet_id=wallet.id,
            share_payment_id=payment.id,
        )
    )


@router.get("")
def list_shared_expenses(db: DbSession, user: CurrentUser):
    return [item(db, t) for t in shared_with(db, user.id)]


@router.get("/{transaction_id}")
def get_shared_expense(transaction_id: int, db: DbSession, user: CurrentUser):
    return item(db, get_shared(db, user, transaction_id))


class PaymentIn(SQLModel):
    user_id: int  # whose share was paid back
    date: dt.date
    wallet_id: int | None = None  # also record it in one of your own wallets


@router.post("/{transaction_id}/payments")
def mark_paid(transaction_id: int, data: PaymentIn, db: DbSession, user: CurrentUser):
    txn = get_shared(db, user, transaction_id)
    if data.user_id == txn.user_id or data.user_id not in shares(txn):
        raise HTTPException(422, "Only someone with a share of this expense can pay it back.")
    if user.id not in (txn.user_id, data.user_id):
        raise HTTPException(422, "You can only mark your own share, or a share of an expense you paid.")
    if any(p.user_id == data.user_id for p in share_payments(db, txn)):
        raise HTTPException(409, "This share is already paid back.")
    payment = SharePayment(transaction_id=txn.id, user_id=data.user_id, date=data.date)
    db.add(payment)
    db.flush()
    if data.wallet_id:
        record(db, user, payment, txn, data.wallet_id)
    db.commit()
    return item(db, txn)


class RecordIn(SQLModel):
    wallet_id: int


@router.post("/payments/{payment_id}/record")
def record_payment(payment_id: int, data: RecordIn, db: DbSession, user: CurrentUser):
    """The other person records the same payment in their own wallet."""
    payment, txn = get_payment(db, user, payment_id)
    record(db, user, payment, txn, data.wallet_id)
    db.commit()
    return item(db, txn)


@router.delete("/payments/{payment_id}")
def unmark_paid(payment_id: int, db: DbSession, user: CurrentUser):
    payment, txn = get_payment(db, user, payment_id)
    delete_payment(db, payment)
    db.commit()
    return item(db, txn)
