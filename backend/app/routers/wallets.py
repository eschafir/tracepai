from fastapi import APIRouter, HTTPException
from sqlmodel import or_, select

from app.auth import CurrentUser, DbSession
from app.models import Transaction, Wallet, WalletBase, WalletOut
from app.recurring import post_due
from app.wallets import balances

router = APIRouter(prefix="/wallets", tags=["wallets"])


def get_owned(db: DbSession, user: CurrentUser, wallet_id: int) -> Wallet:
    wallet = db.get(Wallet, wallet_id)
    if not wallet or wallet.user_id != user.id:
        raise HTTPException(404, "Wallet not found")
    return wallet


@router.get("")
def list_wallets(db: DbSession, user: CurrentUser) -> list[WalletOut]:
    post_due(db, user.id)
    totals = balances(db, user.id)
    wallets = db.exec(select(Wallet).where(Wallet.user_id == user.id).order_by(Wallet.id))
    return [WalletOut(**w.model_dump(), balance=totals.get(w.id, 0)) for w in wallets]


@router.post("")
def create_wallet(data: WalletBase, db: DbSession, user: CurrentUser) -> Wallet:
    wallet = Wallet.model_validate(data, update={"user_id": user.id})
    db.add(wallet)
    db.commit()
    db.refresh(wallet)
    return wallet


@router.put("/{wallet_id}")
def update_wallet(wallet_id: int, data: WalletBase, db: DbSession, user: CurrentUser) -> Wallet:
    wallet = get_owned(db, user, wallet_id)
    wallet.sqlmodel_update(data.model_dump())
    db.commit()
    db.refresh(wallet)
    return wallet


@router.delete("/{wallet_id}")
def delete_wallet(wallet_id: int, db: DbSession, user: CurrentUser):
    wallet = get_owned(db, user, wallet_id)
    used = db.exec(select(Transaction).where(or_(Transaction.wallet_id == wallet_id, Transaction.to_wallet_id == wallet_id))).first()
    if used:
        raise HTTPException(409, "Move or delete this wallet's transactions first.")
    db.delete(wallet)
    db.commit()
    return {"ok": True}
