import datetime as dt
import math

from fastapi import APIRouter, HTTPException
from sqlmodel import col, delete, func, select

from app.auth import CurrentUser, DbSession
from app.models import ContributionBase, Goal, GoalBase, GoalContribution

router = APIRouter(prefix="/goals", tags=["goals"])


def get_owned(db: DbSession, user: CurrentUser, goal_id: int) -> Goal:
    goal = db.get(Goal, goal_id)
    if not goal or goal.user_id != user.id:
        raise HTTPException(404, "Goal not found")
    return goal


def months_until(target: dt.date, today: dt.date) -> int:
    """Whole months between today and the target date, and never less than 1."""
    months = (target.year - today.year) * 12 + target.month - today.month - (1 if target.day < today.day else 0)
    return max(1, months)


def progress(db: DbSession, goal: Goal, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    saved = db.exec(select(func.coalesce(func.sum(GoalContribution.amount), 0)).where(GoalContribution.goal_id == goal.id)).one()
    saved = round(saved, 2)
    remaining = round(max(goal.target_amount - saved, 0), 2)
    months = months_until(goal.target_date, today) if goal.target_date else None
    return {
        **goal.model_dump(),
        "saved": saved,
        "percent": round(100 * saved / goal.target_amount, 1),
        "remaining": remaining,
        "months_left": months,
        "monthly_needed": round(remaining / months, 2) if months and remaining else None,
    }


@router.get("")
def list_goals(db: DbSession, user: CurrentUser):
    goals = db.exec(select(Goal).where(Goal.user_id == user.id).order_by(Goal.id)).all()
    return [progress(db, g) for g in goals]


@router.post("")
def create_goal(data: GoalBase, db: DbSession, user: CurrentUser):
    goal = Goal.model_validate(data, update={"user_id": user.id})
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return progress(db, goal)


@router.put("/{goal_id}")
def update_goal(goal_id: int, data: GoalBase, db: DbSession, user: CurrentUser):
    goal = get_owned(db, user, goal_id)
    goal.sqlmodel_update(data.model_dump())
    db.commit()
    db.refresh(goal)
    return progress(db, goal)


@router.delete("/{goal_id}")
def delete_goal(goal_id: int, db: DbSession, user: CurrentUser):
    goal = get_owned(db, user, goal_id)
    db.exec(delete(GoalContribution).where(GoalContribution.goal_id == goal.id))
    db.delete(goal)
    db.commit()
    return {"ok": True}


@router.get("/{goal_id}/contributions")
def list_contributions(goal_id: int, db: DbSession, user: CurrentUser) -> list[GoalContribution]:
    get_owned(db, user, goal_id)
    stmt = select(GoalContribution).where(GoalContribution.goal_id == goal_id)
    return db.exec(stmt.order_by(col(GoalContribution.date).desc(), col(GoalContribution.id).desc())).all()


@router.post("/{goal_id}/contributions")
def add_contribution(goal_id: int, data: ContributionBase, db: DbSession, user: CurrentUser):
    goal = get_owned(db, user, goal_id)
    if data.amount == 0 or not math.isfinite(data.amount):
        raise HTTPException(422, "Enter an amount to add or take out.")
    db.add(GoalContribution.model_validate(data, update={"goal_id": goal.id}))
    db.commit()
    return progress(db, goal)


@router.delete("/contributions/{contribution_id}")
def delete_contribution(contribution_id: int, db: DbSession, user: CurrentUser):
    contribution = db.get(GoalContribution, contribution_id)
    if not contribution:
        raise HTTPException(404, "Contribution not found")
    goal = get_owned(db, user, contribution.goal_id)
    db.delete(contribution)
    db.commit()
    return progress(db, goal)
