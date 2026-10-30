from sqlalchemy import func, select

from app.models import Tag, Territory, User
from app.services.accounts import delete_account
from tests.test_auth import rect, sign_in


def two_accounts(anonymous, outbox):
    """uno@ has a field with a lot and a tag; dos@ has a field; then uno@ is signed in again."""
    sign_in(anonymous, outbox, "uno@example.com")
    field = anonymous.post(
        "/territories", json={"name": "Uno", "geometry": rect(-59.1), "tags": ["cliente:A"]}
    ).json()
    lot = {"name": "Lote", "geometry": rect(-59.1), "parent_id": field["id"]}
    assert anonymous.post("/territories", json=lot).status_code == 201
    uno = anonymous.cookies.get("fw_session")
    anonymous.cookies.clear()
    sign_in(anonymous, outbox, "dos@example.com")
    anonymous.post("/territories", json={"name": "Dos", "geometry": rect(-59.2)})
    anonymous.cookies.clear()
    anonymous.cookies.set("fw_session", uno)
    return field


def test_the_account_says_what_closing_it_removes(anonymous, outbox):
    two_accounts(anonymous, outbox)
    said = anonymous.get("/auth/me/account").json()
    assert said == {"email": "uno@example.com", "fields": 1, "lots": 1, "telegram": False}


def test_closing_an_account_needs_its_email_typed_again(anonymous, outbox, session):
    two_accounts(anonymous, outbox)
    wrong = anonymous.request("DELETE", "/auth/me", json={"confirm": "dos@example.com"})
    assert (wrong.status_code, wrong.json()["code"]) == (400, "confirm")
    assert session.scalar(select(func.count()).select_from(Territory)) == 3
    assert anonymous.get("/auth/me").status_code == 200


def test_closing_an_account_removes_it_and_only_it(anonymous, outbox, session):
    two_accounts(anonymous, outbox)
    done = anonymous.request("DELETE", "/auth/me", json={"confirm": " Uno@Example.com "})
    assert done.status_code == 204
    session.expire_all()
    assert session.scalar(select(User).where(User.email == "uno@example.com")) is None
    assert session.scalars(select(Territory.owner)).all() == ["dos@example.com"]
    assert session.scalars(select(Tag.owner)).all() == []
    # The session went with it, so the old cookie is no longer signed in.
    assert anonymous.get("/auth/me").status_code == 401
    # Someone else's account is untouched.
    assert session.scalar(select(User).where(User.email == "dos@example.com")) is not None


def test_the_photos_kept_as_files_go_too(anonymous, outbox, session, tmp_path):
    field = two_accounts(anonymous, outbox)
    (tmp_path / str(field["id"])).mkdir()
    (tmp_path / str(field["id"]) / "2026-10-01-true_color.png").write_bytes(b"x")
    other = tmp_path / "99999"
    other.mkdir()
    user = session.scalar(select(User).where(User.email == "uno@example.com"))
    delete_account(session, user, tmp_path)
    assert not (tmp_path / str(field["id"])).exists()
    assert other.exists()


def test_signed_out_nobody_can_close_an_account(anonymous):
    assert anonymous.request("DELETE", "/auth/me", json={"confirm": "x"}).status_code == 401
    assert anonymous.get("/auth/me/account").status_code == 401
