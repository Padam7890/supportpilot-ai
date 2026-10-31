from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_round_trip():
    encoded = hash_password("a-long-test-password")
    assert encoded != "a-long-test-password"
    assert verify_password("a-long-test-password", encoded)
    assert not verify_password("wrong-password", encoded)


def test_jwt_contains_user_and_tenant_claims():
    token = create_access_token("user-123", "org-456")
    claims = decode_access_token(token)
    assert claims["sub"] == "user-123"
    assert claims["org"] == "org-456"
