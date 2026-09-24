import re

from sqlmodel import Session, col, select

from app.models import Category, Kind, Transaction

KEYWORDS = {
    "Transport": ["uber", "lyft", "shell", "chevron", "bart", "metro", "taxi", "parking", "gas"],
    "Groceries": ["safeway", "whole foods", "trader joe", "kroger", "aldi", "grocery", "market"],
    "Dining": ["restaurant", "cafe", "coffee", "starbucks", "chipotle", "pizza", "sushi", "bar", "doordash"],
    "Subscriptions": ["netflix", "spotify", "icloud", "apple.com", "youtube", "disney", "hbo", "prime video"],
    "Utilities": ["electric", "pg&e", "comcast", "water", "internet", "t-mobile", "verizon", "at&t"],
    "Shopping": ["amazon", "uniqlo", "zara", "target", "best buy", "apple store"],
    "Household": ["ikea", "home depot", "lowe"],
    "Rent": ["rent", "apartments", "landlord"],
    "Salary": ["payroll", "salary"],
}


def normalize(merchant: str) -> str:
    text = re.sub(r"[^a-z&'.\s]", " ", merchant.lower())
    return " ".join(word for word in text.split() if len(word) > 1 or word == "&")


def suggest_category(db: Session, user_id: int, merchant: str, kind: Kind = Kind.expense) -> dict | None:
    key = normalize(merchant)
    if not key:
        return None
    recent = db.exec(
        select(Transaction.merchant, Transaction.category_id)
        .where(Transaction.user_id == user_id, Transaction.kind == kind, col(Transaction.category_id).is_not(None))
        .order_by(col(Transaction.date).desc(), col(Transaction.id).desc())
    )
    for past_merchant, category_id in recent:
        if normalize(past_merchant) == key:
            return {"category_id": category_id, "source": "history"}
    categories = {c.name.lower(): c.id for c in db.exec(select(Category).where(Category.user_id == user_id, Category.kind == kind))}
    for name, words in KEYWORDS.items():
        if name.lower() in categories and any(re.search(rf"\b{re.escape(word)}", key) for word in words):
            return {"category_id": categories[name.lower()], "source": "keyword"}
    return None
