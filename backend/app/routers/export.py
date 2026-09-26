import csv
import io
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response
from sqlmodel import select

from app.auth import CurrentUser, DbSession
from app.models import Category, TransactionOut, Wallet
from app.routers.transactions import query_transactions

router = APIRouter(prefix="/export", tags=["export"])

COLUMNS = ["id", "date", "kind", "amount", "currency", "to_amount", "merchant", "category", "wallet", "to_wallet", "tags", "notes"]


@router.get("")
def export(db: DbSession, user: CurrentUser, format: Literal["csv", "json"] = "csv"):
    names = {c.id: c.name for c in db.exec(select(Category).where(Category.user_id == user.id))}
    wallets = {w.id: w for w in db.exec(select(Wallet).where(Wallet.user_id == user.id))}
    rows = []
    for txn in query_transactions(db, user):
        row = TransactionOut.model_validate(txn).model_dump(mode="json")
        parts = [(s.category_id, s.amount) for s in txn.splits] or [(txn.category_id, txn.amount)]
        row["category"] = "; ".join(f"{names.get(c, '')}: {a}" if txn.splits else names.get(c, "") for c, a in parts)
        row["wallet"] = wallets[txn.wallet_id].name
        row["currency"] = wallets[txn.wallet_id].currency
        row["to_wallet"] = wallets[txn.to_wallet_id].name if txn.to_wallet_id else ""
        rows.append(row)
    headers = {"Content-Disposition": f"attachment; filename=tracepai-transactions.{format}"}
    if format == "json":
        return JSONResponse(rows, headers=headers)
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=COLUMNS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return Response(out.getvalue(), media_type="text/csv", headers=headers)
