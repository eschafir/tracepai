import datetime as dt

from fastapi import APIRouter, HTTPException
from sqlmodel import Field, SQLModel, select

from app import fx
from app.auth import CurrentUser, DbSession
from app.models import Category, Kind, Settlement, SharedMember, SharedWallet, SharedWalletBase, Transaction, User, Wallet
from app.shared import (
    balances,
    debts,
    expenses,
    get_member_ledger,
    in_ledger_currency,
    member_ids,
    my_ledgers,
    shares,
    settlements,
    usernames,
)

router = APIRouter(prefix="/shared", tags=["shared"])


def get_owned(db: DbSession, user: CurrentUser, ledger_id: int) -> SharedWallet:
    ledger = get_member_ledger(db, user.id, ledger_id)
    if ledger.owner_id != user.id:
        raise HTTPException(403, "Only the owner of this shared wallet can do that.")
    return ledger


def summary(db: DbSession, user: CurrentUser, ledger: SharedWallet) -> dict:
    ids = member_ids(db, ledger)
    names = usernames(db, ids)
    return {
        **ledger.model_dump(),
        "members": [{"id": uid, "username": names[uid]} for uid in ids],
        "my_balance": balances(db, ledger)[user.id],
        "expense_count": len(expenses(db, ledger)),
        "in_use": bool(expenses(db, ledger) or settlements(db, ledger)),  # its currency is locked
        "categories": db.exec(select(Category).where(Category.user_id == ledger.owner_id).order_by(Category.id)).all(),
    }


def check_currency(db: DbSession, data: SharedWalletBase):
    data.currency = data.currency.upper()
    try:
        fx.refresh(db, data.currency, strict=True)
    except ValueError as err:
        raise HTTPException(422, str(err))


class SharedWalletIn(SharedWalletBase):
    members: list[str] | None = None  # usernames besides the owner; on update, the whole list


def find_users(db: DbSession, names: list[str]) -> list[User]:
    found = []
    for name in {n.strip() for n in names if n.strip()}:
        member = db.exec(select(User).where(User.username == name)).first()
        if not member:
            raise HTTPException(404, f"No one is signed up as {name}.")
        found.append(member)
    return found


def set_members(db: DbSession, ledger: SharedWallet, names: list[str]):
    """Add the people listed and remove the ones who aren't, as long as they're settled up. The owner always stays."""
    wanted = {u.id for u in find_users(db, names)} - {ledger.owner_id}
    current = set(member_ids(db, ledger)) - {ledger.owner_id}
    net = balances(db, ledger)
    for uid in current - wanted:
        if abs(net.get(uid, 0)) >= 0.01:
            raise HTTPException(409, f"{usernames(db, [uid])[uid]} still owes or is owed money here. Settle up first.")
        db.delete(db.get(SharedMember, (ledger.id, uid)))
    for uid in wanted - current:
        db.add(SharedMember(shared_wallet_id=ledger.id, user_id=uid))


@router.get("")
def list_shared(db: DbSession, user: CurrentUser):
    return [summary(db, user, ledger) for ledger in my_ledgers(db, user.id)]


@router.post("")
def create_shared(data: SharedWalletIn, db: DbSession, user: CurrentUser):
    check_currency(db, data)
    ledger = SharedWallet.model_validate(data, update={"owner_id": user.id})
    db.add(ledger)
    db.flush()
    set_members(db, ledger, data.members or [])
    db.commit()
    db.refresh(ledger)
    return summary(db, user, ledger)


@router.put("/{ledger_id}")
def update_shared(ledger_id: int, data: SharedWalletIn, db: DbSession, user: CurrentUser):
    ledger = get_owned(db, user, ledger_id)
    if data.currency.upper() != ledger.currency:
        if expenses(db, ledger) or settlements(db, ledger):
            raise HTTPException(409, "This shared wallet already has expenses, so its currency can't change.")
        check_currency(db, data)
    ledger.sqlmodel_update(data.model_dump(exclude={"members"}))
    if data.members is not None:
        set_members(db, ledger, data.members)
    db.commit()
    return summary(db, user, ledger)


@router.delete("/{ledger_id}")
def delete_shared(ledger_id: int, db: DbSession, user: CurrentUser):
    """Deletes the shared wallet and everything added to it: its expenses from every member's wallet, its payments
    and the payments recorded in wallets."""
    ledger = get_owned(db, user, ledger_id)
    for txn in expenses(db, ledger):
        db.delete(txn)
    for settlement in settlements(db, ledger):
        for txn in db.exec(select(Transaction).where(Transaction.settlement_id == settlement.id)):
            db.delete(txn)
        db.delete(settlement)
    for member in db.exec(select(SharedMember).where(SharedMember.shared_wallet_id == ledger.id)):
        db.delete(member)
    db.delete(ledger)
    db.commit()
    return {"ok": True}


@router.get("/{ledger_id}")
def ledger_detail(ledger_id: int, db: DbSession, user: CurrentUser):
    """Everything members see: expenses (in the payer's currency and the ledger's), payments, and who owes whom."""
    ledger = get_member_ledger(db, user.id, ledger_id)
    convert = in_ledger_currency(db, ledger)
    net = balances(db, ledger)
    return {
        **summary(db, user, ledger),
        "expenses": [
            {
                "id": t.id,
                "date": t.date,
                "merchant": t.merchant,
                "category_id": t.category_id,
                "splits": [{"category_id": s.category_id, "amount": s.amount} for s in t.splits],
                "amount": t.amount,
                "currency": db.get(Wallet, t.wallet_id).currency,
                "amount_shared": round(convert(t), 2),
                "paid_by": t.user_id,
                "shares": [{"user_id": uid, "percent": round(f * 100, 2)} for uid, f in shares(t).items()],
            }
            for t in expenses(db, ledger)
        ],
        "settlements": [
            {**s.model_dump(), "recorded_by": db.exec(select(Transaction.user_id).where(Transaction.settlement_id == s.id)).all()}
            for s in settlements(db, ledger)
        ],
        "balances": net,
        "debts": debts(net),
    }


class NewMember(SQLModel):
    username: str


@router.post("/{ledger_id}/members")
def add_member(ledger_id: int, data: NewMember, db: DbSession, user: CurrentUser):
    ledger = get_owned(db, user, ledger_id)
    member = db.exec(select(User).where(User.username == data.username.strip())).first()
    if not member:
        raise HTTPException(404, f"No one is signed up as {data.username.strip()}.")
    if member.id in member_ids(db, ledger):
        raise HTTPException(409, f"{member.username} is already in this shared wallet.")
    db.add(SharedMember(shared_wallet_id=ledger.id, user_id=member.id))
    db.commit()
    return summary(db, user, ledger)


@router.delete("/{ledger_id}/members/{user_id}")
def remove_member(ledger_id: int, user_id: int, db: DbSession, user: CurrentUser):
    """The owner can remove anyone else; a member can leave. Only once they're settled up."""
    ledger = get_member_ledger(db, user.id, ledger_id)
    if user_id == ledger.owner_id or (user.id != ledger.owner_id and user_id != user.id):
        raise HTTPException(403, "The owner can remove members, and members can leave. The owner can't be removed.")
    membership = db.get(SharedMember, (ledger.id, user_id))
    if not membership:
        raise HTTPException(404, "Not a member of this shared wallet")
    if abs(balances(db, ledger).get(user_id, 0)) >= 0.01:
        raise HTTPException(409, "Settle up first: this member still owes or is owed money here.")
    db.delete(membership)
    db.commit()
    return {"ok": True}


class SettlementIn(SQLModel):
    from_user_id: int
    to_user_id: int
    amount: float = Field(gt=0)
    date: dt.date
    wallet_id: int | None = None  # also record the payment in one of your own wallets


def record_payment(db: DbSession, user: CurrentUser, ledger: SharedWallet, settlement: Settlement, wallet_id: int):
    """A settle-up payment in the user's own wallet: it moves the balance but isn't spending or income."""
    wallet = db.get(Wallet, wallet_id)
    if not wallet or wallet.user_id != user.id:
        raise HTTPException(404, "Wallet not found")
    if wallet.currency != ledger.currency:
        raise HTTPException(422, f"Choose a wallet in {ledger.currency}, the currency of this shared wallet.")
    if db.exec(select(Transaction).where(Transaction.settlement_id == settlement.id, Transaction.user_id == user.id)).first():
        raise HTTPException(409, "You already recorded this payment in one of your wallets.")
    paying = settlement.from_user_id == user.id
    other = db.get(User, settlement.to_user_id if paying else settlement.from_user_id)
    db.add(
        Transaction(
            user_id=user.id,
            date=settlement.date,
            amount=settlement.amount,
            kind=Kind.expense if paying else Kind.income,
            merchant=f"Settle up with {other.username}",
            wallet_id=wallet.id,
            settlement_id=settlement.id,
        )
    )


@router.post("/{ledger_id}/settlements")
def settle(ledger_id: int, data: SettlementIn, db: DbSession, user: CurrentUser):
    ledger = get_member_ledger(db, user.id, ledger_id)
    ids = member_ids(db, ledger)
    if user.id not in (data.from_user_id, data.to_user_id) or data.from_user_id == data.to_user_id:
        raise HTTPException(422, "You can only record a payment you made or received.")
    if data.from_user_id not in ids or data.to_user_id not in ids:
        raise HTTPException(422, "Both people must be members of this shared wallet.")
    settlement = Settlement(shared_wallet_id=ledger.id, **data.model_dump(exclude={"wallet_id"}))
    db.add(settlement)
    db.flush()
    if data.wallet_id:
        record_payment(db, user, ledger, settlement, data.wallet_id)
    db.commit()
    db.refresh(settlement)
    return settlement


class RecordIn(SQLModel):
    wallet_id: int


@router.post("/settlements/{settlement_id}/record")
def record_settlement(settlement_id: int, data: RecordIn, db: DbSession, user: CurrentUser):
    """The other person records the same payment in their own wallet."""
    settlement = db.get(Settlement, settlement_id)
    if not settlement or user.id not in (settlement.from_user_id, settlement.to_user_id):
        raise HTTPException(404, "Payment not found")
    record_payment(db, user, get_member_ledger(db, user.id, settlement.shared_wallet_id), settlement, data.wallet_id)
    db.commit()
    return {"ok": True}


@router.delete("/settlements/{settlement_id}")
def delete_settlement(settlement_id: int, db: DbSession, user: CurrentUser):
    settlement = db.get(Settlement, settlement_id)
    if not settlement or user.id not in (settlement.from_user_id, settlement.to_user_id):
        raise HTTPException(404, "Payment not found")
    for txn in db.exec(select(Transaction).where(Transaction.settlement_id == settlement.id)):
        db.delete(txn)
    db.delete(settlement)
    db.commit()
    return {"ok": True}
