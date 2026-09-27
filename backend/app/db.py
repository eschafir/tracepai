import os
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine, select

from app.models import User
from app.seed import seed

DATA_DIR = Path(os.environ.get("TRACEPAI_DATA_DIR", "data"))
RECEIPTS_DIR = DATA_DIR / "receipts"


def normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://") and "+psycopg" not in url:
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL:
    engine = create_engine(normalize_database_url(DATABASE_URL), pool_pre_ping=True)
else:
    engine = create_engine(f"sqlite:///{DATA_DIR / 'tracepai.db'}", connect_args={"check_same_thread": False})


def add_missing_columns():
    """Add columns that are in the models but not yet in an existing database. New columns are nullable or have a text default."""
    with engine.begin() as conn:
        if engine.dialect.name == "sqlite":
            for table in SQLModel.metadata.sorted_tables:
                existing = {row[1] for row in conn.exec_driver_sql(f'PRAGMA table_info("{table.name}")')}
                if not existing:  # a new table; create_all makes it
                    continue
                for column in table.columns:
                    if column.name not in existing:
                        kind = column.type.compile(dialect=engine.dialect)
                        default = column.default.arg if column.default is not None and column.default.is_scalar else None
                        if isinstance(default, str):  # e.g. wallet.currency = 'USD', so existing rows get a value
                            kind += f" DEFAULT '{default}'"
                        conn.exec_driver_sql(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {kind}')
        else:
            from sqlalchemy import inspect, text

            inspector = inspect(conn)
            existing_tables = set(inspector.get_table_names())
            for table in SQLModel.metadata.sorted_tables:
                if table.name not in existing_tables:
                    continue
                existing_columns = {col["name"] for col in inspector.get_columns(table.name)}
                for column in table.columns:
                    if column.name not in existing_columns:
                        kind = column.type.compile(dialect=engine.dialect)
                        default = column.default.arg if column.default is not None and column.default.is_scalar else None
                        default_clause = f" DEFAULT '{default}'" if isinstance(default, str) else ""
                        conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN IF NOT EXISTS "{column.name}" {kind}{default_clause}'))


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
