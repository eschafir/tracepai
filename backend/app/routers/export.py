import csv
import datetime as dt
import io
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response
from sqlmodel import select

from app.auth import CurrentUser, DbSession
from app.models import Budget, Category, Goal, RecurringRule, Transaction, TransactionOut, Wallet
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


@router.get("/profile")
def export_profile(db: DbSession, user: CurrentUser):
    categories = [
        {
            "id": c.id,
            "name": c.name,
            "color_slot": c.color_slot,
            "kind": c.kind.value if hasattr(c.kind, "value") else str(c.kind),
            "budget_group": c.budget_group.value if c.budget_group and hasattr(c.budget_group, "value") else c.budget_group,
        }
        for c in db.exec(select(Category).where(Category.user_id == user.id).order_by(Category.id))
    ]
    wallets = [
        {
            "id": w.id,
            "name": w.name,
            "kind": w.kind.value if hasattr(w.kind, "value") else str(w.kind),
            "color_slot": w.color_slot,
            "opening_balance": w.opening_balance,
            "currency": w.currency,
        }
        for w in db.exec(select(Wallet).where(Wallet.user_id == user.id).order_by(Wallet.id))
    ]
    budgets = [
        {
            "category_id": b.category_id,
            "monthly_limit": b.monthly_limit,
        }
        for b in db.exec(select(Budget).where(Budget.user_id == user.id))
    ]
    goals = [
        {
            "id": g.id,
            "name": g.name,
            "target_amount": g.target_amount,
            "target_date": g.target_date.isoformat() if g.target_date else None,
            "color_slot": g.color_slot,
            "wallet_id": g.wallet_id,
        }
        for g in db.exec(select(Goal).where(Goal.user_id == user.id).order_by(Goal.id))
    ]
    rules = [
        {
            "id": r.id,
            "kind": r.kind.value if hasattr(r.kind, "value") else str(r.kind),
            "amount": r.amount,
            "merchant": r.merchant,
            "wallet_id": r.wallet_id,
            "to_wallet_id": r.to_wallet_id,
            "to_amount": r.to_amount,
            "category_id": r.category_id,
            "frequency": r.frequency.value if hasattr(r.frequency, "value") else str(r.frequency),
            "next_date": r.next_date.isoformat(),
            "notes": r.notes,
            "tags": r.tags,
            "goal_id": r.goal_id,
            "price_seen": r.price_seen,
        }
        for r in db.exec(select(RecurringRule).where(RecurringRule.user_id == user.id).order_by(RecurringRule.id))
    ]
    user_txns = db.exec(
        select(Transaction).where(Transaction.user_id == user.id).order_by(Transaction.date, Transaction.id)
    ).all()
    txns = []
    for t in user_txns:
        txns.append({
            "id": t.id,
            "date": t.date.isoformat(),
            "kind": t.kind.value if hasattr(t.kind, "value") else str(t.kind),
            "amount": t.amount,
            "merchant": t.merchant,
            "wallet_id": t.wallet_id,
            "to_wallet_id": t.to_wallet_id,
            "to_amount": t.to_amount,
            "category_id": t.category_id,
            "notes": t.notes,
            "tags": t.tags,
            "receipt_path": t.receipt_path,
            "place": t.place,
            "lat": t.lat,
            "lng": t.lng,
            "goal_id": t.goal_id,
            "recurring_id": t.recurring_id,
            "shared_wallet_id": t.shared_wallet_id,
            "shared_members": t.shared_members,
            "settlement_id": t.settlement_id,
            "share_payment_id": t.share_payment_id,
            "splits": [{"category_id": s.category_id, "amount": s.amount} for s in t.splits],
        })

    payload = {
        "version": 1,
        "exported_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "user": {
            "budget_style": user.budget_style,
            "overview_layout": user.overview_layout,
            "year_layout": user.year_layout,
        },
        "wallets": wallets,
        "categories": categories,
        "budgets": budgets,
        "goals": goals,
        "recurring_rules": rules,
        "transactions": txns,
    }
    headers = {"Content-Disposition": f"attachment; filename=tracepai-profile-{user.username}.json"}
    return JSONResponse(payload, headers=headers)

