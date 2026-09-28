from fastapi import APIRouter, HTTPException
from sqlmodel import or_, select

from app import fx
from app.auth import CurrentUser, DbSession
from app.models import Goal, RecurringRule, Transaction, Wallet, WalletBase, WalletOut
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
    rates, _ = fx.user_rates(db, user.id)
    txns = db.exec(select(Transaction.wallet_id, Transaction.to_wallet_id).where(Transaction.user_id == user.id)).all()
    in_use = {wallet_id for pair in txns for wallet_id in pair}
    wallets = db.exec(select(Wallet).where(Wallet.user_id == user.id).order_by(Wallet.id))
    return [
        WalletOut(
            **w.model_dump(),
            balance=totals.get(w.id, 0),
            balance_usd=round(rates.usd(totals.get(w.id, 0), w.currency), 2),
            in_use=w.id in in_use,
        )
        for w in wallets
    ]


def has_transactions(db: DbSession, wallet_id: int) -> bool:
    stmt = select(Transaction).where(or_(Transaction.wallet_id == wallet_id, Transaction.to_wallet_id == wallet_id))
    return db.exec(stmt).first() is not None


def check_currency(db: DbSession, data: WalletBase):
    try:
        fx.refresh(db, data.currency, strict=True)
    except ValueError as err:
        raise HTTPException(422, str(err))


@router.post("")
def create_wallet(data: WalletBase, db: DbSession, user: CurrentUser) -> Wallet:
    check_currency(db, data)
    wallet = Wallet.model_validate(data, update={"user_id": user.id})
    db.add(wallet)
    db.commit()
    db.refresh(wallet)
    return wallet


@router.put("/{wallet_id}")
def update_wallet(wallet_id: int, data: WalletBase, db: DbSession, user: CurrentUser) -> Wallet:
    wallet = get_owned(db, user, wallet_id)
    if data.currency != wallet.currency:
        if has_transactions(db, wallet_id):
            raise HTTPException(409, "This wallet already has transactions, so its currency can't change.")
        check_currency(db, data)
    wallet.sqlmodel_update(data.model_dump())
    db.commit()
    db.refresh(wallet)
    return wallet


@router.delete("/{wallet_id}")
def delete_wallet(wallet_id: int, db: DbSession, user: CurrentUser):
    wallet = get_owned(db, user, wallet_id)
    if has_transactions(db, wallet_id):
        raise HTTPException(409, "Move or delete this wallet's transactions first.")
    rules = select(RecurringRule).where(or_(RecurringRule.wallet_id == wallet_id, RecurringRule.to_wallet_id == wallet_id))
    if db.exec(rules).first():
        raise HTTPException(409, "Delete or change the recurring items that use this wallet first.")
    if db.exec(select(Goal).where(Goal.wallet_id == wallet_id)).first():
        raise HTTPException(409, "Move or delete the goals kept in this wallet first.")
    db.delete(wallet)
    db.commit()
    return {"ok": True}
