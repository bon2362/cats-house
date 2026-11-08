from drive_backup.redact import redact


def test_removes_database_urls_of_any_driver():
    text = 'pg_dump: error: connection to "postgresql://u:secret@host/db?sslmode=require" failed; also postgres+psycopg://a:b@c/d'
    out = redact(text, [])
    assert "secret" not in out and "a:b@c" not in out
    assert out.count("<адрес базы>") == 2


def test_removes_secret_values_longest_first():
    out = redact("token abc123 and abc", ["abc", "abc123"])
    assert out == "token *** and ***"


def test_ignores_empty_secrets_and_limits_length():
    out = redact("x" * 600, ["", None])
    assert len(out) == 500
