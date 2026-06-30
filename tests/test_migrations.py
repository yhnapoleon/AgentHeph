"""M0-remainder: the Alembic migration matches the SQLAlchemy models (no drift).

Builds one schema from ``Base.metadata`` and another by running the migration, then
compares tables + columns. If someone edits the models without a matching migration
(or vice-versa), this fails."""
from __future__ import annotations

import os
import pathlib
import shutil
import tempfile

import pytest

pytest.importorskip("alembic")

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, inspect  # noqa: E402

from agent_core.write.models import Base  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _schema(url: str) -> dict[str, set[str]]:
    engine = create_engine(url)
    try:
        insp = inspect(engine)
        return {t: {c["name"] for c in insp.get_columns(t)} for t in insp.get_table_names()}
    finally:
        engine.dispose()  # release the sqlite file handle (Windows)


def test_migration_matches_models():
    workdir = tempfile.mkdtemp(prefix="agentheph-mig-")
    try:
        models_url = f"sqlite:///{pathlib.Path(workdir, 'models.db').as_posix()}"
        eng = create_engine(models_url)
        Base.metadata.create_all(eng)
        eng.dispose()

        mig_url = f"sqlite:///{pathlib.Path(workdir, 'migrated.db').as_posix()}"
        cfg = Config(str(ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(ROOT / "migrations"))
        cfg.set_main_option("sqlalchemy.url", mig_url)
        os.environ["AGENTHEPH_DB_URL"] = mig_url
        command.upgrade(cfg, "head")

        models_schema = _schema(models_url)
        mig_schema = _schema(mig_url)
        mig_schema.pop("alembic_version", None)  # alembic bookkeeping
        assert models_schema == mig_schema
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
