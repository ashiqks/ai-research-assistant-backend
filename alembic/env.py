from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import os, sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.db.base import Base  # noqa
from app.db import models  # noqa

config = context.config
fileConfig(config.config_file_name)

def run_migrations_offline():
    url = os.getenv("DATABASE_URL", "sqlite:///./dev.db")
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    url = os.getenv("DATABASE_URL", "sqlite:///./dev.db")
    connectable = engine_from_config(
        {"sqlalchemy.url": url},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

