from fastapi import APIRouter, HTTPException
from sqlmodel import col, or_, select

from app.auth import CurrentUser, DbSession
from app.categorize import suggest_category
from app.models import Budget, Category, CategoryBase, Kind, RecurringRule, Split, Transaction

router = APIRouter(prefix="/categories", tags=["categories"])


def get_owned(db: DbSession, user: CurrentUser, category_id: int) -> Category:
    category = db.get(Category, category_id)
    if not category or category.user_id != user.id:
        raise HTTPException(404, "Category not found")
    return category


@router.get("")
def list_categories(db: DbSession, user: CurrentUser) -> list[Category]:
    return db.exec(select(Category).where(Category.user_id == user.id).order_by(Category.id)).all()


@router.get("/suggest")
def suggest(merchant: str, db: DbSession, user: CurrentUser, kind: Kind = Kind.expense):
    return suggest_category(db, user.id, merchant, kind)


@router.post("")
def create_category(data: CategoryBase, db: DbSession, user: CurrentUser) -> Category:
    category = Category.model_validate(data, update={"user_id": user.id})
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.put("/{category_id}")
def update_category(category_id: int, data: CategoryBase, db: DbSession, user: CurrentUser) -> Category:
    category = get_owned(db, user, category_id)
    category.sqlmodel_update(data.model_dump())
    db.commit()
    db.refresh(category)
    return category


@router.delete("/{category_id}")
def delete_category(category_id: int, db: DbSession, user: CurrentUser):
    """Only an unused category can go; its budget goes with it."""
    category = get_owned(db, user, category_id)
    split_txns = select(Split.transaction_id).where(Split.category_id == category_id)
    in_use = [
        select(Transaction).where(or_(Transaction.category_id == category_id, col(Transaction.id).in_(split_txns))),
        select(RecurringRule).where(RecurringRule.category_id == category_id),
    ]
    if any(db.exec(stmt).first() for stmt in in_use):
        raise HTTPException(409, f"{category.name} is used by transactions or recurring items. Change their category first.")
    for budget in db.exec(select(Budget).where(Budget.category_id == category_id)):
        db.delete(budget)
    db.flush()
    db.delete(category)
    db.commit()
    return {"ok": True}
