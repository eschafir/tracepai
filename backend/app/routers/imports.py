import json
from collections import Counter

from fastapi import APIRouter, Form, HTTPException, UploadFile
from sqlmodel import SQLModel, select

from app.auth import CurrentUser, DbSession
from app.categorize import suggest_category
from app.importer import guess_date_format, guess_mapping, parse_amount, parse_date, read_csv
from app.models import Kind, Transaction, Wallet

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
    wallet = db.get(Wallet, wallet_id)
    if not wallet or wallet.user_id != user.id:
        raise HTTPException(404, "Wallet not found")
    columns = Mapping.model_validate(json.loads(mapping))
    headers, rows = load(file)
    index = {h: i for i, h in enumerate(headers)}
    existing = Counter(
        (t.date, round(t.amount, 2), t.merchant)
        for t in db.exec(select(Transaction).where(Transaction.user_id == user.id, Transaction.wallet_id == wallet_id))
    )

    def cell(row: list[str], column: str | None) -> str:
        return row[index[column]] if column in index and index[column] < len(row) else ""

    imported, duplicates, errors = 0, 0, []
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
        key = (date, round(abs(signed), 2), merchant)
        if existing[key]:
            existing[key] -= 1
            duplicates += 1
            continue
        suggestion = suggest_category(db, user.id, merchant, kind)
        db.add(
            Transaction(
                user_id=user.id,
                wallet_id=wallet_id,
                date=date,
                amount=abs(signed),
                kind=kind,
                merchant=merchant,
                category_id=suggestion["category_id"] if suggestion else None,
                tags="imported",
            )
        )
        imported += 1
    db.commit()
    return {"imported": imported, "duplicates": duplicates, "errors": errors}
