from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool


def create_session_factory(database_url: str, deployment: str = "local") -> sessionmaker[Session]:
    engine_options = {"pool_pre_ping": True}
    if deployment == "vercel":
        engine_options["poolclass"] = NullPool
    engine = create_engine(database_url, **engine_options)
    if database_url.startswith("postgresql"):
        event.listen(engine, "connect", _use_public_schema)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _use_public_schema(dbapi_connection, _connection_record) -> None:
    with dbapi_connection.cursor() as cursor:
        cursor.execute("SET search_path TO public")


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session
