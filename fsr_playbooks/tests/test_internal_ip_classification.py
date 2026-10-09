"""Internal means "only exists inside a network" -- not Python's `is_private`.

`ipaddress` counts the RFC 5737 documentation ranges as private. Every seeded
demo alert uses a TEST-NET address as its external C2 destination, so live on
.159 the hunt's one external indicator (203.0.113.42) was refused correlation
search as "an internal (private) address", which is why the classifier must
not count documentation ranges as internal.
"""
from __future__ import annotations

import pytest

from fsr_playbooks.llm._loop_helpers import (
    _classify_ips,
    is_internal_ip,
)


@pytest.mark.parametrize("ip", [
    "10.50.60.70", "172.16.0.1", "172.31.255.254", "192.168.1.10",
    "100.64.0.1", "127.0.0.1", "169.254.1.1", "fd00::1", "fe80::1", "::1"])
def test_internal(ip):
    assert is_internal_ip(ip)


@pytest.mark.parametrize("ip", [
    "203.0.113.42", "198.51.100.7", "192.0.2.1",      # documentation: external stand-ins
    "8.8.8.8", "172.32.0.1", "2001:db8::1", "not-an-ip", ""])
def test_not_internal(ip):
    assert not is_internal_ip(ip)


def test_classify_puts_a_documentation_ip_on_the_external_side():
    internal, external = _classify_ips({"q": "10.50.60.70 -> 203.0.113.42"})
    assert internal == {"10.50.60.70"} and external == {"203.0.113.42"}
