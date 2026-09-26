from collections import defaultdict

from fastapi import HTTPException
from sqlmodel import Session, select

from app.models import Entry, Kind, Transaction, Wallet


def wallet_deltas(txn: Transaction) -> list[tuple[int, float]]:
    """How a transaction moves each wallet's balance, in each wallet's own currency."""
    if txn.kind == Kind.transfer:
        return [(txn.wallet_id, -txn.amount), (txn.to_wallet_id, txn.to_amount or txn.amount)]
    return [(txn.wallet_id, txn.amount if txn.kind == Kind.income else -txn.amount)]


def balances(db: Session, user_id: int) -> dict[int, float]:
    totals = defaultdict(float)
    for wallet in db.exec(select(Wallet).where(Wallet.user_id == user_id)):
        totals[wallet.id] += wallet.opening_balance
    for txn in db.exec(select(Transaction).where(Transaction.user_id == user_id)):
        for wallet_id, delta in wallet_deltas(txn):
            totals[wallet_id] += delta
    return {wallet_id: round(total, 2) for wallet_id, total in totals.items()}


def check_received(db: Session, entry: Entry):
    """A transfer between currencies needs the amount received; one within a currency must not have it."""
    if entry.kind != Kind.transfer:
        return
    source, destination = db.get(Wallet, entry.wallet_id), db.get(Wallet, entry.to_wallet_id)
    if source.currency == destination.currency and entry.to_amount is not None:
        raise HTTPException(422, f"Both wallets use {source.currency}, so leave the received amount empty.")
    if source.currency != destination.currency and entry.to_amount is None:
        raise HTTPException(422, f"{destination.name} uses {destination.currency}. Enter the amount received in {destination.currency}.")
