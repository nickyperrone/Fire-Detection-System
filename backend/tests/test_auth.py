import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.models import LoginLink


def rect(west):
    ring = [[west, -33.0], [west + 0.01, -33.0], [west + 0.01, -32.99], [west, -32.99]]
    return {"type": "Polygon", "coordinates": [[*ring, ring[0]]]}


def sign_in(anonymous, outbox, email, locale="es"):
    assert anonymous.post("/auth/login", json={"email": email, "locale": locale}).status_code == 202
    token = re.search(r"token=(\S+)", outbox[-1].get_content()).group(1)
    return anonymous.get(f"/auth/callback?token={token}", follow_redirects=False)


def test_a_link_by_email_signs_in_once_and_creates_the_account(anonymous, outbox, session):
    response = sign_in(anonymous, outbox, "  Primo@Example.com ")
    assert outbox[0]["To"] == "primo@example.com"
    assert outbox[0]["Subject"] == "Tu link para entrar a Field Watch"
    assert response.status_code == 303
    assert response.headers["location"] == "http://localhost:3000/"
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("fw_session=") and "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert anonymous.get("/auth/me").json() == {
        "email": "primo@example.com",
        "locale": "es",
        "summary": "WEEKLY",
    }

    # Only the hash is stored, and the link is used up.
    token = re.search(r"token=(\S+)", outbox[0].get_content()).group(1)
    assert session.scalar(select(LoginLink.token_hash)) != token
    anonymous.cookies.clear()
    again = anonymous.get(f"/auth/callback?token={token}", follow_redirects=False)
    assert again.headers["location"] == "http://localhost:3000/?signin=expired"
    assert anonymous.get("/auth/me").status_code == 401


def test_an_expired_link_does_not_sign_in(anonymous, outbox, session):
    anonymous.post("/auth/login", json={"email": "a@b.co"})
    session.execute(update(LoginLink).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    session.commit()
    token = re.search(r"token=(\S+)", outbox[0].get_content()).group(1)
    response = anonymous.get(f"/auth/callback?token={token}", follow_redirects=False)
    assert response.headers["location"].endswith("?signin=expired")


def test_links_per_hour_are_limited_without_telling(anonymous, outbox):
    answers = {
        anonymous.post("/auth/login", json={"email": "a@b.co"}).status_code for _ in range(7)
    }
    assert answers == {202}
    assert len(outbox) == 5


def test_bad_addresses_are_refused(anonymous):
    assert anonymous.post("/auth/login", json={"email": "not an email"}).status_code == 422


def test_fields_need_a_session_and_belong_to_whoever_drew_them(anonymous, outbox):
    assert anonymous.get("/portfolio").status_code == 401
    assert (
        anonymous.post("/territories", json={"name": "A", "geometry": rect(-59.1)}).status_code
        == 401
    )

    sign_in(anonymous, outbox, "uno@example.com")
    mine = anonymous.post("/territories", json={"name": "A", "geometry": rect(-59.1)}).json()
    assert [e["name"] for e in anonymous.get("/portfolio").json()] == ["A"]

    anonymous.cookies.clear()
    sign_in(anonymous, outbox, "dos@example.com")
    assert anonymous.get("/portfolio").json() == []
    assert anonymous.get(f"/territories/{mine['id']}").status_code == 404


def test_signing_out_ends_the_session(anonymous, outbox):
    sign_in(anonymous, outbox, "uno@example.com")
    session_cookie = anonymous.cookies["fw_session"]
    assert anonymous.post("/auth/logout").status_code == 204
    anonymous.cookies.set("fw_session", session_cookie)
    assert anonymous.get("/auth/me").status_code == 401
