"""Shared expenses: paid from the payer's own wallet and split by percent, either in a shared wallet (settled up as a
ledger) or on their own (each person pays back their share)."""

from collections import defaultdict

from fastapi import HTTPException
from sqlmodel import Session, col, or_, select

from app import fx
from app.models import Settlement, ShareConsent, SharePayment, SharedMember, SharedWallet, Transaction, User, Wallet


def member_ids(db: Session, ledger: SharedWallet) -> list[int]:
    """The owner and everyone who accepted the invitation."""
    stmt = select(SharedMember.user_id).where(SharedMember.shared_wallet_id == ledger.id, SharedMember.pending == False)  # noqa: E712
    return [ledger.owner_id, *sorted(db.exec(stmt).all())]


def invited_ids(db: Session, ledger: SharedWallet) -> list[int]:
    stmt = select(SharedMember.user_id).where(SharedMember.shared_wallet_id == ledger.id, SharedMember.pending == True)  # noqa: E712
    return sorted(db.exec(stmt).all())


def my_ledgers(db: Session, user_id: int, pending: bool = False) -> list[SharedWallet]:
    """The shared wallets the user owns or joined, or with pending, the ones they're invited to."""
    joined = select(SharedMember.shared_wallet_id).where(SharedMember.user_id == user_id, SharedMember.pending == pending)
    mine = col(SharedWallet.id).in_(joined) if pending else or_(SharedWallet.owner_id == user_id, col(SharedWallet.id).in_(joined))
    return db.exec(select(SharedWallet).where(mine).order_by(SharedWallet.id)).all()


def get_member_ledger(db: Session, user_id: int, ledger_id: int) -> SharedWallet:
    ledger = db.get(SharedWallet, ledger_id)
    if not ledger or user_id not in member_ids(db, ledger):
        raise HTTPException(404, "Shared wallet not found")
    return ledger


def shares(txn: Transaction) -> dict[int, float]:
    return parse_shares(txn.shared_members)


def parse_shares(shared_members: str | None) -> dict[int, float]:
    """Who shares an expense and each person's fraction, from "1:60,4:40". The older "1,4" means an equal split."""
    if not shared_members:
        return {}
    parts = [p.split(":") for p in shared_members.split(",")]
    if all(len(p) == 1 for p in parts):
        return {int(p[0]): 1 / len(parts) for p in parts}
    return {int(uid): float(percent) / 100 for uid, percent in parts}


def encode_shares(percents: dict[int, float]) -> str:
    return ",".join(f"{uid}:{round(percent, 4):g}" for uid, percent in percents.items() if percent > 0)


def equal_shares(ids: list[int]) -> dict[int, float]:
    """Percentages that add up to exactly 100, the last person taking the rounding (33.33, 33.33, 33.34)."""
    each = round(100 / len(ids), 2)
    return {uid: (round(100 - each * (len(ids) - 1), 2) if i == len(ids) - 1 else each) for i, uid in enumerate(ids)}


def expenses(db: Session, ledger: SharedWallet) -> list[Transaction]:
    stmt = select(Transaction).where(Transaction.shared_wallet_id == ledger.id)
    return db.exec(stmt.order_by(col(Transaction.date).desc(), col(Transaction.id).desc())).all()


def settlements(db: Session, ledger: SharedWallet) -> list[Settlement]:
    stmt = select(Settlement).where(Settlement.shared_wallet_id == ledger.id)
    return db.exec(stmt.order_by(col(Settlement.date).desc(), col(Settlement.id).desc())).all()


def in_ledger_currency(db: Session, ledger: SharedWallet):
    """Converts an expense from its payer's wallet currency into the ledger's, at the expense's date."""
    rates = fx.Rates(db, {ledger.currency})

    def convert(txn: Transaction) -> float:
        currency = db.get(Wallet, txn.wallet_id).currency
        return rates.usd(txn.amount, currency, txn.date) * rates.per_usd(ledger.currency, txn.date)

    return convert


def balances(db: Session, ledger: SharedWallet) -> dict[int, float]:
    """Each member's net position in the ledger's currency: positive means the others owe them."""
    net = defaultdict(float, {uid: 0.0 for uid in member_ids(db, ledger)})
    convert = in_ledger_currency(db, ledger)
    for txn in expenses(db, ledger):
        amount = convert(txn)
        net[txn.user_id] += amount
        for uid, fraction in shares(txn).items():
            net[uid] -= amount * fraction
    for s in settlements(db, ledger):
        net[s.from_user_id] += s.amount
        net[s.to_user_id] -= s.amount
    return {uid: round(v, 2) for uid, v in net.items()}


def debts(net: dict[int, float]) -> list[dict]:
    """The fewest payments that even everyone out: the biggest debtor pays the biggest creditor, and so on."""
    owed = sorted(([uid, v] for uid, v in net.items() if v > 0.005), key=lambda x: -x[1])
    owing = sorted(([uid, -v] for uid, v in net.items() if v < -0.005), key=lambda x: -x[1])
    out = []
    while owed and owing:
        amount = min(owed[0][1], owing[0][1])
        out.append({"from_user_id": owing[0][0], "to_user_id": owed[0][0], "amount": round(amount, 2)})
        owed[0][1] -= amount
        owing[0][1] -= amount
        if owed[0][1] < 0.005:
            owed.pop(0)
        if owing[0][1] < 0.005:
            owing.pop(0)
    return out


def usernames(db: Session, ids: list[int]) -> dict[int, str]:
    return {u.id: u.username for u in db.exec(select(User).where(col(User.id).in_(ids)))}


def consents(db: Session, user_id: int) -> dict[int, bool]:
    """Whose direct shares the user accepted (True) or declined (False). Anyone else's are waiting for an answer."""
    return {c.from_user_id: c.accepted for c in db.exec(select(ShareConsent).where(ShareConsent.user_id == user_id))}


def shared_with(db: Session, user_id: int, pending: bool = False) -> list[Transaction]:
    """Shared expenses outside shared wallets that the user paid or accepted a share of, newest first. With pending,
    the ones from people the user hasn't answered yet."""
    stmt = select(Transaction).where(
        col(Transaction.shared_wallet_id).is_(None),
        col(Transaction.shared_members).is_not(None),
        or_(Transaction.user_id == user_id, col(Transaction.shared_members).contains(f"{user_id}:")),
    )
    txns = db.exec(stmt.order_by(col(Transaction.date).desc(), col(Transaction.id).desc())).all()
    answers = consents(db, user_id)
    if pending:
        return [t for t in txns if t.user_id != user_id and user_id in shares(t) and t.user_id not in answers]
    return [t for t in txns if t.user_id == user_id or (user_id in shares(t) and answers.get(t.user_id))]


def share_payments(db: Session, txn: Transaction) -> list[SharePayment]:
    return db.exec(select(SharePayment).where(SharePayment.transaction_id == txn.id)).all()


def delete_payment(db: Session, payment: SharePayment):
    """A payment and the transactions that recorded it in either person's wallet."""
    for recorded in db.exec(select(Transaction).where(Transaction.share_payment_id == payment.id)):
        db.delete(recorded)
    db.delete(payment)
