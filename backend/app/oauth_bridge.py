"""Minimal Starlette adapters for Authlib's framework-independent server."""

from collections import defaultdict

from authlib.oauth2.rfc6749 import OAuth2Payload, OAuth2Request
from starlette.datastructures import FormData
from starlette.exceptions import HTTPException
from starlette.formparsers import FormParser
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class Payload(OAuth2Payload):
    def __init__(self, values):
        self._data = dict(values)
        self._datalist = defaultdict(list)
        for key, value in values.multi_items():
            self._datalist[key].append(value)

    @property
    def data(self):
        return self._data

    @property
    def datalist(self):
        return self._datalist


class OAuthRequest(OAuth2Request):
    def __init__(self, method, uri, headers, args, form):
        super().__init__(method, uri, headers=headers)
        self._args = args
        self._form = form
        self.payload = Payload(args if method == "GET" else form)

    @property
    def args(self):
        return self._args

    @property
    def form(self):
        return self._form


async def oauth_request(request: Request, issuer: str) -> OAuthRequest:
    async def bounded_stream():
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > 8192:
                raise HTTPException(status_code=413, detail="Request too large")
            yield chunk

    if request.method == "POST":
        if (
            request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            != "application/x-www-form-urlencoded"
        ):
            raise HTTPException(status_code=415, detail="Expected form data")
        form = await FormParser(request.headers, bounded_stream()).parse()
    else:
        form = FormData()
    uri = issuer + request.url.path
    if request.url.query:
        uri += "?" + request.url.query
    return OAuthRequest(request.method, uri, request.headers, request.query_params, form)


class OAuthResponse(Response):
    @property
    def location(self):
        return self.headers.get("location")

    @location.setter
    def location(self, value):
        self.headers["location"] = value


def oauth_response(status, body, headers):
    if isinstance(body, (dict, list)):
        response = JSONResponse(body, status_code=status, headers=dict(headers))
        return OAuthResponse(response.body, status_code=status, headers=dict(response.headers))
    return OAuthResponse(body or b"", status_code=status, headers=dict(headers))
