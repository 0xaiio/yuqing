from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, echo=False, connect_args=connect_args)


def create_db_and_tables() -> None:
    from app import models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    _run_sqlite_migrations()


def _run_sqlite_migrations() -> None:
    if not settings.database_url.startswith("sqlite"):
        return

    required_columns = {
        "photo": {
            "face_clusters": "TEXT",
            "face_count": "INTEGER DEFAULT 0",
            "vector_embedding": "TEXT",
        },
        "facecluster": {
            "display_name": "TEXT",
            "centroid": "TEXT",
            "person_profile_id": "INTEGER",
            "example_photo_id": "INTEGER",
            "created_at": "TIMESTAMP",
            "updated_at": "TIMESTAMP",
        },
        "personprofile": {
            "normalized_name": "TEXT",
            "centroid": "TEXT",
            "example_sample_id": "INTEGER",
            "sample_count": "INTEGER DEFAULT 0",
            "created_at": "TIMESTAMP",
            "updated_at": "TIMESTAMP",
        },
        "personsample": {
            "original_filename": "TEXT",
            "storage_path": "TEXT",
            "embedding": "TEXT",
            "created_at": "TIMESTAMP",
        },
    }

    with engine.begin() as connection:
        for table_name, columns in required_columns.items():
            existing_columns = _get_existing_columns(connection, table_name)
            if not existing_columns:
                continue
            for column_name, column_definition in columns.items():
                if column_name in existing_columns:
                    continue
                connection.exec_driver_sql(
                    f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
                )


def _get_existing_columns(connection, table_name: str) -> set[str]:
    rows = connection.exec_driver_sql(f"PRAGMA table_info('{table_name}')").all()
    return {str(row[1]) for row in rows}


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
