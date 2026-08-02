"""Tests for WattBoxAsyncDriver against scripted WB-800-IPVM-6 behaviour.

These cover the three ways the IP driver fails on 800-series hardware:

* the device does not echo commands over raw telnet
* replies may contain spaces, commas, braces and parentheses
* some requests are answered with ``#Error`` rather than a value
"""

from __future__ import annotations

import pytest

from .conftest import FakeDevice
from .fixtures import CONTROL_OK, ERROR_REPLIES, OUTLET_NAMES, WB800_IPVM_6

pytestmark = pytest.mark.asyncio


async def test_telnet_no_echo_returns_value(make_driver) -> None:
    """The core 800-series regression.

    Over raw telnet these units send only the reply line. The driver used to
    guard this case with ``self.transport not in ("telnet", "asynctelnet")``,
    but ``self.transport`` is a transport *object*, never a string, so the
    guard was always true and the driver issued a second read that blocked
    until the operation timeout.
    """
    driver = make_driver(FakeDevice(WB800_IPVM_6, echo=False), transport="asynctelnet")

    response = await driver._send_command("?Model")

    assert response.result == "WB-800-IPVM-6"
    assert not response.failed


async def test_telnet_outlet_name_with_spaces_is_not_truncated(make_driver) -> None:
    """``?OutletName`` is polled on every update cycle."""
    driver = make_driver(FakeDevice(WB800_IPVM_6, echo=False), transport="asynctelnet")

    response = await driver._send_command("?OutletName")

    expected = ",".join("{" + n + "}" for n in OUTLET_NAMES)
    assert response.result == expected
    assert "Media Bridge 1 to 3" in response.result


async def test_ssh_with_echo_returns_value(make_driver) -> None:
    """The SSH path echoes; the reply must still be located correctly."""
    driver = make_driver(FakeDevice(WB800_IPVM_6, echo=True), transport="asyncssh")

    response = await driver._send_command("?Firmware")

    assert response.result == "2.10.0.0"


async def test_error_reply_is_reported_not_hung(make_driver) -> None:
    """An ``#Error`` reply must be flagged, not waited out.

    WB-800-IPVM-6 on fw 2.10.0.0 was never observed returning ``#Error`` for
    any read-only request, but the protocol documents it and other integrators
    report it, so the path is pinned here with a synthetic reply.
    """
    driver = make_driver(
        FakeDevice({**WB800_IPVM_6, **ERROR_REPLIES}, echo=False),
        transport="asynctelnet",
    )

    response = await driver._send_command("?UPSStatus")

    assert response.failed, "an #Error reply must mark the response failed"


async def test_reply_split_across_packets(make_driver) -> None:
    """A long reply arriving in several TCP segments must be reassembled."""
    device = FakeDevice(WB800_IPVM_6, echo=False, chunk_size=8)
    driver = make_driver(device, transport="asynctelnet")

    response = await driver._send_command("?OutletName")

    expected = ",".join("{" + n + "}" for n in OUTLET_NAMES)
    assert response.result == expected


async def test_control_message_returns_ok(make_driver) -> None:
    """Control messages answer ``OK`` rather than ``?Key=value``."""
    driver = make_driver(
        FakeDevice({**WB800_IPVM_6, **CONTROL_OK}, echo=False), transport="asynctelnet"
    )

    response = await driver._send_command("!OutletSet=1,ON,0")

    assert response.result == "OK"
    assert not response.failed


async def test_outlet_power_status_indexed_reply(make_driver) -> None:
    driver = make_driver(FakeDevice(WB800_IPVM_6, echo=False), transport="asynctelnet")

    response = await driver._send_command("?OutletPowerStatus=2")

    assert response.result == "2,21.40,0.18,119.88"
