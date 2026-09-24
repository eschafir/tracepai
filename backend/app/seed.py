import datetime as dt
import random

from pwdlib import PasswordHash
from sqlmodel import Session

from app.models import (
    Budget,
    Category,
    CategoryKind,
    Goal,
    GoalContribution,
    Kind,
    RecurringRule,
    Split,
    Transaction,
    User,
    Wallet,
    WalletKind,
)
from app.recurring import post_due

EXPENSES = {
    # name: (color slot, monthly budget, merchants, (min, max) amount, times per month)
    "Rent": (1, 1500, [], (0, 0), 0),
    "Groceries": (2, 600, ["Whole Foods", "Trader Joe's", "Safeway"], (25, 140), 7),
    "Dining": (3, 350, ["Blue Bottle", "Chipotle", "Sushi Ran", "Tartine"], (8, 75), 9),
    "Transport": (4, 200, ["Uber", "Shell", "BART"], (6, 55), 6),
    "Utilities": (5, 250, ["PG&E", "Comcast", "T-Mobile"], (45, 110), 3),
    "Subscriptions": (6, 80, [], (0, 0), 0),
    "Shopping": (7, 300, ["Amazon", "Uniqlo", "Target"], (15, 180), 3),
    "Household": (8, 120, ["Target", "IKEA", "Home Depot"], (10, 90), 2),
}
PLACES = {
    # merchant: (place, lat, lng)
    "Whole Foods": ("Whole Foods Market, California St", 37.7907, -122.4213),
    "Trader Joe's": ("Trader Joe's, 4th St", 37.7849, -122.4057),
    "Safeway": ("Safeway, Market St", 37.7686, -122.4270),
    "Blue Bottle": ("Blue Bottle Coffee, Mint Plaza", 37.7823, -122.4078),
    "Chipotle": ("Chipotle, Market St", 37.7894, -122.4014),
    "Sushi Ran": ("Sushi Ran, Sausalito", 37.8591, -122.4853),
    "Tartine": ("Tartine Bakery, Guerrero St", 37.7614, -122.4241),
    "Shell": ("Shell, 9th St", 37.7743, -122.4107),
    "BART": ("Powell St BART", 37.7844, -122.4079),
    "Target": ("Target, Mission St", 37.7845, -122.4033),
    "Uniqlo": ("Uniqlo, Powell St", 37.7856, -122.4078),
    "IKEA": ("IKEA Emeryville", 37.8313, -122.2923),
    "Home Depot": ("The Home Depot, Bayshore Blvd", 37.7474, -122.4063),
}
SUBSCRIPTIONS = [("Netflix", 15.49, 5), ("Spotify", 11.99, 12), ("iCloud", 2.99, 20)]


def seed(session: Session):
    rng = random.Random(42)
    user = User(username="user", password_hash=PasswordHash.recommended().hash("password"))
    session.add(user)
    session.flush()

    checking = Wallet(user_id=user.id, name="Checking", kind=WalletKind.bank, color_slot=1, opening_balance=2500)
    card = Wallet(user_id=user.id, name="Credit card", kind=WalletKind.card, color_slot=7, opening_balance=0)
    cash = Wallet(user_id=user.id, name="Cash", kind=WalletKind.cash, color_slot=4, opening_balance=100)
    savings = Wallet(user_id=user.id, name="Savings", kind=WalletKind.savings, color_slot=3, opening_balance=5000)
    salary = Category(user_id=user.id, name="Salary", color_slot=6, kind=CategoryKind.income)
    freelance = Category(user_id=user.id, name="Freelance", color_slot=1, kind=CategoryKind.income)
    session.add_all([checking, card, cash, savings, salary, freelance])
    categories = {}
    for name, (slot, *_) in EXPENSES.items():
        categories[name] = Category(user_id=user.id, name=name, color_slot=slot)
        session.add(categories[name])
    session.flush()
    for name, (_, limit, *_) in EXPENSES.items():
        session.add(Budget(user_id=user.id, category_id=categories[name].id, monthly_limit=limit))

    def add(date, amount, kind, merchant, wallet, category=None, splits=(), **extra):
        place, lat, lng = PLACES.get(merchant, (None, None, None))
        session.add(
            Transaction(
                place=place,
                lat=lat,
                lng=lng,
                user_id=user.id,
                date=date,
                amount=round(amount, 2),
                kind=kind,
                merchant=merchant,
                wallet_id=wallet.id,
                category_id=category.id if category else None,
                splits=[Split(category_id=c.id, amount=a) for c, a in splits],
                **extra,
            )
        )

    today = dt.date.today()
    first = (today.replace(day=1) - dt.timedelta(days=150)).replace(day=1)
    session.add_all(
        [
            RecurringRule(user_id=user.id, next_date=first, kind=Kind.income, amount=5200, merchant="Acme Corp",
                          wallet_id=checking.id, category_id=salary.id),
            RecurringRule(user_id=user.id, next_date=first, amount=1450, merchant="Parkview Apartments",
                          wallet_id=checking.id, category_id=categories["Rent"].id),
            RecurringRule(user_id=user.id, next_date=first.replace(day=2), kind=Kind.transfer, amount=500,
                          merchant="Monthly savings", wallet_id=checking.id, to_wallet_id=savings.id),
        ]
    )

    month = first
    card_spent = 0.0
    while month <= today:
        next_month = (month + dt.timedelta(days=32)).replace(day=1)
        days = [d for d in range((next_month - month).days) if month + dt.timedelta(days=d) <= today]

        def day(fixed=None):
            return month + dt.timedelta(days=fixed if fixed in days else rng.choice(days))

        if card_spent and 4 in days:
            add(day(4), card_spent, Kind.transfer, "Card payment", checking, to_wallet_id=card.id)
            card_spent = 0.0
        if 2 in days:
            add(day(2), 200, Kind.transfer, "ATM withdrawal", checking, to_wallet_id=cash.id)
        if rng.random() < 0.6:
            add(day(), rng.uniform(400, 1200), Kind.income, "Client project", checking, freelance, tags="freelance")
        for merchant, amount, on_day in SUBSCRIPTIONS:
            if on_day in days:
                add(day(on_day), amount, Kind.expense, merchant, card, categories["Subscriptions"])
                card_spent += amount
        for name, (_, _, merchants, (lo, hi), times) in EXPENSES.items():
            for _ in range(round(times * len(days) / 30)):
                if name == "Utilities":
                    wallet = checking
                elif name in ("Dining", "Transport") and rng.random() < 0.3:
                    wallet = cash
                else:
                    wallet = card
                amount = round(rng.uniform(lo, hi), 2)
                add(day(), amount, Kind.expense, rng.choice(merchants), wallet, categories[name])
                if wallet is card:
                    card_spent += amount
        if len(days) > 10:
            add(
                day(),
                150,
                Kind.expense,
                "Target",
                card,
                splits=[(categories["Groceries"], 100), (categories["Household"], 50)],
                notes="Split: groceries and household supplies",
            )
            card_spent += 150
        month = next_month

    add(first + dt.timedelta(days=40), 1850, Kind.expense, "United Airlines", checking, categories["Shopping"], tags="vacation", notes="Flights to Lisbon")
    add(first + dt.timedelta(days=95), 1299, Kind.expense, "Apple Store", checking, categories["Shopping"], tags="workReimbursable", notes="Laptop")
    trip = Goal(user_id=user.id, name="Lisbon trip", target_amount=2000, color_slot=2,
                target_date=(today.replace(day=1) + dt.timedelta(days=190)).replace(day=1))
    fund = Goal(user_id=user.id, name="Emergency fund", target_amount=10000, color_slot=3)
    session.add_all([trip, fund])
    session.flush()
    for months_ago, amount in ((3, 300), (2, 300), (1, 400)):
        session.add(GoalContribution(goal_id=trip.id, amount=amount, date=today - dt.timedelta(days=30 * months_ago), note="Monthly"))
    session.add(GoalContribution(goal_id=fund.id, amount=2500, date=first, note="Starting amount"))
    session.add(GoalContribution(goal_id=fund.id, amount=500, date=today - dt.timedelta(days=20), note="Bonus"))
    session.commit()
    post_due(session, user.id, today)
