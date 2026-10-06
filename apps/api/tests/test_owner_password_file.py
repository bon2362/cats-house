import pytest
from argon2 import PasswordHasher

from app.auth.password_file import OWNER_PASSWORD_KEY, validate_new_password, write_env_value


def test_replaces_only_the_password_line_and_escapes_dollars(tmp_path):
    env = tmp_path / ".env"
    env.write_text("A=1\nCATS_HOUSE_OWNER_PASSWORD_HASH=$$argon2id$$old\nB=x$$y\n", encoding="utf-8")
    new_hash = PasswordHasher().hash("correct horse battery")

    write_env_value(env, OWNER_PASSWORD_KEY, new_hash)

    lines = env.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "A=1"
    assert lines[2] == "B=x$$y"
    stored = lines[1].removeprefix(f"{OWNER_PASSWORD_KEY}=")
    assert "$" not in stored.replace("$$", "")
    assert PasswordHasher().verify(stored.replace("$$", "$"), "correct horse battery")


def test_adds_the_line_to_a_missing_or_new_file(tmp_path):
    env = tmp_path / ".env"

    write_env_value(env, OWNER_PASSWORD_KEY, "$argon2id$x")

    assert env.read_text(encoding="utf-8") == "CATS_HOUSE_OWNER_PASSWORD_HASH=$$argon2id$$x\n"


@pytest.mark.parametrize(
    ("first", "second", "message"),
    [("long enough pass", "long enough pasS", "не совпадают"), ("short", "short", "не менее 12")],
)
def test_rejects_mismatched_or_short_passwords(first, second, message):
    with pytest.raises(ValueError, match=message):
        validate_new_password(first, second)


def test_keeps_every_other_byte_of_the_file_including_crlf_and_a_missing_final_newline(tmp_path):
    env = tmp_path / ".env"
    env.write_bytes(b"A=1\r\nCATS_HOUSE_OWNER_PASSWORD_HASH=$$old\r\nB=x$$y")

    write_env_value(env, OWNER_PASSWORD_KEY, "$new")

    assert env.read_bytes() == b"A=1\r\nCATS_HOUSE_OWNER_PASSWORD_HASH=$$new\r\nB=x$$y"


def test_an_interrupted_write_leaves_the_original_file_intact(tmp_path, monkeypatch):
    import os

    env = tmp_path / ".env"
    env.write_text("A=1\nCATS_HOUSE_OWNER_PASSWORD_HASH=$$old\n", encoding="utf-8")

    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError):
        write_env_value(env, OWNER_PASSWORD_KEY, "$new")

    assert env.read_text(encoding="utf-8") == "A=1\nCATS_HOUSE_OWNER_PASSWORD_HASH=$$old\n"
    assert [path.name for path in tmp_path.iterdir()] == [".env"]
