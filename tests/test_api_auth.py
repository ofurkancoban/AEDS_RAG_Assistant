"""Identity: who a caller is, and how they are allowed to become someone."""

import pytest

from db.models import Role, SessionLocal, User


def test_guest_endpoint_mints_a_distinct_identity_per_call(client):
    first = client.post("/auth/guest")
    second = client.post("/auth/guest")
    assert first.status_code == 200
    assert second.status_code == 200

    me_first = client.get("/auth/me", headers={"Authorization": f"Bearer {first.json()['access_token']}"})
    me_second = client.get("/auth/me", headers={"Authorization": f"Bearer {second.json()['access_token']}"})

    # Two visitors must not share an identity: threads, chat history and the
    # rate-limit bucket are all keyed off it.
    assert me_first.json()["id"] != me_second.json()["id"]
    assert me_first.json()["is_guest"] is True
    assert me_first.json()["role"] == "user"


def test_no_token_falls_back_to_one_shared_guest(client):
    first = client.get("/auth/me")
    second = client.get("/auth/me")
    assert first.status_code == 200
    # A new row per tokenless request would let an unauthenticated loop fill
    # the users table.
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["email"] == "guest@aeds.local"


def test_invalid_token_is_rejected_rather_than_downgraded(client):
    response = client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    # Silently treating a bad token as "anonymous" would let a client whose
    # session expired keep working while writing into a different identity.
    assert response.status_code == 401


def test_token_for_a_deleted_user_is_rejected(client, admin_user):
    from api.auth import create_access_token

    token = create_access_token(admin_user)
    session = SessionLocal()
    try:
        session.query(User).filter(User.id == admin_user.id).delete()
        session.commit()
    finally:
        session.close()

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_register_bootstraps_the_first_admin_then_closes(client):
    first = client.post("/auth/register", json={"email": "founder@example.com", "password": "long-enough"})
    assert first.status_code == 200

    session = SessionLocal()
    try:
        created = session.query(User).filter(User.email == "founder@example.com").one()
        assert created.role == Role.ADMIN
    finally:
        session.close()

    second = client.post("/auth/register", json={"email": "someone@example.com", "password": "long-enough"})
    # Students are anonymous; public sign-up is not a feature.
    assert second.status_code == 403


def test_register_rejects_short_passwords(client):
    response = client.post("/auth/register", json={"email": "weak@example.com", "password": "short"})
    assert response.status_code == 400
    assert "at least" in response.json()["detail"]


def test_register_rejects_an_empty_password(client):
    # verify_password("", hash_of_"") succeeds, so an empty password made the
    # account openable by anyone who knew the address.
    response = client.post("/auth/register", json={"email": "empty@example.com", "password": ""})
    assert response.status_code == 400


@pytest.mark.parametrize("login_email", ["Admin@Example.com", "  admin@example.com  "])
def test_login_is_case_and_whitespace_insensitive(client, admin_user, login_email):
    response = client.post(
        "/auth/login",
        data={"username": login_email, "password": "admin-password"},
    )
    assert response.status_code == 200


def test_login_refuses_guest_accounts(client):
    token = client.post("/auth/guest").json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    guest_email = me.json()["email"]

    response = client.post("/auth/login", data={"username": guest_email, "password": ""})
    assert response.status_code == 401


def test_login_gives_the_same_error_for_unknown_and_wrong_password(client, admin_user):
    unknown = client.post("/auth/login", data={"username": "nobody@example.com", "password": "whatever"})
    wrong = client.post("/auth/login", data={"username": "admin@example.com", "password": "wrong-password"})
    assert unknown.status_code == wrong.status_code == 401
    # Differing messages would turn this endpoint into an account-enumeration
    # oracle.
    assert unknown.json()["detail"] == wrong.json()["detail"]


def test_login_runs_password_verification_for_an_unknown_email_too(client, admin_user, monkeypatch):
    """The response body cannot distinguish "no such user" from "wrong
    password" (see the test above), but a login that skips bcrypt entirely
    for an unknown email answers in under a millisecond while a real wrong
    guess takes bcrypt's ~100-300ms - a timing side channel that still
    reveals which emails have accounts. verify_password must run against
    some real hash on both paths so the two cannot be told apart by timing
    either."""
    import api.routes_auth as routes_auth

    calls = []
    real_verify = routes_auth.verify_password

    def spy(password, hashed):
        calls.append(hashed)
        return real_verify(password, hashed)

    monkeypatch.setattr(routes_auth, "verify_password", spy)

    client.post("/auth/login", data={"username": "nobody@example.com", "password": "whatever"})

    assert len(calls) == 1
    assert calls[0] == routes_auth._DUMMY_PASSWORD_HASH


def test_auth_endpoints_are_rate_limited_per_ip(client, monkeypatch):
    from api import rate_limit, routes_auth

    tiny = rate_limit.RateLimiter("test-login", [(3, 3600)])
    monkeypatch.setattr(routes_auth, "auth_limiter", tiny)

    for _ in range(3):
        client.post("/auth/login", data={"username": "nobody@example.com", "password": "x"})

    blocked = client.post("/auth/login", data={"username": "nobody@example.com", "password": "x"})
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_guest_creation_is_rate_limited_per_ip(client, monkeypatch):
    from api import rate_limit, routes_auth

    monkeypatch.setattr(routes_auth, "guest_limiter", rate_limit.RateLimiter("test-guest-mint", [(2, 3600)]))

    assert client.post("/auth/guest").status_code == 200
    assert client.post("/auth/guest").status_code == 200
    # Each call inserts a users row.
    assert client.post("/auth/guest").status_code == 429
