import json
import socket
import ssl

import anyio
import httpcore
import httpx
import pytest
from app.cimd import ClientMetadataResolver, InvalidClientMetadata
from httpcore._backends.anyio import AnyIOBackend

CLIENT = "https://client.example/metadata"
METADATA = {
    "client_id": CLIENT,
    "client_name": "Example",
    "redirect_uris": ["https://client.example/callback"],
    "token_endpoint_auth_method": "none",
}


def run(resolver, client_id=CLIENT):
    return anyio.run(resolver.resolve, client_id)


@pytest.fixture
def metadata_server(monkeypatch):
    state = {"addresses": ["8.8.8.8"], "body": METADATA, "headers": {}, "status": 200}
    requests = []
    client_type = httpx.AsyncClient

    async def resolve(host, port, **kwargs):
        assert host == "client.example" and port == 443
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port)) for ip in state["addresses"]
        ]

    def handler(request):
        requests.append(request)
        if state.get("error"):
            raise state["error"]
        content = state["body"]
        if not isinstance(content, bytes):
            content = json.dumps(content).encode()
        return httpx.Response(state["status"], headers=state["headers"], content=content)

    def client(**kwargs):
        assert kwargs == {"trust_env": False, "follow_redirects": False}
        return client_type(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(anyio, "getaddrinfo", resolve)
    monkeypatch.setattr(httpx, "AsyncClient", client)
    state["headers"]["content-type"] = "application/json"
    return state, requests


def test_resolver_pins_public_ip_and_tls_hostname(metadata_server):
    _, requests = metadata_server
    resolver = ClientMetadataResolver()
    assert run(resolver) == METADATA
    assert run(resolver) == METADATA
    assert len(requests) == 1
    assert requests[0].url.host == "8.8.8.8"
    assert requests[0].headers["host"] == "client.example"
    assert requests[0].headers["accept-encoding"] == "identity"
    assert requests[0].extensions["sni_hostname"] == "client.example"
    assert "cookie" not in requests[0].headers and "authorization" not in requests[0].headers


@pytest.mark.parametrize(
    "client_id",
    [
        "http://client.example/metadata",
        "https://client.example/",
        "https://user@client.example/x",
        "https://client.example:444/x",
        "https://client.example/x#fragment",
        "https://client.example/x#",
        "https://@client.example/x",
    ],
)
def test_invalid_client_url_rejected(metadata_server, client_id):
    with pytest.raises(InvalidClientMetadata):
        run(ClientMetadataResolver(), client_id)
    assert not metadata_server[1]


@pytest.mark.parametrize(
    "addresses",
    [
        ["127.0.0.1"],
        ["10.0.0.1"],
        ["169.254.1.1"],
        ["::1"],
        ["::ffff:127.0.0.1"],
        ["8.8.8.8", "10.0.0.1"],
    ],
)
def test_internal_and_mixed_dns_rejected(metadata_server, addresses):
    metadata_server[0]["addresses"] = addresses
    with pytest.raises(InvalidClientMetadata):
        run(ClientMetadataResolver())
    assert not metadata_server[1]


@pytest.mark.parametrize(
    "change",
    [
        {"client_id": "https://other.example/x"},
        {"client_name": ""},
        {"redirect_uris": []},
        {"redirect_uris": ["http://client.example/callback"]},
        {"token_endpoint_auth_method": "basic"},
        {"redirect_uris": ["https://*.example/callback"]},
        {"token_endpoint_auth_method": None},
        {"grant_types": "authorization_code"},
        {"response_types": [5]},
        {"client_uri": 10},
    ],
)
def test_invalid_metadata_rejected(metadata_server, change):
    metadata_server[0]["body"] = METADATA | change
    with pytest.raises(InvalidClientMetadata):
        run(ClientMetadataResolver())


@pytest.mark.parametrize(
    "body,status,content_type",
    [
        (b"{", 200, "application/json"),
        (b"x" * 65537, 200, "application/json"),
        (b"{}", 302, "application/json"),
        (b"{}", 200, "text/html"),
    ],
    ids=["malformed", "oversized", "redirect", "content-type"],
)
def test_invalid_response_rejected(metadata_server, body, status, content_type):
    state, _ = metadata_server
    state.update(body=body, status=status)
    state["headers"]["content-type"] = content_type
    with pytest.raises(InvalidClientMetadata):
        run(ClientMetadataResolver())


@pytest.mark.parametrize("directive", ["no-store", "no-cache", "max-age=0", "max-age=invalid"])
def test_cache_directives_are_honored(metadata_server, directive):
    metadata_server[0]["headers"]["cache-control"] = directive
    resolver = ClientMetadataResolver()
    run(resolver)
    run(resolver)
    assert len(metadata_server[1]) == 2


def test_cache_expiry_size_and_age(metadata_server):
    state, requests = metadata_server
    state["headers"].update({"cache-control": "max-age=10", "age": "10"})
    resolver = ClientMetadataResolver()
    run(resolver)
    assert not resolver.cache
    state["headers"].clear()
    state["headers"]["content-type"] = "application/json"
    resolver.cache.update({str(i): (float("inf"), {}) for i in range(128)})
    run(resolver)
    assert len(resolver.cache) == 128 and "0" not in resolver.cache
    resolver.cache[CLIENT] = (0, METADATA)
    run(resolver)
    assert len(requests) == 3


def test_dns_timeout_is_closed(metadata_server, monkeypatch):
    async def fail(*args, **kwargs):
        raise TimeoutError()

    monkeypatch.setattr(anyio, "getaddrinfo", fail)
    with pytest.raises(InvalidClientMetadata):
        run(ClientMetadataResolver())


def test_total_deadline_interrupts_dns(metadata_server, monkeypatch):
    fail_after = anyio.fail_after

    def short_deadline(seconds):
        assert seconds == 5
        return fail_after(0.01)

    async def slow(*args, **kwargs):
        await anyio.sleep(1)

    monkeypatch.setattr(anyio, "fail_after", short_deadline)
    monkeypatch.setattr(anyio, "getaddrinfo", slow)
    with pytest.raises(InvalidClientMetadata):
        run(ClientMetadataResolver())


def test_tls_failure_is_closed(metadata_server):
    metadata_server[0]["error"] = httpx.ConnectError("TLS failed")
    with pytest.raises(InvalidClientMetadata):
        run(ClientMetadataResolver())


def test_compressed_metadata_is_rejected_before_decoding(metadata_server):
    metadata_server[0]["headers"]["content-encoding"] = "gzip"
    with pytest.raises(InvalidClientMetadata):
        run(ClientMetadataResolver())


def test_http_stack_connects_to_checked_ip_and_verifies_hostname(monkeypatch):
    observed = []
    body = json.dumps(METADATA).encode()

    class Stream(httpcore.AsyncNetworkStream):
        async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
            observed.append((server_hostname, ssl_context.check_hostname, ssl_context.verify_mode))
            return self

        async def write(self, buffer, timeout=None):
            observed.append(buffer)

        async def read(self, max_bytes, timeout=None):
            if not hasattr(self, "sent"):
                self.sent = True
                return (
                    b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
                    + str(len(body)).encode()
                    + b"\r\n\r\n"
                    + body
                )
            return b""

        async def aclose(self):
            pass

    async def resolve(host, port, **kwargs):
        observed.append((host, port))
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", port))]

    async def connect(self, host, port, **kwargs):
        observed.append((host, port))
        return Stream()

    monkeypatch.setattr(anyio, "getaddrinfo", resolve)
    monkeypatch.setattr(AnyIOBackend, "connect_tcp", connect)
    assert run(ClientMetadataResolver()) == METADATA
    assert observed[:3] == [
        ("client.example", 443),
        ("8.8.8.8", 443),
        ("client.example", True, ssl.CERT_REQUIRED),
    ]
    assert b"host: client.example" in observed[3].lower()
