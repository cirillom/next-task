"""Fetch public-client metadata without allowing access to internal hosts."""

import ipaddress
import json
import socket
import time
from collections import OrderedDict
from urllib.parse import urlsplit, urlunsplit

import anyio
import httpx
from mcp.shared.auth import OAuthClientMetadata


class InvalidClientMetadata(ValueError):
    pass


def _https_url(value: str, *, path_required: bool = False) -> bool:
    try:
        url = urlsplit(value)
        port = url.port
        return bool(
            url.scheme == "https"
            and url.hostname
            and (not path_required or port in (None, 443))
            and url.username is None
            and url.password is None
            and not url.fragment
            and "#" not in value
            and not any(char.isspace() or ord(char) < 32 for char in value)
            and "*" not in url.hostname
            and (not path_required or url.path and url.path != "/")
        )
    except ValueError:
        return False


def _validate(client_id: str, data: object) -> dict:
    if not isinstance(data, dict) or data.get("client_id") != client_id:
        raise InvalidClientMetadata()
    OAuthClientMetadata.model_validate(data)
    redirects = data.get("redirect_uris")
    if (
        not isinstance(data.get("client_name"), str)
        or not data["client_name"].strip()
        or not isinstance(redirects, list)
        or not redirects
        or not all(isinstance(uri, str) and _https_url(uri) for uri in redirects)
        or data.get("token_endpoint_auth_method", "client_secret_basic") != "none"
        or any(
            not isinstance(data[key], list) or not all(isinstance(item, str) for item in data[key])
            for key in ("grant_types", "response_types")
            if key in data
        )
    ):
        raise InvalidClientMetadata()
    return data


class ClientMetadataResolver:
    def __init__(self):
        self.cache: OrderedDict[str, tuple[float, dict]] = OrderedDict()

    async def resolve(self, client_id: str) -> dict:
        if not isinstance(client_id, str) or not _https_url(client_id, path_required=True):
            raise InvalidClientMetadata()
        cached = self.cache.get(client_id)
        if cached and cached[0] > time.monotonic():
            self.cache.move_to_end(client_id)
            return cached[1]
        self.cache.pop(client_id, None)
        url = urlsplit(client_id)
        if url.hostname.lower().rstrip(".").endswith((".localhost", ".local", ".internal")):
            raise InvalidClientMetadata()
        try:
            with anyio.fail_after(5):
                addresses = await anyio.getaddrinfo(url.hostname, 443, type=socket.SOCK_STREAM)
                ips = {ipaddress.ip_address(address[4][0]) for address in addresses}
                if not ips or any(not ip.is_global for ip in ips):
                    raise InvalidClientMetadata()
                ip = sorted(ips, key=str)[0]
                host = url.hostname.encode("idna").decode("ascii")
                authority = f"[{ip}]" if ip.version == 6 else str(ip)
                target = urlunsplit(("https", authority, url.path, url.query, ""))
                async with (
                    httpx.AsyncClient(trust_env=False, follow_redirects=False) as client,
                    client.stream(
                        "GET",
                        target,
                        headers={"Host": url.netloc, "Accept-Encoding": "identity"},
                        extensions={"sni_hostname": host},
                    ) as response,
                ):
                    if (
                        response.status_code != 200
                        or response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                        != "application/json"
                        or response.headers.get("content-encoding", "identity").lower()
                        != "identity"
                    ):
                        raise InvalidClientMetadata()
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > 65536:
                            raise InvalidClientMetadata()
                    data = _validate(client_id, json.loads(body))
                    directives = response.headers.get("cache-control", "").lower().split(",")
                    ttl = 300
                    for directive in directives:
                        name, _, value = directive.strip().partition("=")
                        if name in ("no-store", "no-cache", "private"):
                            ttl = 0
                        elif name in ("max-age", "s-maxage"):
                            try:
                                ttl = min(ttl, max(0, int(value.strip('"'))))
                            except ValueError:
                                ttl = 0
                    try:
                        ttl = max(0, ttl - max(0, int(response.headers.get("age", "0"))))
                    except ValueError:
                        ttl = 0
                    if ttl:
                        self.cache[client_id] = (time.monotonic() + ttl, data)
                        if len(self.cache) > 128:
                            self.cache.popitem(last=False)
                    return data
        except (
            OSError,
            TimeoutError,
            httpx.HTTPError,
            httpx.InvalidURL,
            UnicodeError,
            ValueError,
        ) as exc:
            raise InvalidClientMetadata() from exc
