import httpx

from app.config import Settings, get_settings
from app.main import app
from app.routers.dependencies import http_client
from app.services.captcha import RateLimit, client_ip

LOGIN = {"email": "uno@example.com", "locale": "es"}


def with_turnstile(answer: dict, seen: list):
    app.dependency_overrides[get_settings] = lambda: Settings(
        turnstile_site_key="site", turnstile_secret_key="secret"
    )

    def cloudflare(request: httpx.Request) -> httpx.Response:
        seen.append(request.content.decode())
        return httpx.Response(200, json=answer)

    app.dependency_overrides[http_client] = lambda: httpx.Client(
        transport=httpx.MockTransport(cloudflare)
    )


def test_the_page_gets_the_public_key_only(anonymous):
    with_turnstile({"success": True}, [])
    assert anonymous.get("/auth/config").json() == {"captcha_site_key": "site"}


def test_sign_in_needs_cloudflares_check_when_it_is_set_up(anonymous, outbox):
    seen = []
    with_turnstile({"success": False}, seen)
    response = anonymous.post("/auth/login", json=LOGIN | {"captcha": "bad"})
    assert (response.status_code, response.json()["code"]) == (403, "captcha")
    missing = anonymous.post("/auth/login", json=LOGIN)
    assert missing.status_code == 403
    assert outbox == []
    # The visitor's address from Cloudflare goes along with the token.
    anonymous.post(
        "/auth/login", json=LOGIN | {"captcha": "t"}, headers={"CF-Connecting-IP": "203.0.113.9"}
    )
    assert "remoteip=203.0.113.9" in seen[-1] and "secret=secret" in seen[-1]


def test_a_passed_check_sends_the_link(anonymous, outbox):
    with_turnstile({"success": True}, [])
    assert anonymous.post("/auth/login", json=LOGIN | {"captcha": "ok"}).status_code == 202
    assert len(outbox) == 1


def test_one_network_address_gets_a_limited_number_of_sign_ins(anonymous, thresholds):
    limit = thresholds["auth"]["login_requests_per_ip_hour"]
    headers = {"CF-Connecting-IP": "198.51.100.7"}
    codes = [
        anonymous.post(
            "/auth/login", json={"email": f"u{i}@example.com"}, headers=headers
        ).status_code
        for i in range(limit + 1)
    ]
    assert codes[:limit] == [202] * limit
    assert codes[-1] == 429
    # Another address is not held back.
    other = {"CF-Connecting-IP": "198.51.100.8"}
    assert anonymous.post("/auth/login", json=LOGIN, headers=other).status_code == 202


def test_the_limit_forgets_after_an_hour():
    limit = RateLimit()
    assert limit.allow("ip", 1, now=0) and not limit.allow("ip", 1, now=10)
    assert limit.allow("ip", 1, now=3601)


def test_the_visitor_address_comes_from_cloudflare_first():
    assert (
        client_ip({"cf-connecting-ip": "1.1.1.1", "x-forwarded-for": "2.2.2.2"}, "3") == "1.1.1.1"
    )
    assert client_ip({"x-forwarded-for": "2.2.2.2, 9.9.9.9"}, "3") == "2.2.2.2"
    assert client_ip({}, "3") == "3"
