import datetime as dt
import json
from collections import Counter

from typing import Literal

from fastapi import APIRouter, Form, HTTPException, UploadFile
from sqlmodel import Field, SQLModel, select

from app.auth import CurrentUser, DbSession
from app.categorize import suggest_category
from app.importer import guess_date_format, guess_mapping, parse_amount, parse_date, read_csv
from app.models import Budget, Category, CategoryKind, Goal, Kind, RecurringRule, Split, Transaction, Wallet

router = APIRouter(prefix="/import", tags=["import"])


class Mapping(SQLModel):
    date: str
    merchant: str
    amount: str | None = None
    debit: str | None = None
    credit: str | None = None


def load(file: UploadFile) -> tuple[list[str], list[list[str]]]:
    try:
        headers, rows = read_csv(file.file.read())
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


@router.post("/profile")
def import_profile(
    file: UploadFile,
    db: DbSession,
    user: CurrentUser,
    mode: Literal["replace", "merge"] = Form("replace"),
):
    try:
        raw = file.file.read()
        data = json.loads(raw)
    except Exception:
        raise HTTPException(400, "The file could not be read as valid JSON.")

    if not isinstance(data, dict) or "wallets" not in data or "categories" not in data:
        raise HTTPException(400, "The file does not look like a TracepAI profile export.")

    if mode == "replace":
        user_txn_ids = [t.id for t in db.exec(select(Transaction.id).where(Transaction.user_id == user.id)).all()]
        if user_txn_ids:
            for tid in user_txn_ids:
                for s in db.exec(select(Split).where(Split.transaction_id == tid)).all():
                    db.delete(s)
            for t in db.exec(select(Transaction).where(Transaction.user_id == user.id)).all():
                db.delete(t)
        for r in db.exec(select(RecurringRule).where(RecurringRule.user_id == user.id)).all():
            db.delete(r)
        for b in db.exec(select(Budget).where(Budget.user_id == user.id)).all():
            db.delete(b)
        for g in db.exec(select(Goal).where(Goal.user_id == user.id)).all():
            db.delete(g)
        for c in db.exec(select(Category).where(Category.user_id == user.id)).all():
            db.delete(c)
        for w in db.exec(select(Wallet).where(Wallet.user_id == user.id)).all():
            db.delete(w)
        db.flush()

    wallet_map: dict[int, int] = {}
    existing_wallets = {w.name: w for w in db.exec(select(Wallet).where(Wallet.user_id == user.id)).all()}
    for w in data.get("wallets", []):
        old_id = w.get("id")
        if mode == "merge" and w.get("name") in existing_wallets:
            existing = existing_wallets[w["name"]]
            if old_id is not None:
                wallet_map[old_id] = existing.id
        else:
            new_wallet = Wallet(
                user_id=user.id,
                name=w["name"],
                kind=w.get("kind", "bank"),
                color_slot=w.get("color_slot", 1),
                opening_balance=w.get("opening_balance", 0.0),
                currency=w.get("currency", "USD"),
            )
            db.add(new_wallet)
            db.flush()
            if old_id is not None:
                wallet_map[old_id] = new_wallet.id
            existing_wallets[new_wallet.name] = new_wallet

    category_map: dict[int, int] = {}
    existing_cats = {(c.name, str(c.kind)): c for c in db.exec(select(Category).where(Category.user_id == user.id)).all()}
    for c in data.get("categories", []):
        old_id = c.get("id")
        key = (c["name"], str(c.get("kind", "expense")))
        if mode == "merge" and key in existing_cats:
            existing = existing_cats[key]
            if old_id is not None:
                category_map[old_id] = existing.id
        else:
            new_cat = Category(
                user_id=user.id,
                name=c["name"],
                color_slot=c.get("color_slot", 1),
                kind=c.get("kind", "expense"),
                budget_group=c.get("budget_group"),
            )
            db.add(new_cat)
            db.flush()
            if old_id is not None:
                category_map[old_id] = new_cat.id
            existing_cats[key] = new_cat

    budget_count = 0
    for b in data.get("budgets", []):
        cat_id = category_map.get(b.get("category_id"))
        if cat_id:
            existing_b = db.exec(select(Budget).where(Budget.user_id == user.id, Budget.category_id == cat_id)).first()
            if existing_b:
                existing_b.monthly_limit = b.get("monthly_limit", existing_b.monthly_limit)
                db.add(existing_b)
            else:
                db.add(Budget(user_id=user.id, category_id=cat_id, monthly_limit=b["monthly_limit"]))
            budget_count += 1

    goal_map: dict[int, int] = {}
    for g in data.get("goals", []):
        old_id = g.get("id")
        w_id = wallet_map.get(g.get("wallet_id"))
        t_date = dt.date.fromisoformat(g["target_date"]) if g.get("target_date") else None
        new_goal = Goal(
            user_id=user.id,
            name=g["name"],
            target_amount=g["target_amount"],
            target_date=t_date,
            color_slot=g.get("color_slot", 3),
            wallet_id=w_id,
        )
        db.add(new_goal)
        db.flush()
        if old_id is not None:
            goal_map[old_id] = new_goal.id

    rule_map: dict[int, int] = {}
    for r in data.get("recurring_rules", []):
        old_id = r.get("id")
        w_id = wallet_map.get(r.get("wallet_id"))
        if not w_id:
            continue
        to_w_id = wallet_map.get(r.get("to_wallet_id"))
        cat_id = category_map.get(r.get("category_id"))
        g_id = goal_map.get(r.get("goal_id"))
        n_date = dt.date.fromisoformat(r["next_date"]) if r.get("next_date") else dt.date.today()
        new_rule = RecurringRule(
            user_id=user.id,
            wallet_id=w_id,
            to_wallet_id=to_w_id,
            amount=r["amount"],
            to_amount=r.get("to_amount"),
            kind=r.get("kind", "expense"),
            merchant=r.get("merchant", ""),
            category_id=cat_id,
            frequency=r.get("frequency", "monthly"),
            next_date=n_date,
            notes=r.get("notes", ""),
            tags=r.get("tags", ""),
            goal_id=g_id,
            price_seen=r.get("price_seen"),
        )
        db.add(new_rule)
        db.flush()
        if old_id is not None:
            rule_map[old_id] = new_rule.id

    txns_count = 0
    for t in data.get("transactions", []):
        w_id = wallet_map.get(t.get("wallet_id"))
        if not w_id:
            continue
        to_w_id = wallet_map.get(t.get("to_wallet_id"))
        cat_id = category_map.get(t.get("category_id"))
        g_id = goal_map.get(t.get("goal_id"))
        r_id = rule_map.get(t.get("recurring_id"))
        t_date = dt.date.fromisoformat(t["date"]) if t.get("date") else dt.date.today()

        splits = [
            Split(category_id=category_map[s["category_id"]], amount=s["amount"])
            for s in t.get("splits", [])
            if s.get("category_id") in category_map
        ]
        new_txn = Transaction(
            user_id=user.id,
            wallet_id=w_id,
            to_wallet_id=to_w_id,
            amount=t["amount"],
            to_amount=t.get("to_amount"),
            kind=t.get("kind", "expense"),
            merchant=t.get("merchant", ""),
            category_id=cat_id,
            date=t_date,
            notes=t.get("notes", ""),
            tags=t.get("tags", ""),
            receipt_path=t.get("receipt_path"),
            place=t.get("place"),
            lat=t.get("lat"),
            lng=t.get("lng"),
            goal_id=g_id,
            recurring_id=r_id,
            splits=splits,
        )
        db.add(new_txn)
        txns_count += 1

    u_pref = data.get("user", {})
    if "budget_style" in u_pref:
        user.budget_style = u_pref["budget_style"]
    if "overview_layout" in u_pref:
        user.overview_layout = u_pref["overview_layout"]
    if "year_layout" in u_pref:
        user.year_layout = u_pref["year_layout"]
    db.add(user)

    db.commit()
    return {
        "ok": True,
        "imported": {
            "wallets": len(wallet_map),
            "categories": len(category_map),
            "budgets": budget_count,
            "goals": len(goal_map),
            "recurring_rules": len(rule_map),
            "transactions": txns_count,
        },
    }

