"""A small aiohttp stand-in for the provider tests.

`aioresponses` used to fill this role. It builds real `aiohttp.ClientResponse`
objects, so it breaks whenever aiohttp changes that constructor — and aiohttp
3.14 did exactly that (`stream_writer` became a required keyword argument),
which pinned the whole test suite to an aiohttp old enough to strand us on a
Home Assistant below this integration's own 2026.3 floor.

This double never touches aiohttp internals. It swaps out
`aiohttp.ClientSession` for the duration of a `with` block and hands back a
response object implementing the two things every provider calls on one:
`raise_for_status()` and `await json()`. The only aiohttp import is
`ClientResponseError`, so that error-path tests still assert against the real
exception type.

Usage mirrors what the tests already did::

    with mock_http() as m:
        m.get(f"{BASE_URL}/getListings", payload=[{"_id": "listing-1"}])
        await provider.get_properties()

Matching is on method plus URL, where the URL is either an exact string or a
compiled regex. Query strings are ignored when matching and recorded in the
call log instead — providers pass their query as `params=`, which the tests
assert on there. A request that matches no registered route raises, so a
provider quietly calling an unexpected endpoint fails the test rather than
hanging or returning `None`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any
from unittest.mock import patch

from aiohttp import ClientResponseError, RequestInfo
from multidict import CIMultiDict, CIMultiDictProxy
from yarl import URL


@dataclass(frozen=True)
class Call:
    """One recorded request. `kwargs` holds headers/params/json as passed."""

    method: str
    url: str
    kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass
class _Route:
    method: str
    url: str | re.Pattern[str]
    payload: Any
    status: int

    def matches(self, method: str, url: str) -> bool:
        if method != self.method:
            return False
        if isinstance(self.url, re.Pattern):
            return self.url.match(url) is not None
        return url == self.url


class _MockResponse:
    """The object a provider gets back from `async with session.get(...)`."""

    def __init__(self, method: str, url: str, payload: Any, status: int) -> None:
        self._method = method
        self._url = url
        self._payload = payload
        self.status = status

    async def __aenter__(self) -> _MockResponse:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    def raise_for_status(self) -> None:
        if self.status < 400:
            return
        raise ClientResponseError(
            request_info=_request_info(self._method, self._url),
            history=(),
            status=self.status,
            message=f"mock {self.status}",
        )

    async def json(self, **_kwargs: Any) -> Any:
        return self._payload

    async def text(self, **_kwargs: Any) -> str:
        return str(self._payload)


def _request_info(method: str, url: str) -> RequestInfo:
    """The RequestInfo aiohttp attaches to a ClientResponseError."""
    parsed = URL(url)
    return RequestInfo(
        url=parsed,
        method=method,
        headers=CIMultiDictProxy(CIMultiDict()),
        real_url=parsed,
    )


class _MockSession:
    """Replaces `aiohttp.ClientSession` — an async CM yielding itself."""

    def __init__(self, mocker: HttpMock, *_args: Any, **_kwargs: Any) -> None:
        self._mocker = mocker

    async def __aenter__(self) -> _MockSession:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    async def close(self) -> None:
        return None

    def get(self, url: str, **kwargs: Any) -> _MockResponse:
        return self._mocker._handle("GET", url, kwargs)

    def post(self, url: str, **kwargs: Any) -> _MockResponse:
        return self._mocker._handle("POST", url, kwargs)

    def put(self, url: str, **kwargs: Any) -> _MockResponse:
        return self._mocker._handle("PUT", url, kwargs)


class HttpMock:
    """Route registry plus call log, handed to the test by `mock_http()`."""

    def __init__(self) -> None:
        self._routes: list[_Route] = []
        self.requests: dict[tuple[str, str], list[Call]] = {}

    def get(self, url: str | re.Pattern[str], *, payload: Any = None, status: int = 200) -> None:
        self._routes.append(_Route("GET", url, payload, status))

    def post(self, url: str | re.Pattern[str], *, payload: Any = None, status: int = 200) -> None:
        self._routes.append(_Route("POST", url, payload, status))

    def put(self, url: str | re.Pattern[str], *, payload: Any = None, status: int = 200) -> None:
        self._routes.append(_Route("PUT", url, payload, status))

    def _handle(self, method: str, url: str, kwargs: dict[str, Any]) -> _MockResponse:
        bare = str(URL(url).with_query(None))
        self.requests.setdefault((method, bare), []).append(Call(method, url, kwargs))

        for route in self._routes:
            if route.matches(method, bare):
                return _MockResponse(method, url, route.payload, route.status)

        registered = "\n  ".join(
            f"{r.method} {r.url.pattern if isinstance(r.url, re.Pattern) else r.url}"
            for r in self._routes
        ) or "(none)"
        raise AssertionError(
            f"Unexpected request {method} {bare}\nRegistered routes:\n  {registered}"
        )


def mock_http():
    """Patch `aiohttp.ClientSession` for the block, yielding an `HttpMock`."""
    mocker = HttpMock()
    return _MockHttpContext(mocker)


class _MockHttpContext:
    def __init__(self, mocker: HttpMock) -> None:
        self._mocker = mocker
        self._patcher = patch(
            "aiohttp.ClientSession",
            side_effect=lambda *a, **kw: _MockSession(mocker, *a, **kw),
        )

    def __enter__(self) -> HttpMock:
        self._patcher.start()
        return self._mocker

    def __exit__(self, *exc_info: object) -> None:
        self._patcher.stop()
