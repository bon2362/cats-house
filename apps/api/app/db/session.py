from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool


def create_session_factory(database_url: str, deployment: str = "local") -> sessionmaker[Session]:
    engine_options = {"pool_pre_ping": True}
    if deployment == "vercel":
        engine_options["poolclass"] = NullPool
    return sessionmaker(bind=create_engine(database_url, **engine_options), expire_on_commit=False)


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session
