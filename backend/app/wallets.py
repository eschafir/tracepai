from collections import defaultdict

from sqlmodel import Session, select

from app.models import Kind, Transaction, Wallet


def wallet_deltas(txn: Transaction) -> list[tuple[int, float]]:
    """How a transaction moves each wallet's balance."""
    if txn.kind == Kind.transfer:
        return [(txn.wallet_id, -txn.amount), (txn.to_wallet_id, txn.amount)]
    return [(txn.wallet_id, txn.amount if txn.kind == Kind.income else -txn.amount)]


def balances(db: Session, user_id: int) -> dict[int, float]:
    totals = defaultdict(float)
    for wallet in db.exec(select(Wallet).where(Wallet.user_id == user_id)):
        totals[wallet.id] += wallet.opening_balance
    for txn in db.exec(select(Transaction).where(Transaction.user_id == user_id)):
        for wallet_id, delta in wallet_deltas(txn):
            totals[wallet_id] += delta
    return {wallet_id: round(total, 2) for wallet_id, total in totals.items()}
