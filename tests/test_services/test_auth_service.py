import pytest

from backend.services.auth_service import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_hash_and_verify():
    hashed = hash_password("mysecret")
    assert verify_password("mysecret", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_token_roundtrip():
    token = create_access_token("user-123")
    assert decode_token(token) == "user-123"


def test_invalid_token_raises():
    from jose import JWTError

    with pytest.raises(JWTError):
        decode_token("not.a.valid.token")
