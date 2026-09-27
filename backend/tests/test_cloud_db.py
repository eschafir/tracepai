from unittest.mock import MagicMock, patch

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db import add_missing_columns, normalize_database_url
from app.fx import get_insert_fn


def test_normalize_database_url():
    assert (
        normalize_database_url("postgres://postgres:secret@db.supabase.co:5432/postgres")
        == "postgresql+psycopg://postgres:secret@db.supabase.co:5432/postgres"
    )
    assert (
        normalize_database_url("postgresql://postgres:secret@db.supabase.co:6543/postgres")
        == "postgresql+psycopg://postgres:secret@db.supabase.co:6543/postgres"
    )
    assert (
        normalize_database_url("postgresql+psycopg://postgres:secret@db.supabase.co:6543/postgres")
        == "postgresql+psycopg://postgres:secret@db.supabase.co:6543/postgres"
    )
    assert normalize_database_url("sqlite:///data/tracepai.db") == "sqlite:///data/tracepai.db"


def test_fx_dialect_selection():
    with patch("app.db.engine") as mock_engine:
        mock_engine.dialect.name = "postgresql"
        fn = get_insert_fn()
        assert fn is pg_insert

        mock_engine.dialect.name = "sqlite"
        fn = get_insert_fn()
        assert fn is sqlite_insert


def test_add_missing_columns_sqlite():
    # Calling add_missing_columns on an initialized DB should succeed idempotently
    add_missing_columns()
