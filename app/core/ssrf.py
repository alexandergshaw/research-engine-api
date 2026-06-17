"""SSRF guard for the caller-supplied dynamic source (``feed.poll``).

The dynamic-source connector fetches a URL the *caller* provides, which is a
classic server-side request forgery vector (cloud metadata at 169.254.169.254,
``localhost``, internal services). Every outbound dynamic fetch is validated
here first: scheme is restricted, an optional host allowlist is enforced, and —
unless explicitly disabled — the host is resolved and rejected if any resolved
address is private/loopback/link-local/reserved.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class SsrfError(ValueError):
    """The caller-supplied URL is not allowed to be fetched."""


def _host_allowed(host: str, allowlist: frozenset[str]) -> bool:
    host = host.lower()
    for entry in allowlist:
        entry = entry.lower().lstrip(".")
        if host == entry or host.endswith("." + entry):
            return True
    return False


def _is_blocked_ip(ip: ipaddress._BaseAddress) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local  # incl. 169.254.169.254 cloud metadata
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _resolve_ips(host: str) -> list[ipaddress._BaseAddress]:
    """Resolved IPs for ``host`` (the IP itself if it's already a literal)."""
    try:
        return [ipaddress.ip_address(host)]
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise SsrfError(f"cannot resolve host '{host}'") from exc
    ips: list[ipaddress._BaseAddress] = []
    for info in infos:
        addr = info[4][0]
        try:
            ips.append(ipaddress.ip_address(addr))
        except ValueError:
            continue
    if not ips:
        raise SsrfError(f"cannot resolve host '{host}'")
    return ips


def validate_url(
    url: str,
    *,
    allow_http: bool = False,
    block_private: bool = True,
    allowlist: frozenset[str] = frozenset(),
) -> str:
    """Validate a caller-supplied URL and return its hostname, or raise ``SsrfError``."""
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise SsrfError(f"unsupported scheme '{parsed.scheme}'; use http(s)")
    if scheme == "http" and not allow_http:
        raise SsrfError("http is disabled; use https")
    host = parsed.hostname
    if not host:
        raise SsrfError("url is missing a host")
    if allowlist and not _host_allowed(host, allowlist):
        raise SsrfError(f"host '{host}' is not in the allowlist")
    if block_private:
        for ip in _resolve_ips(host):
            if _is_blocked_ip(ip):
                raise SsrfError(f"host '{host}' resolves to a blocked address ({ip})")
    return host
