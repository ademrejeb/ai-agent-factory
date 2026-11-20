"""Outbound URL policy for provider connections and graph HTTP nodes.

Operators configure provider roots and HTTP nodes, but that is still
server-side egress. Reject loopback, private, link-local/metadata and reserved
targets unless the deployment explicitly allows internal providers.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

from app.errors import AppError


def _reject(message: str) -> None:
    raise AppError("invalid_url", message, 400)


def _check_address(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address, *, allow_private: bool
) -> None:
    # Link-local covers the 169.254.169.254 metadata endpoint and must never be
    # allowed, even when internal providers are enabled.
    if address.is_link_local or address.is_multicast:
        _reject("Outbound URLs cannot target link-local or multicast addresses.")
    if address.is_unspecified:
        _reject("Outbound URLs cannot target an unspecified address.")
    if allow_private and (address.is_private or address.is_loopback):
        return
    if address.is_reserved:
        _reject("Outbound URLs cannot target reserved addresses.")


def validate_outbound_url(
    url: str,
    *,
    allow_private: bool,
    label: str = "URL",
    require_https: bool = False,
) -> str:
    parts = urlsplit(str(url).strip())
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        _reject(f"{label} must be an absolute http(s) URL.")
    if parts.username or parts.password:
        _reject(f"{label} must not contain userinfo.")
    if parts.fragment:
        _reject(f"{label} must not contain a fragment.")
    if require_https and parts.scheme != "https":
        _reject(f"{label} must use HTTPS.")

    host = parts.hostname
    try:
        infos = socket.getaddrinfo(host, parts.port or (443 if parts.scheme == "https" else 80))
    except OSError as exc:
        raise AppError("invalid_url", f"{label} host could not be resolved.", 400) from exc

    resolved: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for info in infos:
        try:
            resolved.append(ipaddress.ip_address(info[4][0]))
        except ValueError:
            continue
    if not resolved:
        _reject(f"{label} host could not be resolved to an IP address.")

    for address in resolved:
        _check_address(address, allow_private=allow_private)
        if address.is_global:
            continue
        if allow_private and (address.is_private or address.is_loopback):
            continue
        _reject(
            f"{label} cannot target {address}. "
            "Set ALLOW_PRIVATE_PROVIDER_URLS=true only for trusted internal services."
        )
    return str(url).strip()
