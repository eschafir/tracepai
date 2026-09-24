import os
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine, select

from app.models import User
from app.seed import seed

DATA_DIR = Path(os.environ.get("TRACEPAI_DATA_DIR", "data"))
RECEIPTS_DIR = DATA_DIR / "receipts"

engine = create_engine(f"sqlite:///{DATA_DIR / 'tracepai.db'}", connect_args={"check_same_thread": False})


def init_db():
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        if not session.exec(select(User)).first():
            seed(session)


def get_session():
    with Session(engine) as session:
        yield session
