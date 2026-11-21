"""Builds the ``httpx`` client: timeouts, pool, TLS, proxies and the hosts that skip them."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    import httpx

    from rayohx.config import NetworkConfig


def no_proxy_mounts(entries: Iterable[str]) -> dict[str, None]:
    """``httpx`` mounts that send the hosts listed in ``NO_PROXY`` straight out, with no proxy."""
    mounts: dict[str, None] = {}
    for entry in entries:
        if entry == "*":
            mounts["all://"] = None
            continue
        host = entry.lstrip("*").lstrip(".").split(":")[0]
        if host and "/" not in host and "[" not in host:  # no CIDR ranges or IPv6
            mounts[f"all://{host}"] = None
            mounts[f"all://*.{host}"] = None
    return mounts


def build_client(
    config: NetworkConfig, *, pool_size: int, transport: httpx.BaseTransport | None = None
) -> httpx.Client:
    """The ``httpx`` client for ``config``.

    Redirects are left to the caller, which follows them hop by hop, and the environment is never
    read here: proxies come from the configuration, or from the environment only when
    ``proxy_from_env`` is on and no explicit proxy is set.
    """
    import httpx

    from rayohx._http._common import environment_proxies, proxy_url, tls_context

    timeout = httpx.Timeout(
        connect=config.connect_timeout,
        read=config.read_timeout,
        write=config.read_timeout,
        pool=config.connect_timeout,
    )
    limits = httpx.Limits(max_connections=pool_size, max_keepalive_connections=pool_size)
    tls = tls_context(
        config.verify_tls, config.client_cert, config.client_key, config.client_key_password
    )
    mounts: dict[str, httpx.BaseTransport | None] = {}
    if config.proxy is None and config.proxy_from_env and transport is None:
        proxies, no_proxy = environment_proxies()
        for scheme, found in proxies.items():
            mounts[f"{scheme}://"] = httpx.HTTPTransport(
                verify=tls, limits=limits, proxy=proxy_url(found)
            )
        if proxies:
            mounts.update(no_proxy_mounts(no_proxy))
    return httpx.Client(
        transport=transport,
        mounts=mounts or None,
        timeout=timeout,
        limits=limits,
        verify=tls,
        proxy=proxy_url(config.proxy) if config.proxy else None,
        follow_redirects=False,  # redirects are followed by the caller, hop by hop
        trust_env=False,  # settings come from the config, never from hidden variables
    )
