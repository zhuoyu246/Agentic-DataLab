from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from typing import Generator
from core.config import get_settings

settings = get_settings()

engine_options: dict = {"pool_pre_ping": True}

if settings.postgres_dsn.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}
    if ":memory:" in settings.postgres_dsn:
        engine_options["poolclass"] = StaticPool
else:
    engine_options.update(pool_size=10, max_overflow=20)

engine = create_engine(settings.postgres_dsn, **engine_options)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
