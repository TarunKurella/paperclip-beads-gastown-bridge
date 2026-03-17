from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from bridge import db


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = db.connect(str(tmp_path / "test.db"))
    db.migrate(c, str(Path(__file__).parent.parent / "bridge" / "migrations"))
    return c
