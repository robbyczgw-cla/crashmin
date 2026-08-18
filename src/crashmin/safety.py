"""Refuse to poke remote/production systems unless the user opts in."""

from __future__ import annotations

import ipaddress
import socket

from crashmin.models import HttpRequest


class SafetyError(RuntimeError):
    pass


_LOOPBACK_NAMES = {"localhost", "localhost.localdomain"}


def _host_ips(host: str) -> list[ipaddress._BaseAddress]:
    try:
        return [ipaddress.ip_address(host)]
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SafetyError(f"cannot resolve host {host!r}: {exc}") from exc
    addresses: list[ipaddress._BaseAddress] = []
    for info in infos:
        addr = info[4][0]
        try:
            addresses.append(ipaddress.ip_address(addr))
        except ValueError:
            continue
    return addresses


def is_loopback_host(host: str) -> bool:
    if host.lower() in _LOOPBACK_NAMES:
        return True
    try:
        ips = _host_ips(host)
    except SafetyError:
        return False
    return bool(ips) and all(ip.is_loopback for ip in ips)


def classify_target(host: str) -> str:
    if is_loopback_host(host):
        return "loopback"
    try:
        ips = _host_ips(host)
    except SafetyError:
        return "unresolved"
    if not ips:
        return "unresolved"
    if all(ip.is_private or ip.is_loopback or ip.is_link_local for ip in ips):
        return "private"
    return "remote"


MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def check_target(req: HttpRequest, allow_remote: bool = False) -> None:
    kind = classify_target(req.host)
    if kind == "loopback":
        return
    if allow_remote:
        return
    raise SafetyError(
        f"refusing to send {req.method.upper()} {req.log_target()} "
        f"({kind} target). CrashMin will mutate the remote system while it "
        f"reduces. Re-run against a local or staging server, or pass "
        f"--allow-remote if you really mean it."
    )


def warn_mutating(req: HttpRequest) -> str | None:
    if req.method.upper() in MUTATING_METHODS:
        return (
            f"sending {req.method.upper()} requests during reduction; "
            "use a local/staging target and never production"
        )
    return None
