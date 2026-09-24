import datetime as dt

from fastapi import APIRouter, HTTPException
from sqlmodel import col, select

from app.auth import CurrentUser, DbSession
from app.models import RecurringBase, RecurringRule
from app.recurring import advance, post_due, suggestions

router = APIRouter(prefix="/recurring", tags=["recurring"])


def get_owned(db: DbSession, user: CurrentUser, rule_id: int) -> RecurringRule:
    rule = db.get(RecurringRule, rule_id)
    if not rule or rule.user_id != user.id:
        raise HTTPException(404, "Recurring item not found")
    return rule


@router.get("")
def list_rules(db: DbSession, user: CurrentUser) -> list[RecurringRule]:
    post_due(db, user.id)
    return db.exec(select(RecurringRule).where(RecurringRule.user_id == user.id).order_by(col(RecurringRule.next_date))).all()


@router.get("/upcoming")
def upcoming(db: DbSession, user: CurrentUser, days: int = 14):
    post_due(db, user.id)
    until = dt.date.today() + dt.timedelta(days=days)
    items = []
    for rule in db.exec(select(RecurringRule).where(RecurringRule.user_id == user.id, RecurringRule.next_date <= until)):
        date = rule.next_date
        while date <= until:
            items.append({"rule_id": rule.id, "date": date, **rule.model_dump(include={"merchant", "amount", "kind", "wallet_id", "to_wallet_id"})})
            date = advance(date, rule.frequency)
    return sorted(items, key=lambda i: i["date"])


@router.get("/suggestions")
def list_suggestions(db: DbSession, user: CurrentUser):
    return suggestions(db, user.id)


@router.post("")
def create_rule(data: RecurringBase, db: DbSession, user: CurrentUser) -> RecurringRule:
    rule = RecurringRule.model_validate(data, update={"user_id": user.id})
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.put("/{rule_id}")
def update_rule(rule_id: int, data: RecurringBase, db: DbSession, user: CurrentUser) -> RecurringRule:
    rule = get_owned(db, user, rule_id)
    rule.sqlmodel_update(data.model_dump())
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, db: DbSession, user: CurrentUser):
    db.delete(get_owned(db, user, rule_id))
    db.commit()
    return {"ok": True}
