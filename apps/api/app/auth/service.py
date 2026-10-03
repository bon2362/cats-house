from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from pydantic import SecretStr

password_hasher = PasswordHasher()


def verify_owner_password(password: str, password_hash: SecretStr) -> bool:
    try:
        return password_hasher.verify(password_hash.get_secret_value(), password)
    except (InvalidHashError, VerifyMismatchError):
        return False
