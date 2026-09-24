import os
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine, select

from app.models import User
from app.seed import seed

DATA_DIR = Path(os.environ.get("TRACEPAI_DATA_DIR", "data"))
RECEIPTS_DIR = DATA_DIR / "receipts"

engine = create_engine(f"sqlite:///{DATA_DIR / 'tracepai.db'}", connect_args={"check_same_thread": False})


def add_missing_columns():
    """Add columns that are in the models but not yet in an existing database. New columns are nullable."""
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            existing = {row[1] for row in conn.exec_driver_sql(f'PRAGMA table_info("{table.name}")')}
            if not existing:  # a new table; create_all makes it
                continue
            for column in table.columns:
                if column.name not in existing:
                    kind = column.type.compile(dialect=engine.dialect)
                    conn.exec_driver_sql(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {kind}')


def init_db():
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(engine)
    add_missing_columns()
    with Session(engine) as session:
        if not session.exec(select(User)).first():
            seed(session)


def get_session():
    with Session(engine) as session:
        yield session
