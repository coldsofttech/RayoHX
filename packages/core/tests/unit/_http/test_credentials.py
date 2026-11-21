"""Which hosts receive secrets, and the headers each request carries."""

import httpx

from rayohx._http._credentials import CredentialScope
from rayohx.config import NetworkConfig
from rayohx.models import SegmentRange
from tests.helpers.http import URL, Handler, make, ok


def test_custom_user_agent_and_headers_are_sent() -> None:
    client, recorder, _ = make(
        ok(), user_agent="Agent/2", headers={"Referer": "https://site.example/", "X-Extra": "1"}
    )
    client.fetch_bytes(URL)
    headers = recorder.requests[0].headers
    assert headers["user-agent"] == "Agent/2"
    assert headers["referer"] == "https://site.example/"
    assert headers["x-extra"] == "1"


def test_a_user_agent_header_replaces_the_default() -> None:
    client, recorder, _ = make(ok(), headers={"user-agent": "Mine"})
    client.fetch_bytes(URL)
    assert recorder.requests[0].headers.get_list("user-agent") == ["Mine"]


SECRETS = {"Authorization": "Bearer s3", "X-Api-Key": "k3", "Referer": "https://site.example/"}


def echo_after_redirect() -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "media.example.com":
            return httpx.Response(302, headers={"location": "https://cdn.other.net/seg.ts"})
        return httpx.Response(200, content=b"segment")

    return handler


def test_secrets_do_not_follow_a_redirect_to_another_host() -> None:
    client, recorder, _ = make(echo_after_redirect(), headers=SECRETS, cookies={"sid": "abc"})
    client.fetch_bytes(URL)
    first, second = recorder.requests
    assert first.headers["authorization"] == "Bearer s3"
    assert first.headers["x-api-key"] == "k3"
    assert first.headers["cookie"] == "sid=abc"
    for name in ("authorization", "x-api-key", "cookie"):
        assert name not in second.headers
    assert second.headers["referer"] == "https://site.example/"
    assert second.headers["user-agent"] == "RayoHX"


def test_listed_credential_hosts_receive_secrets() -> None:
    client, recorder, _ = make(
        echo_after_redirect(),
        headers=SECRETS,
        cookies={"sid": "abc"},
        credential_hosts=("CDN.other.net",),
    )
    client.fetch_bytes(URL)
    second = recorder.requests[1]
    assert second.headers["authorization"] == "Bearer s3"
    assert second.headers["cookie"] == "sid=abc"


def test_a_fixed_origin_does_not_trust_a_different_first_host() -> None:
    client, recorder, _ = make(
        ok(), origin="https://start.example.com/m.m3u8", headers=SECRETS, cookies={"a": "b"}
    )
    client.fetch_bytes("https://elsewhere.example.org/a.ts")
    assert "authorization" not in recorder.requests[0].headers
    assert "cookie" not in recorder.requests[0].headers


def test_without_an_origin_the_first_host_is_trusted() -> None:
    client, recorder, _ = make(ok(), origin=None, headers=SECRETS)
    client.fetch_bytes("https://first.example.com/a.ts")
    client.fetch_bytes("https://second.example.com/a.ts")
    assert "authorization" in recorder.requests[0].headers
    assert "authorization" not in recorder.requests[1].headers


def test_an_explicit_cookie_header_is_not_duplicated() -> None:
    client, recorder, _ = make(ok(), headers={"Cookie": "mine=1"}, cookies={"sid": "abc"})
    client.fetch_bytes(URL)
    assert recorder.requests[0].headers.get_list("cookie") == ["mine=1"]


def test_scope_trusts_the_origin_and_listed_hosts_only() -> None:
    config = NetworkConfig(credential_hosts=("keys.example.com",))
    scope = CredentialScope(config, "https://start.example.com/m.m3u8")
    assert scope.is_trusted("start.example.com")
    assert scope.is_trusted("keys.example.com")
    assert not scope.is_trusted("other.example.com")


def test_scope_without_an_origin_adopts_the_first_host() -> None:
    scope = CredentialScope(NetworkConfig())
    assert scope.is_trusted("first.example.com")
    assert not scope.is_trusted("second.example.com")


def test_scope_adds_cookies_and_range_for_trusted_hosts() -> None:
    config = NetworkConfig(cookies={"sid": "abc"}, headers={"Authorization": "Bearer t"})
    scope = CredentialScope(config, URL)
    byte_range = SegmentRange(offset=10, length=5)
    trusted = scope.headers_for(URL, "identity", byte_range)
    assert trusted["Cookie"] == "sid=abc"
    assert trusted["Authorization"] == "Bearer t"
    assert trusted["Range"] == byte_range.http_header()
    untrusted = scope.headers_for("https://elsewhere.example.org/a.ts", "identity", None)
    assert "Cookie" not in untrusted
    assert "Authorization" not in untrusted
    assert "Range" not in untrusted
    assert untrusted["Accept-Encoding"] == "identity"
