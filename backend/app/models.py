import datetime as dt
from enum import StrEnum

from pydantic import model_validator
from sqlmodel import Field, Relationship, SQLModel


class Kind(StrEnum):
    income = "income"
    expense = "expense"
    transfer = "transfer"


class CategoryKind(StrEnum):
    income = "income"
    expense = "expense"


class WalletKind(StrEnum):
    bank = "bank"
    card = "card"
    cash = "cash"
    savings = "savings"


class Frequency(StrEnum):
    weekly = "weekly"
    monthly = "monthly"
    yearly = "yearly"


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    password_hash: str


class Session(SQLModel, table=True):
    token: str = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.UTC))


class CategoryBase(SQLModel):
    name: str
    color_slot: int = Field(ge=1, le=8)
    kind: CategoryKind = CategoryKind.expense


class Category(CategoryBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)


class WalletBase(SQLModel):
    name: str
    kind: WalletKind = WalletKind.bank
    color_slot: int = Field(ge=1, le=8)
    opening_balance: float = 0


class Wallet(WalletBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)


class WalletOut(WalletBase):
    id: int
    balance: float


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
    kind: Kind = Kind.expense
    merchant: str = ""
    category_id: int | None = Field(default=None, foreign_key="category.id")
    notes: str = ""
    tags: str = ""


def check_transfer(entry: Entry, splits: list | None = None):
    if entry.kind == Kind.transfer:
        if entry.to_wallet_id is None or entry.to_wallet_id == entry.wallet_id:
            raise ValueError("A transfer needs two different wallets")
        if entry.category_id is not None or splits:
            raise ValueError("A transfer can't have a category or splits")
    elif entry.to_wallet_id is not None:
        raise ValueError("Only transfers have a destination wallet")


class TransactionBase(Entry):
    date: dt.date
    receipt_path: str | None = None
    place: str | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    recurring_id: int | None = Field(default=None, foreign_key="recurringrule.id")


class Transaction(TransactionBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    splits: list[Split] = Relationship(
        back_populates="txn", sa_relationship_kwargs={"cascade": "all, delete-orphan", "lazy": "selectin"}
    )


class TransactionIn(TransactionBase):
    splits: list[SplitBase] = []
    repeat: Frequency | None = None

    @model_validator(mode="after")
    def valid_transfer(self):
        check_transfer(self, self.splits)
        return self


class TransactionOut(TransactionBase):
    id: int
    splits: list[SplitBase] = []


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


class GoalBase(SQLModel):
    name: str
    target_amount: float = Field(gt=0)
    target_date: dt.date | None = None
    color_slot: int = Field(default=3, ge=1, le=8)


class Goal(GoalBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)


class ContributionBase(SQLModel):
    date: dt.date
    amount: float
    note: str = ""


class GoalContribution(ContributionBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    goal_id: int = Field(foreign_key="goal.id", index=True, ondelete="CASCADE")
