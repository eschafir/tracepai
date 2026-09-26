"""Shared wallets: expenses paid from members' own wallets and split equally between the members at the time."""

from collections import defaultdict

from fastapi import HTTPException
from sqlmodel import Session, col, or_, select

from app import fx
from app.models import Settlement, SharedMember, SharedWallet, Transaction, User, Wallet


def member_ids(db: Session, ledger: SharedWallet) -> list[int]:
    members = db.exec(select(SharedMember.user_id).where(SharedMember.shared_wallet_id == ledger.id)).all()
    return [ledger.owner_id, *sorted(members)]


def my_ledgers(db: Session, user_id: int) -> list[SharedWallet]:
    joined = select(SharedMember.shared_wallet_id).where(SharedMember.user_id == user_id)
    stmt = select(SharedWallet).where(or_(SharedWallet.owner_id == user_id, col(SharedWallet.id).in_(joined)))
    return db.exec(stmt.order_by(SharedWallet.id)).all()


def get_member_ledger(db: Session, user_id: int, ledger_id: int) -> SharedWallet:
    ledger = db.get(SharedWallet, ledger_id)
    if not ledger or user_id not in member_ids(db, ledger):
        raise HTTPException(404, "Shared wallet not found")
    return ledger


def shares(txn: Transaction) -> dict[int, float]:
    """Who shares an expense and each person's fraction, from "1:60,4:40". The older "1,4" means an equal split."""
    if not txn.shared_members:
        return {}
    parts = [p.split(":") for p in txn.shared_members.split(",")]
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
