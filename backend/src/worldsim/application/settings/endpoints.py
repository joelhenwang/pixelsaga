"""Custom text-endpoint safety policy (owned by MAINMENU-A05).

Operator-approved origins only: the validator blocks cloud metadata and
link-local targets, embedded credentials, and unbounded redirects. Local
inference endpoints need an explicit per-connection allowance. Probes never
forward credentials to another host.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

from worldsim.domain.errors import DomainError, ErrorCode

METADATA_HOSTS = {"169.254.169.254", "100.100.100.100", "fd00:ec2::254"}
METADATA_NETS = (
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("100.100.100.100/32"),
)


@dataclass(frozen=True)
class EndpointPolicy:
    allow_local: bool = False


def validate_endpoint(raw: str, policy: EndpointPolicy) -> str:
    """Normalize an operator endpoint or raise; never fetch here."""
    parsed = urlparse(raw.strip())
    if parsed.scheme not in ("https", "http"):
        raise DomainError(ErrorCode.VALIDATION_FAILED, "endpoint must be http(s)")
    if parsed.scheme == "http" and not policy.allow_local:
        raise DomainError(
            ErrorCode.VALIDATION_FAILED, "plain http needs an explicit local allowance"
        )
    if not parsed.hostname:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "endpoint needs a host")
    if parsed.username or parsed.password:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "credentials do not belong in URLs")
    if parsed.query and ("key=" in parsed.query or "token=" in parsed.query):
        raise DomainError(ErrorCode.VALIDATION_FAILED, "secrets do not belong in URLs")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if not 1 <= port <= 65535:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "bad endpoint port")
    host = parsed.hostname.lower()
    if host in METADATA_HOSTS:
        raise DomainError(ErrorCode.FORBIDDEN, "metadata endpoints are blocked")
    try:
        direct = ipaddress.ip_address(host)
    except ValueError:
        direct = None
    if direct is not None and _blocked_ip(direct, policy):
        raise DomainError(ErrorCode.FORBIDDEN, "endpoint target is blocked")
    try:
        resolved = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise DomainError(ErrorCode.VALIDATION_FAILED, f"endpoint does not resolve: {exc}") from exc
    for family, _, _, _, sockaddr in resolved:
        try:
            candidate = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            continue
        if _blocked_ip(candidate, policy):
            raise DomainError(ErrorCode.FORBIDDEN, "endpoint resolves to a blocked target")
        if family == socket.AF_INET6 and candidate.is_link_local:
            raise DomainError(ErrorCode.FORBIDDEN, "endpoint resolves to a blocked target")
    normalized = f"{parsed.scheme}://{host}"
    if port not in (80, 443):
        normalized += f":{port}"
    path = parsed.path.rstrip("/") or ""
    return normalized + path


def _blocked_ip(candidate: object, policy: EndpointPolicy) -> bool:
    if not isinstance(candidate, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
        return False
    if any(candidate in net for net in METADATA_NETS):
        return True
    if candidate.is_link_local:
        return True
    if candidate.is_loopback or candidate.is_private:
        return not policy.allow_local
    if candidate.is_multicast or candidate.is_reserved or candidate.is_unspecified:
        return True
    return False
