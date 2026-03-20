from sqlalchemy import create_engine, text, event, inspect, Integer, Float, String, DateTime, Boolean, BigInteger
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from src.core.config import get_config
from src.core.logging import get_logger

logger = get_logger(__name__)

COLUMN_RENAMES = {
    "counter_states": {"last_raw_value": "current_value"},
    "jobs": {"prometheus_url": "url"},
}


class Base(DeclarativeBase):
    pass


def _get_column_type_sql(column):
    """Convert SQLAlchemy column type to PostgreSQL type string."""
    col_type = type(column.type)
    if col_type == Integer or col_type.__name__ == 'Integer':
        return "INTEGER"
    elif col_type == String or col_type.__name__ == 'String':
        length = getattr(column.type, 'length', None)
        return f"VARCHAR({length})" if length else "VARCHAR(255)"
    elif col_type == DateTime or col_type.__name__ == 'DateTime':
        return "TIMESTAMP"
    elif col_type == Boolean or col_type.__name__ == 'Boolean':
        return "BOOLEAN"
    elif col_type == Float or col_type.__name__ == 'Float':
        return "DOUBLE PRECISION"
    elif col_type == BigInteger or col_type.__name__ == 'BigInteger':
        return "BIGINT"
    else:
        return "TEXT"


def _get_column_default_sql(column):
    """Get SQL default clause for a column."""
    if column.default is not None:
        default_val = column.default.arg
        if callable(default_val):
            return None
        if isinstance(default_val, bool):
            return "TRUE" if default_val else "FALSE"
        if isinstance(default_val, (int, float)):
            return str(default_val)
        if isinstance(default_val, str):
            return f"'{default_val}'"
    return None


class Database:
    def __init__(self):
        config = get_config()

        user = config.database_user
        credential = config.database_credential
        host = config.database_host
        port = config.database_port
        dbname = config.database_name

        db_url = f"postgresql://{user}:{credential}@{host}:{port}/{dbname}"
        logger.info("Connecting to database at {}:{}/{}", host, port, dbname)
        self.engine = create_engine(
            db_url,
            pool_pre_ping=True,
            pool_recycle=300,
        )
        self.schema = config.database_schema

        if self.schema:
            self._ensure_schema_exists()
            self._set_search_path()

        self.SessionLocal = sessionmaker(bind=self.engine)
        logger.debug("Database connection established")

    def _ensure_schema_exists(self):
        """Create the schema if it doesn't exist."""
        logger.info("Ensuring schema '{}' exists", self.schema)
        with self.engine.connect() as conn:
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {self.schema}"))
            conn.commit()

    def _set_search_path(self):
        """Set search_path on every new connection so tables use the configured schema."""
        schema = self.schema

        @event.listens_for(self.engine, "connect")
        def set_search_path(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute(f"SET search_path TO {schema}, public")
            cursor.close()

    def create_tables(self):
        from src.core.db import db_models  # noqa: F401
        logger.debug("Creating database tables")
        Base.metadata.create_all(self.engine)
        logger.info("Database tables created")

    def sync_schema(self):
        from src.core.db import db_models  # noqa: F401

        inspector = inspect(self.engine)
        existing_tables = inspector.get_table_names(schema=self.schema)

        for _table_key, table in Base.metadata.tables.items():
            if table.name not in existing_tables:
                logger.info("Table '{}' does not exist, will be created", table.name)
                continue

            existing_columns = {col['name'] for col in inspector.get_columns(table.name, schema=self.schema)}
            model_columns = {col.name: col for col in table.columns}

            # Rename columns if needed (idempotent: skips if old name doesn't exist)
            renames = COLUMN_RENAMES.get(table.name, {})
            if renames:
                with self.engine.connect() as conn:
                    for old_name, new_name in renames.items():
                        if old_name in existing_columns and new_name not in existing_columns:
                            qualified_table = f'"{self.schema}"."{table.name}"' if self.schema else f'"{table.name}"'
                            sql = f'ALTER TABLE {qualified_table} RENAME COLUMN "{old_name}" TO "{new_name}"'
                            logger.info("Renaming column: {}", sql)
                            conn.execute(text(sql))
                    conn.commit()
                # Refresh existing columns after renames
                existing_columns = {col['name'] for col in inspector.get_columns(table.name, schema=self.schema)}

            missing_columns = set(model_columns.keys()) - existing_columns

            if missing_columns:
                logger.info("Table '{}' missing columns: {}", table.name, missing_columns)

                with self.engine.connect() as conn:
                    for col_name in missing_columns:
                        column = model_columns[col_name]
                        col_type = _get_column_type_sql(column)
                        nullable = column.nullable if column.nullable is not None else True
                        default = _get_column_default_sql(column)

                        qualified_table = f'"{self.schema}"."{table.name}"' if self.schema else f'"{table.name}"'
                        sql = f'ALTER TABLE {qualified_table} ADD COLUMN "{col_name}" {col_type}'

                        if default is not None:
                            sql += f" DEFAULT {default}"

                        if not nullable:
                            if default is not None:
                                sql += " NOT NULL"
                            else:
                                sql += " NULL"

                        logger.info("Adding column: {}", sql)
                        conn.execute(text(sql))

                    conn.commit()
                    logger.info("Added {} column(s) to '{}'", len(missing_columns), table.name)

        Base.metadata.create_all(self.engine)

        # Backfill count column for existing rows
        qualified_cs = f'"{self.schema}"."counter_states"' if self.schema else '"counter_states"'
        with self.engine.connect() as conn:
            conn.execute(text(
                f"UPDATE {qualified_cs} SET count = current_value + checkpoint WHERE count = 0"
            ))
            conn.commit()

        logger.info("Schema synchronization complete")

    def get_session(self):
        return self.SessionLocal()


_db: Database | None = None


def get_db_instance() -> Database:
    global _db
    if _db is None:
        _db = Database()
    return _db


def get_db():
    """FastAPI dependency that yields a sync session."""
    db = get_db_instance()
    session = db.get_session()
    try:
        yield session
    finally:
        session.close()
