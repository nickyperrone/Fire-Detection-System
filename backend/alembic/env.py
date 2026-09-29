from logging.config import fileConfig

from sqlalchemy import create_engine

from alembic import context
from app.config import get_settings
from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def include_object(obj, name, type_, reflected, compare_to):
    # Tables that exist only in the database belong to extensions (spatial_ref_sys, and the
    # Tiger geocoder tables that the postgis/postgis image installs), never to this app.
    return not (type_ == "table" and reflected and compare_to is None)


def run_migrations_online() -> None:
    # Tests pass their own URL through the Alembic config; everything else uses the settings.
    url = config.get_main_option("sqlalchemy.url") or get_settings().database_url
    with create_engine(url).connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=Base.metadata,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
