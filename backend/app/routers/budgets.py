from fastapi import APIRouter, HTTPException
from sqlmodel import select

from app.auth import CurrentUser, DbSession, check_owned
from app.models import Budget, BudgetBase, Category

router = APIRouter(prefix="/budgets", tags=["budgets"])


def get_owned(db: DbSession, user: CurrentUser, budget_id: int) -> Budget:
    budget = db.get(Budget, budget_id)
    if not budget or budget.user_id != user.id:
        raise HTTPException(404, "Budget not found")
    return budget


@router.get("")
def list_budgets(db: DbSession, user: CurrentUser) -> list[Budget]:
    return db.exec(select(Budget).where(Budget.user_id == user.id).order_by(Budget.id)).all()


@router.post("")
def create_budget(data: BudgetBase, db: DbSession, user: CurrentUser) -> Budget:
    check_owned(db, Category, user.id, data.category_id)
    budget = Budget.model_validate(data, update={"user_id": user.id})
    db.add(budget)
    db.commit()
    db.refresh(budget)
    return budget


@router.put("/{budget_id}")
def update_budget(budget_id: int, data: BudgetBase, db: DbSession, user: CurrentUser) -> Budget:
    budget = get_owned(db, user, budget_id)
    check_owned(db, Category, user.id, data.category_id)
    budget.sqlmodel_update(data.model_dump())
    db.commit()
    db.refresh(budget)
    return budget


@router.delete("/{budget_id}")
def delete_budget(budget_id: int, db: DbSession, user: CurrentUser):
    db.delete(get_owned(db, user, budget_id))
    db.commit()
    return {"ok": True}
