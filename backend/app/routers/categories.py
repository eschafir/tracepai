from fastapi import APIRouter, HTTPException
from sqlmodel import select

from app.auth import CurrentUser, DbSession
from app.categorize import suggest_category
from app.models import Category, CategoryBase, Kind

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
    db.delete(get_owned(db, user, category_id))
    db.commit()
    return {"ok": True}
