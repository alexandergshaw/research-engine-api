"""Resilient outbound HTTP: shared client, retries, and per-source circuit breakers.

This is the resilience backbone. Every connector fetches through one shared
``HttpClient`` so that timeouts, retry/backoff, and circuit-breaker state are
applied uniformly and a misbehaving source is isolated from the rest.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import httpx
import pybreaker
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class UpstreamError(Exception):
    """Base class for upstream-source failures."""

    def __init__(self, message: str, *, source: str | None = None, status: int | None = None):
        super().__init__(message)
        self.source = source
        self.status = status


class RetryableUpstream(UpstreamError):
    """Transient failure (timeout, 5xx, 429, open breaker) — safe to retry/skip."""


class NotFoundUpstream(UpstreamError):
    """The source has no data for this query (404). Not a source failure."""


def _is_client_error(exc: BaseException) -> bool:
    """Predicate for breaker ``exclude``: client-side errors must not open the breaker."""
    if isinstance(exc, NotFoundUpstream):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return 400 <= exc.response.status_code < 500
    return False


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


class HttpClient:
    def __init__(
        self,
        *,
        user_agent: str,
        timeout: float,
        max_retries: int = 3,
        breaker_fail_max: int = 5,
        breaker_reset_timeout: int = 60,
    ):
        self._client = httpx.Client(
            headers={"User-Agent": user_agent},
            timeout=timeout,
            follow_redirects=True,
        )
        self._max_retries = max_retries
        self._breaker_fail_max = breaker_fail_max
        self._breaker_reset_timeout = breaker_reset_timeout
        self._breakers: dict[str, pybreaker.CircuitBreaker] = {}
        self._lock = threading.Lock()

    # -- circuit breakers --------------------------------------------------
    def breaker(self, name: str) -> pybreaker.CircuitBreaker:
        with self._lock:
            brk = self._breakers.get(name)
            if brk is None:
                brk = pybreaker.CircuitBreaker(
                    fail_max=self._breaker_fail_max,
                    reset_timeout=self._breaker_reset_timeout,
                    name=name,
                    exclude=[_is_client_error],
                )
                self._breakers[name] = brk
            return brk

    def breaker_open(self, name: str) -> bool:
        return self.breaker(name).current_state == pybreaker.STATE_OPEN

    # -- requests ----------------------------------------------------------
    def get_json(
        self,
        source: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> Any:
        return self.request(
            "GET", source, url, params=params, headers=headers, timeout=timeout
        ).json()

    def get_text(
        self,
        source: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> str:
        return self.request(
            "GET", source, url, params=params, headers=headers, timeout=timeout
        ).text

    def request(
        self,
        method: str,
        source: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        json: Any | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        """Resilient request returning the raw Response (retries + breaker applied).

        ``timeout`` overrides the client default for this call (e.g. bulk downloads).
        """
        breaker = self.breaker(source)

        def _guarded() -> httpx.Response:
            return self._with_retry(
                method, source, url, params=params, headers=headers, json=json, timeout=timeout
            )

        try:
            return breaker.call(_guarded)
        except pybreaker.CircuitBreakerError as exc:
            raise RetryableUpstream(f"{source}: circuit open", source=source) from exc

    def _with_retry(self, method, source, url, *, params, headers, json, timeout) -> httpx.Response:
        retryer = Retrying(
            reraise=True,
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential_jitter(initial=0.3, max=4.0),
            retry=retry_if_exception_type((httpx.TransportError, RetryableUpstream)),
        )
        return retryer(self._send_once, method, source, url, params, headers, json, timeout)

    def _send_once(self, method, source, url, params, headers, json, timeout) -> httpx.Response:
        timeout_arg = httpx.USE_CLIENT_DEFAULT if timeout is None else timeout
        resp = self._client.request(
            method, url, params=params, headers=headers, json=json, timeout=timeout_arg
        )
        status = resp.status_code
        if status in _RETRYABLE_STATUS:
            delay = _parse_retry_after(resp.headers.get("Retry-After"))
            if delay:
                time.sleep(min(delay, 5.0))
            raise RetryableUpstream(f"{source}: HTTP {status}", source=source, status=status)
        if status == 404:
            raise NotFoundUpstream(f"{source}: not found", source=source, status=404)
        resp.raise_for_status()  # other 4xx -> HTTPStatusError (excluded from breaker)
        return resp

    def close(self) -> None:
        self._client.close()
