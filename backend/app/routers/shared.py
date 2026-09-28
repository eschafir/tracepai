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
    invited_ids,
    member_ids,
    my_ledgers,
    shared_with,
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
    ids, invited = member_ids(db, ledger), invited_ids(db, ledger)
    names = usernames(db, ids + invited)
    return {
        **ledger.model_dump(),
        "members": [{"id": uid, "username": names[uid]} for uid in ids],
        "invited": [{"id": uid, "username": names[uid]} for uid in invited],  # they haven't accepted yet
        "my_balance": balances(db, ledger)[user.id],
        "expense_count": len(expenses(db, ledger)),
        "in_use": bool(expenses(db, ledger) or settlements(db, ledger)),  # its currency is locked
        "categories": db.exec(select(Category).where(Category.user_id == ledger.owner_id).order_by(Category.id)).all(),
    }


def check_currency(db: DbSession, data: SharedWalletBase):
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
    """Invite the people listed and remove the ones who aren't, as long as they're settled up. The owner always stays."""
    wanted = {u.id for u in find_users(db, names)} - {ledger.owner_id}
    current = {m.user_id: m for m in db.exec(select(SharedMember).where(SharedMember.shared_wallet_id == ledger.id))}
    net = balances(db, ledger)
    for uid in set(current) - wanted:
        if abs(net.get(uid, 0)) >= 0.01:
            raise HTTPException(409, f"{usernames(db, [uid])[uid]} still owes or is owed money here. Settle up first.")
        db.delete(current[uid])
    for uid in wanted - set(current):
        db.add(SharedMember(shared_wallet_id=ledger.id, user_id=uid, pending=True))


@router.get("")
def list_shared(db: DbSession, user: CurrentUser):
    return [summary(db, user, ledger) for ledger in my_ledgers(db, user.id)]


@router.get("/requests")
def share_requests(db: DbSession, user: CurrentUser):
    """What others want to share with the user and nothing counts for until they accept: shared wallets they're invited
    to, and people who shared expenses with them directly."""
    wallets = my_ledgers(db, user.id, pending=True)
    waiting = shared_with(db, user.id, pending=True)
    owners = usernames(db, [w.owner_id for w in wallets] + [t.user_id for t in waiting])
    people = {}
    for txn in waiting:
        people.setdefault(txn.user_id, {"id": txn.user_id, "username": owners[txn.user_id], "expenses": 0})["expenses"] += 1
    return {
        "wallets": [{"id": w.id, "name": w.name, "owner": owners[w.owner_id]} for w in wallets],
        "people": list(people.values()),
    }


def invitation(db: DbSession, user: CurrentUser, ledger_id: int) -> SharedMember:
    membership = db.get(SharedMember, (ledger_id, user.id))
    if not membership or not membership.pending:
        raise HTTPException(404, "Invitation not found")
    return membership


@router.post("/{ledger_id}/accept")
def accept_invitation(ledger_id: int, db: DbSession, user: CurrentUser):
    invitation(db, user, ledger_id).pending = False
    db.commit()
    return summary(db, user, db.get(SharedWallet, ledger_id))


@router.post("/{ledger_id}/decline")
def decline_invitation(ledger_id: int, db: DbSession, user: CurrentUser):
    db.delete(invitation(db, user, ledger_id))
    db.commit()
    return {"ok": True}


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
    if data.currency != ledger.currency:
        if expenses(db, ledger) or settlements(db, ledger):
            raise HTTPException(409, "This shared wallet already has expenses, so its currency can't change.")
        check_currency(db, data)
    if data.members is not None:  # first: it may fetch rates, which must happen before anything changes
        set_members(db, ledger, data.members)
    ledger.sqlmodel_update(data.model_dump(exclude={"members"}))
    db.commit()
    return summary(db, user, ledger)


@router.delete("/{ledger_id}")
def delete_shared(ledger_id: int, db: DbSession, user: CurrentUser):
    """Deletes the shared wallet and everything added to it: its expenses from every member's wallet, its payments
    and the payments recorded in wallets."""
    ledger = get_owned(db, user, ledger_id)
    payments = settlements(db, ledger)
    for txn in expenses(db, ledger):
        db.delete(txn)
    for settlement in payments:
        for txn in db.exec(select(Transaction).where(Transaction.settlement_id == settlement.id)):
            db.delete(txn)
    db.flush()  # transactions first, then what they point to
    for row in [*payments, *db.exec(select(SharedMember).where(SharedMember.shared_wallet_id == ledger.id))]:
        db.delete(row)
    db.flush()
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
    if member.id in member_ids(db, ledger) + invited_ids(db, ledger):
        raise HTTPException(409, f"{member.username} is already in this shared wallet, or invited to it.")
    db.add(SharedMember(shared_wallet_id=ledger.id, user_id=member.id, pending=True))
    db.commit()
    return summary(db, user, ledger)


@router.delete("/{ledger_id}/members/{user_id}")
def remove_member(ledger_id: int, user_id: int, db: DbSession, user: CurrentUser):
    """The owner can remove anyone else, or take back an invitation; a member can leave. Only once they're settled up."""
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
    db.flush()
    db.delete(settlement)
    db.commit()
    return {"ok": True}
