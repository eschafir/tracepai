import datetime as dt
from enum import StrEnum
from typing import Literal

from pydantic import model_validator
from sqlmodel import Field, Relationship, SQLModel


class Kind(StrEnum):
    income = "income"
    expense = "expense"
    transfer = "transfer"


class CategoryKind(StrEnum):
    income = "income"
    expense = "expense"


class BudgetGroup(StrEnum):
    need = "need"
    want = "want"
    savings = "savings"


class WalletKind(StrEnum):
    bank = "bank"
    card = "card"
    cash = "cash"
    savings = "savings"


class Frequency(StrEnum):
    weekly = "weekly"
    monthly = "monthly"
    yearly = "yearly"


class FxRate(SQLModel, table=True):
    currency: str = Field(primary_key=True)
    date: dt.date = Field(primary_key=True)
    per_usd: float  # units of the currency per 1 USD


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    password_hash: str
    budget_style: str = "limits"  # limits, zero_based or 50_30_20


class Session(SQLModel, table=True):
    token: str = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.UTC))


class CategoryBase(SQLModel):
    name: str
    color_slot: int = Field(ge=1, le=8)
    kind: CategoryKind = CategoryKind.expense
    budget_group: BudgetGroup | None = None  # for 50/30/20 budgets


class Category(CategoryBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)


class WalletBase(SQLModel):
    name: str
    kind: WalletKind = WalletKind.bank
    color_slot: int = Field(ge=1, le=8)
    opening_balance: float = 0
    currency: str = Field(default="USD", min_length=3, max_length=3)


class Wallet(WalletBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)


class WalletOut(WalletBase):
    id: int
    balance: float
    balance_usd: float
    in_use: bool  # has transactions, so its currency is locked


class SplitBase(SQLModel):
    category_id: int = Field(foreign_key="category.id")
    amount: float = Field(gt=0)


class Split(SplitBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    transaction_id: int = Field(foreign_key="transaction.id", index=True, ondelete="CASCADE")
    txn: "Transaction" = Relationship(back_populates="splits")


class Entry(SQLModel):
    """Fields shared by transactions and the recurring rules that create them."""

    wallet_id: int = Field(foreign_key="wallet.id", index=True)
    to_wallet_id: int | None = Field(default=None, foreign_key="wallet.id")
    amount: float = Field(gt=0)
    to_amount: float | None = Field(default=None, gt=0)  # received, in the destination wallet's currency
    kind: Kind = Kind.expense
    merchant: str = ""
    category_id: int | None = Field(default=None, foreign_key="category.id")
    notes: str = ""
    tags: str = ""
    goal_id: int | None = Field(default=None, foreign_key="goal.id")  # a transfer into or out of a savings goal


def check_transfer(entry: Entry, splits: list | None = None):
    if entry.kind == Kind.transfer:
        if entry.to_wallet_id is None or entry.to_wallet_id == entry.wallet_id:
            raise ValueError("A transfer needs two different wallets")
        if entry.category_id is not None or splits:
            raise ValueError("A transfer can't have a category or splits")
    elif entry.to_wallet_id is not None or entry.to_amount is not None:
        raise ValueError("Only transfers have a destination wallet")


class SharedWalletBase(SQLModel):
    name: str
    currency: str = Field(default="USD", min_length=3, max_length=3)
    color_slot: int = Field(default=2, ge=1, le=8)


class SharedWallet(SharedWalletBase, table=True):
    """A ledger of expenses split equally between its members. Money stays in each member's own wallets."""

    id: int | None = Field(default=None, primary_key=True)
    owner_id: int = Field(foreign_key="user.id", index=True)


class SharedMember(SQLModel, table=True):
    shared_wallet_id: int = Field(foreign_key="sharedwallet.id", primary_key=True)
    user_id: int = Field(foreign_key="user.id", primary_key=True)


class Settlement(SQLModel, table=True):
    """A payment between two members that evens out the shared ledger, in the ledger's currency."""

    id: int | None = Field(default=None, primary_key=True)
    shared_wallet_id: int = Field(foreign_key="sharedwallet.id", index=True)
    from_user_id: int = Field(foreign_key="user.id")
    to_user_id: int = Field(foreign_key="user.id")
    amount: float = Field(gt=0)
    date: dt.date


class TransactionBase(Entry):
    date: dt.date
    receipt_path: str | None = None
    place: str | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    recurring_id: int | None = Field(default=None, foreign_key="recurringrule.id")
    shared_wallet_id: int | None = Field(default=None, foreign_key="sharedwallet.id")  # an expense split in a shared wallet


class Transaction(TransactionBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    shared_members: str | None = None  # who shares this expense and their percent, fixed when shared: "1:60,4:40"
    settlement_id: int | None = Field(default=None, foreign_key="settlement.id")  # money moved to settle up, not spending
    splits: list[Split] = Relationship(
        back_populates="txn", sa_relationship_kwargs={"cascade": "all, delete-orphan", "lazy": "selectin"}
    )


class TransactionIn(TransactionBase):
    splits: list[SplitBase] = []
    shares: dict[int, float] | None = None  # shared expenses: percent per user id, adding up to 100
    repeat: Frequency | None = None

    @model_validator(mode="after")
    def valid_transfer(self):
        check_transfer(self, self.splits)
        return self


class TransactionOut(TransactionBase):
    id: int
    splits: list[SplitBase] = []
    shared_members: str | None = None
    settlement_id: int | None = None


class BudgetBase(SQLModel):
    category_id: int = Field(foreign_key="category.id")
    monthly_limit: float = Field(gt=0)


class Budget(BudgetBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)


class RecurringBase(Entry):
    frequency: Frequency = Frequency.monthly
    next_date: dt.date

    @model_validator(mode="after")
    def valid_transfer(self):
        check_transfer(self)
        return self


class RecurringRule(RecurringBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    price_seen: float | None = None  # a changed charge the user chose to keep the old amount for


class GoalBase(SQLModel):
    name: str
    target_amount: float = Field(gt=0)
    target_date: dt.date | None = None
    color_slot: int = Field(default=3, ge=1, le=8)
    wallet_id: int | None = Field(default=None, foreign_key="wallet.id")


class Goal(GoalBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)


class ContributionIn(SQLModel):
    """Money added to a goal ("in", from wallet_id) or taken out of it ("out", to wallet_id)."""

    date: dt.date
    amount: float = Field(gt=0)
    direction: Literal["in", "out"]
    wallet_id: int
    note: str = ""
    received: float | None = Field(default=None, gt=0)  # in the destination wallet's currency, when it differs
    repeat: Literal["monthly"] | None = None  # adding only: also add this amount every month
