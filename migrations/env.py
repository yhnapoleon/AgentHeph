"""Alembic environment. Target metadata = the write-flow tables (agent_core.write).

DB URL comes from ``AGENTHEPH_DB_URL`` (default: local SQLite file) so no credentials
live in config. As more modules add tables, import their Base/metadata here.
"""
from __future__ import annotations

import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from agent_core.write.models import Base

config = context.config
DB_URL = os.environ.get("AGENTHEPH_DB_URL", "sqlite:///agentheph.db")
config.set_main_option("sqlalchemy.url", DB_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=DB_URL, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.", poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
