import asyncio

from httpx import ASGITransport, AsyncClient



def create_app(settings):
    from app.main import create_app as make  # app.main builds an app from the environment on import

    return make(settings)

HEADERS = {"x-robots-tag": "noindex, nofollow, noarchive", "x-frame-options": "DENY", "referrer-policy": "same-origin", "x-content-type-options": "nosniff"}


def call(app, method, path, headers=None, client=("127.0.0.1", 5000)):
    async def run():
        transport = ASGITransport(app=app, client=client)
        async with AsyncClient(transport=transport, base_url="https://testserver") as http:
            return await http.request(method, path, headers=headers)
    return asyncio.run(run())


def test_every_response_forbids_indexing_and_framing(settings):
    app = create_app(settings)
    for path in ("/api/v1/health", "/robots.txt"):
        response = call(app, "GET", path)
        assert {key: response.headers[key] for key in HEADERS} == HEADERS


def test_robots_txt_disallows_everything(settings):
    response = call(create_app(settings), "GET", "/robots.txt")
    assert response.status_code == 200 and response.text == "User-agent: *\nDisallow: /\n"


def public(settings, **changes):
    return create_app(settings.model_copy(update={"public_mode": True, **changes}))


def test_public_mode_limits_each_address_separately(settings):
    app = public(settings)
    first = {"CF-Connecting-IP": "203.0.113.1"}
    statuses = [call(app, "GET", "/api/v1/health", first).status_code for _ in range(121)]
    other = call(app, "GET", "/api/v1/health", {"CF-Connecting-IP": "203.0.113.2"})

    assert statuses[:120] == [200] * 120 and statuses[120] == 429
    blocked = call(app, "GET", "/api/v1/health", first)
    assert blocked.json() == {"detail": "Слишком много запросов. Подождите минуту."} and int(blocked.headers["retry-after"]) >= 1
    assert blocked.headers["x-robots-tag"].startswith("noindex")
    assert other.status_code == 200
    assert call(app, "GET", "/robots.txt", first).status_code == 200  # not an /api/ request


def test_no_limit_outside_public_mode(settings):
    app = create_app(settings)
    assert {call(app, "GET", "/api/v1/health").status_code for _ in range(130)} == {200}


def test_forged_tunnel_header_is_ignored_from_a_remote_connection(settings):
    app = public(settings)
    for index in range(120):
        call(app, "GET", "/api/v1/health", {"CF-Connecting-IP": f"198.51.100.{index}"}, client=("192.0.2.9", 5000))
    assert call(app, "GET", "/api/v1/health", {"CF-Connecting-IP": "198.51.100.200"}, client=("192.0.2.9", 5000)).status_code == 429


def test_the_signed_in_owner_is_not_limited(settings):
    app = public(settings)

    async def run():
        transport = ASGITransport(app=app, client=("127.0.0.1", 5000))
        async with AsyncClient(transport=transport, base_url="https://testserver") as http:
            await http.post("/api/v1/auth/login", json={"password": "test-owner-password"}, headers={"CF-Connecting-IP": "203.0.113.5"})
            return [(await http.get("/api/v1/auth/status", headers={"CF-Connecting-IP": "203.0.113.5"})).status_code for _ in range(130)]

    assert set(asyncio.run(run())) == {200}


def test_login_throttle_counts_the_tunnel_visitor_address(settings):
    app = public(settings)

    async def run():
        transport = ASGITransport(app=app, client=("127.0.0.1", 5000))
        async with AsyncClient(transport=transport, base_url="https://testserver") as http:
            async def attempt(address):
                response = await http.post("/api/v1/auth/login", json={"password": "wrong"}, headers={"CF-Connecting-IP": address})
                return response.status_code
            first = [await attempt("203.0.113.7") for _ in range(6)]
            return first, await attempt("203.0.113.8")

    first, other = asyncio.run(run())
    assert first == [401] * 5 + [429] and other == 401


def site(settings, tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("nope")
    return create_app(settings.model_copy(update={"web_dist": dist}))


def test_built_pages_and_assets_are_served(settings, tmp_path):
    app = site(settings, tmp_path)
    page = call(app, "GET", "/people/123")
    home = call(app, "GET", "/")
    asset = call(app, "GET", "/assets/app.js")
    assert page.status_code == 200 and page.text == "<html>app</html>" and page.headers["x-robots-tag"].startswith("noindex")
    assert home.text == "<html>app</html>"
    assert asset.status_code == 200 and asset.text == "console.log(1)"


def test_api_routes_and_files_outside_dist_are_not_swallowed(settings, tmp_path):
    app = site(settings, tmp_path)
    missing_api = call(app, "GET", "/api/v1/no-such-route")
    escapes = [call(app, "GET", path) for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/assets/%2e%2e/%2e%2e/secret.txt")]
    assert missing_api.status_code == 404 and missing_api.json() == {"detail": "Not Found"}
    assert all("nope" not in response.text for response in escapes)
    assert call(app, "GET", "/robots.txt").text.startswith("User-agent")
    assert call(app, "GET", "/api/v1/health").status_code == 200


def test_public_mode_hides_the_api_description(settings):
    hidden = public(settings)
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert call(hidden, "GET", path).status_code == 404
    assert call(create_app(settings), "GET", "/openapi.json").status_code == 200
