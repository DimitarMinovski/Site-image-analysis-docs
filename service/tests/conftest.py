"""Test configuration.

Tests run against a dedicated database and a temporary storage root, so they
never touch development data. The environment is set here, before any app module
is imported, because Settings reads the environment once at import time.

There is a deliberate guard on the truncate helper: it refuses to run unless the
database name contains "test". Pointing a test suite at a real database is a
mistake that happens, and it should fail loudly rather than quietly erase rows.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import psycopg
import pytest

TEST_DB = "siteimg_test"
ADMIN_URL = os.environ.get("ADMIN_DATABASE_URL", "postgresql://localhost:5432/postgres")

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", f"postgresql://localhost:5432/{TEST_DB}"
)
os.environ.setdefault("STORAGE_BACKEND", "local")
os.environ.setdefault("STORAGE_ROOT", tempfile.mkdtemp(prefix="siteimg-test-"))
os.environ.setdefault("API_TOKEN", "test-token")
os.environ.setdefault("ANALYSER", "stub")
os.environ.setdefault("MODEL_PROVIDER", "none")


def _ensure_database() -> None:
    with psycopg.connect(ADMIN_URL, autocommit=True) as c:
        exists = c.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,)).fetchone()
        if not exists:
            c.execute(f'CREATE DATABASE "{TEST_DB}"')


def _truncate() -> None:
    from app.config import settings

    if "test" not in settings.database_url.rsplit("/", 1)[-1]:
        raise RuntimeError(
            f"refusing to truncate {settings.database_url!r}: "
            "the database name must contain 'test'"
        )
    with psycopg.connect(settings.database_url) as c:
        c.execute("TRUNCATE reviews, assessments, representations, jobs, images RESTART IDENTITY CASCADE")
        c.commit()


@pytest.fixture(scope="session", autouse=True)
def _database():
    _ensure_database()
    from app.db import migrate

    migrate()
    yield


@pytest.fixture(autouse=True)
def _clean_tables(_database):
    """Each test starts from an empty database.

    Isolation matters here specifically because uploads are idempotent by image
    SHA: a row left behind by an earlier test turns a fresh upload into a
    duplicate, and the test would be asserting the wrong thing.
    """
    _truncate()
    yield
