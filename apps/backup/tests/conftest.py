"""Тестовая база PostgreSQL 17 с выдуманными данными и настоящие pg_dump/pg_restore."""

import hashlib

import psycopg
import pytest
from testcontainers.community.postgres import PostgresContainer

FAKE_FILES = [bytes([i]) * 50_000 + b"%PDF-fake" for i in range(5)]


@pytest.fixture(scope="session")
def bin_dir(tmp_path_factory):
    from drive_backup.pgtools import ensure_binaries
    return ensure_binaries(tmp_path_factory.mktemp("pg"))


def create_schema(conn, with_media=True):
    conn.execute("create table people (id int primary key, full_name text not null)")
    conn.execute("create table unions (id int primary key)")
    conn.execute("create table parent_children (id int primary key)")
    conn.execute("create table events (id int primary key, label text)")
    if with_media:
        conn.execute("create table media (id int primary key, content bytea, preview bytea)")


@pytest.fixture(scope="session")
def source_db():
    with PostgresContainer("postgres:17-alpine", driver=None) as container:
        url = container.get_connection_url()
        with psycopg.connect(url, autocommit=True) as conn:
            create_schema(conn)
            conn.execute("insert into people values (1, 'Тестова Анна'), (2, 'Тестов Пётр')")
            conn.execute("insert into unions values (1)")
            conn.execute("insert into parent_children values (1), (2)")
            conn.execute("insert into events values (1, 'Рождение')")
            for i, content in enumerate(FAKE_FILES):
                conn.execute("insert into media values (%s, %s, %s)", (i, content, content[:100] if i % 2 else None))
            conn.execute("create database restored")
            conn.execute("create database no_media")
        yield {"url": url + "?sslmode=disable", "container": container}


@pytest.fixture(scope="session")
def dump_file(tmp_path_factory, source_db, bin_dir):
    from drive_backup.pgtools import dump
    target = tmp_path_factory.mktemp("dump") / "cats-house-2026-11-09T0200Z.dump"
    dump(source_db["url"], target, bin_dir)
    return target


def media_digests(url):
    with psycopg.connect(url) as conn:
        rows = conn.execute("select id, content from media order by id").fetchall()
    return [(row[0], hashlib.sha256(row[1]).hexdigest()) for row in rows]
