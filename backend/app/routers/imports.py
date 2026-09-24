import datetime as dt
import json
from collections import Counter

from fastapi import APIRouter, Form, HTTPException, UploadFile
from sqlmodel import Field, SQLModel, select

from app import vision
from app.auth import CurrentUser, DbSession
from app.categorize import suggest_category
from app.documents import to_images
from app.importer import guess_date_format, guess_mapping, parse_amount, parse_date, read_csv
from app.models import CategoryKind, Kind, Transaction, Wallet

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


@router.post("/document/preview")
def preview_document(file: UploadFile, db: DbSession, user: CurrentUser):
    extraction = vision.read_pages(to_images(file.file.read()))
    rows = []
    for row in extraction.transactions:
        suggestion = suggest_category(db, user.id, row.merchant, row.kind)
        rows.append({**row.model_dump(), "category_id": suggestion["category_id"] if suggestion else None})
    return {"document_type": extraction.document_type, "transactions": rows}


class DocumentRow(SQLModel):
    date: dt.date | None
    merchant: str = ""
    amount: float
    kind: CategoryKind
    category_id: int | None = None


class DocumentImport(SQLModel):
    wallet_id: int
    transactions: list[DocumentRow]


@router.post("/document")
def import_document(data: DocumentImport, db: DbSession, user: CurrentUser):
    wallet = owned_wallet(db, user, data.wallet_id)
    rows, errors = [], []
    for number, row in enumerate(data.transactions, start=1):
        if row.date is None:
            errors.append({"row": number, "message": "The date is missing"})
        elif row.amount <= 0:
            errors.append({"row": number, "message": "The amount must be more than zero"})
        else:
            rows.append(ImportRow(**row.model_dump(), suggest=False))
    return save_rows(db, user.id, wallet.id, rows, errors)
