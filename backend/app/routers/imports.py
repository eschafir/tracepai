import datetime as dt
import json
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal

from fastapi import APIRouter, Form, HTTPException, UploadFile
from pydantic import ValidationError
from sqlmodel import Field, SQLModel, select

from app.auth import CurrentUser, DbSession
from app.categorize import suggest_category
from app.documents import read_upload
from app.importer import guess_date_format, guess_mapping, parse_amount, parse_date, read_csv
from app.models import (
    Budget,
    BudgetBase,
    Category,
    CategoryBase,
    CategoryKind,
    Goal,
    GoalBase,
    Kind,
    RecurringBase,
    RecurringRule,
    Settlement,
    SharePayment,
    SharedWallet,
    Transaction,
    TransactionIn,
    User,
    Wallet,
    WalletBase,
)
from app.routers.recurring import check_rule
from app.routers.settings import LAYOUTS, SettingsIn
from app.routers.transactions import apply
from app.routers.wallets import check_currency
from app.shared import member_ids, my_ledgers, parse_shares, shared_with
from app.storage import is_own_receipt

router = APIRouter(prefix="/import", tags=["import"])


class Mapping(SQLModel):
    date: str
    merchant: str
    amount: str | None = None
    debit: str | None = None
    credit: str | None = None


def load(file: UploadFile) -> tuple[list[str], list[list[str]]]:
    content = read_upload(file)
    try:
        headers, rows = read_csv(content)
    except Exception:
        raise HTTPException(400, "This file doesn't look like a CSV. Export your statement as CSV and try again.")
    if not rows:
        raise HTTPException(400, "The file has a header row but no transactions.")
    return headers, rows


@router.post("/preview")
def preview(file: UploadFile, user: CurrentUser):
    headers, rows = load(file)
    mapping = guess_mapping(headers)
    dates = [row[headers.index(mapping["date"])] for row in rows] if mapping["date"] else []
    return {
        "headers": headers,
        "rows": rows[:5],
        "row_count": len(rows),
        "mapping": mapping,
        "date_format": guess_date_format(dates) or "YYYY-MM-DD",
    }


@router.post("")
def import_csv(
    file: UploadFile,
    db: DbSession,
    user: CurrentUser,
    wallet_id: int = Form(),
    mapping: str = Form(),
    date_format: str = Form("YYYY-MM-DD"),
    expenses_negative: bool = Form(True),
):
    wallet = owned_wallet(db, user, wallet_id)
    columns = Mapping.model_validate(json.loads(mapping))
    headers, rows = load(file)
    index = {h: i for i, h in enumerate(headers)}

    def cell(row: list[str], column: str | None) -> str:
        return row[index[column]] if column in index and index[column] < len(row) else ""

    parsed, errors = [], []
    for number, row in enumerate(rows, start=2):
        try:
            date = parse_date(cell(row, columns.date), date_format)
            merchant = cell(row, columns.merchant).strip()
            if columns.amount:
                signed = parse_amount(cell(row, columns.amount))
                if signed is None:
                    raise ValueError("The amount is empty")
                signed = signed if expenses_negative else -signed
            else:
                debit, credit = parse_amount(cell(row, columns.debit)), parse_amount(cell(row, columns.credit))
                if not debit and not credit:
                    raise ValueError("Both debit and credit are empty")
                signed = abs(credit) if credit else -abs(debit)
            if signed == 0:
                raise ValueError("The amount is zero")
        except ValueError as err:
            errors.append({"row": number, "message": str(err)})
            continue
        kind = Kind.income if signed > 0 else Kind.expense
        parsed.append(ImportRow(date=date, merchant=merchant, amount=abs(signed), kind=kind))
    return save_rows(db, user.id, wallet.id, parsed, errors)


class ImportRow(SQLModel):
    date: dt.date
    merchant: str = ""
    amount: float = Field(gt=0)
    kind: CategoryKind
    category_id: int | None = None
    suggest: bool = True


def save_rows(db: DbSession, user_id: int, wallet_id: int, rows: list[ImportRow], errors: list[dict]) -> dict:
    """Save imported rows, skipping ones already in the wallet and filling in categories."""
    existing = Counter(
        (t.date, round(t.amount, 2), t.merchant)
        for t in db.exec(select(Transaction).where(Transaction.user_id == user_id, Transaction.wallet_id == wallet_id))
    )
    imported, duplicates = 0, 0
    for row in rows:
        key = (row.date, round(row.amount, 2), row.merchant)
        if existing[key]:
            existing[key] -= 1
            duplicates += 1
            continue
        category_id = row.category_id
        if category_id is None and row.suggest:
            suggestion = suggest_category(db, user_id, row.merchant, row.kind)
            category_id = suggestion["category_id"] if suggestion else None
        db.add(
            Transaction(
                user_id=user_id,
                wallet_id=wallet_id,
                date=row.date,
                amount=row.amount,
                kind=row.kind,
                merchant=row.merchant,
                category_id=category_id,
                tags="imported",
            )
        )
        imported += 1
    db.commit()
    return {"imported": imported, "duplicates": duplicates, "errors": errors}


def owned_wallet(db: DbSession, user: CurrentUser, wallet_id: int) -> Wallet:
    wallet = db.get(Wallet, wallet_id)
    if not wallet or wallet.user_id != user.id:
        raise HTTPException(404, "Wallet not found")
    return wallet


@contextmanager
def record(what: str, number: int) -> Iterator[None]:
    """Turns a problem with one record of an uploaded profile into a 400 that names the record."""
    try:
        yield
    except HTTPException as err:
        raise HTTPException(400, f"{what} {number} in the file: {err.detail}")
    except (AttributeError, KeyError, TypeError, ValueError) as err:
        if isinstance(err, ValidationError):
            reason = f"{'.'.join(map(str, err.errors()[0]['loc']))}: {err.errors()[0]['msg']}"
        else:
            reason = f"{err} is missing" if isinstance(err, KeyError) else str(err)
        raise HTTPException(400, f"{what} {number} in the file is invalid ({reason}).")


def records(data: dict, key: str, what: str, model: type[SQLModel]) -> list[tuple[int, dict, SQLModel]]:
    """A section of the profile, each record checked against the model the API uses for it."""
    items = data.get(key) or []
    if not isinstance(items, list):
        raise HTTPException(400, f"The {key} in the file should be a list.")
    out = []
    for number, item in enumerate(items, start=1):
        with record(what, number):
            out.append((number, item, model.model_validate(item)))
    return out


def mapped(ids: dict[int, int], old: int | None, what: str) -> int | None:
    if old is None:
        return None
    if old not in ids:
        raise ValueError(f"it refers to a {what} that isn't in the file")
    return ids[old]


def clear_account(db: DbSession, user: CurrentUser):
    """Deletes the user's records, children first so foreign keys hold."""
    for model in (Transaction, RecurringRule, Budget, Goal, Category, Wallet):
        for row in db.exec(select(model).where(model.user_id == user.id)):
            db.delete(row)
        db.flush()


def restore_sharing(db: DbSession, user: CurrentUser, item: dict) -> dict:
    """The sharing fields of an exported transaction that still hold for this user; the rest are dropped."""
    ledger_id = item.get("shared_wallet_id")
    in_ledger = ledger_id is not None and any(ledger.id == ledger_id for ledger in my_ledgers(db, user.id))
    fractions = parse_shares(item.get("shared_members"))
    people = set(fractions)
    if in_ledger:
        valid = bool(people) and people <= set(member_ids(db, db.get(SharedWallet, ledger_id)))
    else:
        valid = user.id in people and len(people) > 1 and all(db.get(User, uid) for uid in people)
    settlement = db.get(Settlement, item["settlement_id"]) if item.get("settlement_id") else None
    payment = db.get(SharePayment, item["share_payment_id"]) if item.get("share_payment_id") else None
    paid_txn = payment and db.get(Transaction, payment.transaction_id)
    return {
        "shared_wallet_id": ledger_id if in_ledger else None,
        "shares": {uid: round(f * 100, 4) for uid, f in fractions.items()} if valid else None,
        "settlement_id": settlement.id if settlement and user.id in (settlement.from_user_id, settlement.to_user_id) else None,
        "share_payment_id": payment.id if paid_txn and user.id in (payment.user_id, paid_txn.user_id) else None,
    }


@router.post("/profile")
def import_profile(
    file: UploadFile,
    db: DbSession,
    user: CurrentUser,
    mode: Literal["replace", "merge"] = Form("merge"),
):
    """Restores a profile export. Merge adds what isn't in the account yet; replace deletes the account's records first.
    Every record is checked like the API checks it, and nothing is saved unless the whole file is valid."""
    try:
        data = json.loads(read_upload(file))
    except ValueError:
        raise HTTPException(400, "The file could not be read as valid JSON.")
    if not isinstance(data, dict) or "wallets" not in data or "categories" not in data:
        raise HTTPException(400, "The file does not look like a TracepAI profile export.")

    wallets = records(data, "wallets", "Wallet", WalletBase)
    categories = records(data, "categories", "Category", CategoryBase)
    budgets = records(data, "budgets", "Budget", BudgetBase)
    goals = records(data, "goals", "Goal", GoalBase)
    rules = records(data, "recurring_rules", "Recurring item", RecurringBase)
    txns = records(data, "transactions", "Transaction", TransactionIn)
    with record("User settings", 1):
        prefs = data.get("user") or {}
        settings = SettingsIn.model_validate({k: prefs[k].split(",") if k in LAYOUTS else prefs[k] for k in ("budget_style", *LAYOUTS) if k in prefs})
    for number, _, wallet in wallets:
        with record("Wallet", number):
            check_currency(db, wallet)  # may fetch and commit rates, so it runs before anything changes

    if mode == "replace":
        if my_ledgers(db, user.id) or shared_with(db, user.id):
            raise HTTPException(409, "Replace can't be used while you share wallets or expenses with others. Use merge instead.")
    my_receipts = set(db.exec(select(Transaction.receipt_path).where(Transaction.user_id == user.id)))
    if mode == "replace":
        clear_account(db, user)
    added = Counter()

    wallet_ids: dict[int, int] = {}
    existing_wallets = {w.name: w for w in db.exec(select(Wallet).where(Wallet.user_id == user.id))}
    for number, item, data_in in wallets:
        wallet = existing_wallets.get(data_in.name)
        if wallet and wallet.currency != data_in.currency:
            raise HTTPException(
                400, f"Wallet {number} in the file: {wallet.name} is in {wallet.currency} here and in {data_in.currency} in the file."
            )
        if not wallet:
            wallet = Wallet.model_validate(data_in, update={"user_id": user.id})
            db.add(wallet)
            db.flush()
            existing_wallets[wallet.name] = wallet
            added["wallets"] += 1
        wallet_ids[item.get("id")] = wallet.id

    category_ids: dict[int, int] = {}
    existing_categories = {(c.name, c.kind): c for c in db.exec(select(Category).where(Category.user_id == user.id))}
    for _, item, data_in in categories:
        category = existing_categories.get((data_in.name, data_in.kind))
        if not category:
            category = Category.model_validate(data_in, update={"user_id": user.id})
            db.add(category)
            db.flush()
            existing_categories[(category.name, category.kind)] = category
            added["categories"] += 1
        category_ids[item.get("id")] = category.id

    for number, _, data_in in budgets:
        with record("Budget", number):
            category_id = mapped(category_ids, data_in.category_id, "category")
        budget = db.exec(select(Budget).where(Budget.user_id == user.id, Budget.category_id == category_id)).first()
        if budget:
            budget.monthly_limit = data_in.monthly_limit
        else:
            db.add(Budget(user_id=user.id, category_id=category_id, monthly_limit=data_in.monthly_limit))
        added["budgets"] += 1

    goal_ids: dict[int, int] = {}
    existing_goals = {g.name: g for g in db.exec(select(Goal).where(Goal.user_id == user.id))}
    for number, item, data_in in goals:
        with record("Goal", number):
            data_in.wallet_id = mapped(wallet_ids, data_in.wallet_id, "wallet")
        goal = existing_goals.get(data_in.name)
        if not goal:
            goal = Goal.model_validate(data_in, update={"user_id": user.id})
            db.add(goal)
            db.flush()
            added["goals"] += 1
        goal_ids[item.get("id")] = goal.id

    def rule_key(rule: RecurringBase) -> tuple:
        return (rule.wallet_id, rule.to_wallet_id, rule.kind, rule.merchant, rule.frequency)

    rule_ids: dict[int, int] = {}
    existing_rules = {rule_key(r): r for r in db.exec(select(RecurringRule).where(RecurringRule.user_id == user.id))}
    for number, item, data_in in rules:
        with record("Recurring item", number):
            data_in = RecurringBase.model_validate(
                data_in.model_dump()
                | {
                    "wallet_id": mapped(wallet_ids, data_in.wallet_id, "wallet"),
                    "to_wallet_id": mapped(wallet_ids, data_in.to_wallet_id, "wallet"),
                    "category_id": mapped(category_ids, data_in.category_id, "category"),
                    "goal_id": mapped(goal_ids, data_in.goal_id, "goal"),
                }
            )
            check_rule(db, user, data_in)
            price_seen = float(item["price_seen"]) if item.get("price_seen") is not None else None
        rule = existing_rules.get(rule_key(data_in))
        if not rule:
            rule = RecurringRule.model_validate(data_in, update={"user_id": user.id, "price_seen": price_seen})
            db.add(rule)
            db.flush()
            existing_rules[rule_key(rule)] = rule
            added["recurring_rules"] += 1
        rule_ids[item.get("id")] = rule.id

    def txn_key(t: Transaction | TransactionIn) -> tuple:
        return (t.wallet_id, t.date, round(t.amount, 2), t.merchant, t.kind)

    existing_txns = Counter(txn_key(t) for t in db.exec(select(Transaction).where(Transaction.user_id == user.id)))
    for number, item, data_in in txns:
        with record("Transaction", number):
            sharing = restore_sharing(db, user, item)
            ledger = db.get(SharedWallet, sharing["shared_wallet_id"]) if sharing["shared_wallet_id"] else None

            def category(old: int | None) -> int | None:
                if ledger and ledger.owner_id != user.id:  # a shared wallet's expenses use its owner's categories
                    found = db.get(Category, old) if old is not None else None
                    return old if found and found.user_id == ledger.owner_id else None
                return mapped(category_ids, old, "category")

            data_in = TransactionIn.model_validate(
                data_in.model_dump(exclude={"shares", "repeat", "shared_wallet_id"})
                | {
                    "wallet_id": mapped(wallet_ids, data_in.wallet_id, "wallet"),
                    "to_wallet_id": mapped(wallet_ids, data_in.to_wallet_id, "wallet"),
                    "category_id": category(data_in.category_id),
                    "splits": [{"category_id": c, "amount": s.amount} for s in data_in.splits if (c := category(s.category_id))],
                    "goal_id": mapped(goal_ids, data_in.goal_id, "goal"),
                    "receipt_path": None,  # set below: a receipt this account had before a replace is allowed too
                    "shared_wallet_id": sharing["shared_wallet_id"],
                    "shares": sharing["shares"],
                }
            )
            if existing_txns[txn_key(data_in)]:  # already in the account
                existing_txns[txn_key(data_in)] -= 1
                continue
            txn = Transaction(user_id=user.id, date=data_in.date, amount=data_in.amount, wallet_id=data_in.wallet_id)
            apply(db, user, txn, data_in)
            receipt = item.get("receipt_path")
            txn.receipt_path = receipt if receipt and (is_own_receipt(user.id, receipt) or receipt in my_receipts) else None
            txn.recurring_id = rule_ids.get(item.get("recurring_id"))
            txn.settlement_id = sharing["settlement_id"]
            txn.share_payment_id = sharing["share_payment_id"]
        db.add(txn)
        added["transactions"] += 1

    for key, value in settings.model_dump(exclude_none=True).items():
        setattr(user, key, ",".join(value) if key in LAYOUTS else value)
    db.add(user)
    db.commit()
    return {"ok": True, "imported": {key: added[key] for key in ("wallets", "categories", "budgets", "goals", "recurring_rules", "transactions")}}
