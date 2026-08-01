"""End-to-end tests for IpWattBox against a scripted WB-800-IPVM-6.

Covers the two calls Home Assistant makes: ``async_get_initial`` at setup and
``async_update`` on every poll.
"""

from __future__ import annotations

import pytest

from pywattbox.ip_wattbox import IpWattBox

from .conftest import FakeDevice
from .fixtures import OUTLET_NAMES, WB800_IPVM_6

pytestmark = pytest.mark.asyncio


@pytest.fixture
def wattbox(make_driver):
    """An IpWattBox whose async driver is wired to a scripted device."""

    def _build(replies=None, *, echo: bool = False, chunk_size: int | None = None):
        device = FakeDevice(replies or WB800_IPVM_6, echo=echo, chunk_size=chunk_size)
        box = IpWattBox(host="192.0.2.1", user="admin", password="secret", port=23)
        box._async_driver = make_driver(device, transport="asynctelnet")
        return box, device

    return _build


async def test_initial_discovers_six_outlets(wattbox) -> None:
    box, _ = wattbox()

    await box.async_get_initial()

    assert box.hardware_version == "WB-800-IPVM-6"
    assert box.firmware_version == "2.10.0.0"
    assert box.serial_number == "ST000000000000"
    assert box.hostname == "WattBox"
    assert box.number_outlets == 6
    assert sorted(box.outlets) == [1, 2, 3, 4, 5, 6]
    assert box.has_ups is False


async def test_update_populates_names_status_and_power(wattbox) -> None:
    box, _ = wattbox()
    await box.async_get_initial()

    await box.async_update()

    # Names survive spaces and parentheses, and the braces are stripped.
    assert [box.outlets[i].name for i in range(1, 7)] == list(OUTLET_NAMES)
    assert [box.outlets[i].status for i in range(1, 7)] == [
        True,
        True,
        True,
        True,
        True,
        False,
    ]
    assert box.current_value == 0.4
    assert box.power_value == 48.0
    assert box.voltage_value == 120.0
    assert box.outlets[2].power_value == 21.4
    assert box.outlets[2].voltage_value == 120.0


async def test_update_skips_ups_request_without_a_ups(wattbox) -> None:
    """A unit with no UPS must not be asked for UPS status.

    Asking wastes a round trip on every poll and returns a reply that
    ``parse_ups_status`` cannot handle -- which aborted the entire update.
    """
    box, device = wattbox()
    await box.async_get_initial()
    device.received.clear()

    await box.async_update()

    assert "?UPSStatus" not in device.received


async def test_update_requests_ups_status_when_a_ups_is_present(wattbox) -> None:
    replies = {
        **WB800_IPVM_6,
        "?UPSConnection": b"?UPSConnection=1\n",
        "?UPSStatus": b"?UPSStatus=100,12,Good,False,45,False,False\n",
    }
    box, device = wattbox(replies)
    await box.async_get_initial()
    assert box.has_ups is True

    await box.async_update()

    assert "?UPSStatus" in device.received
    assert box.battery_charge == 100
    assert box.battery_health is True
    assert box.power_lost is False
    assert box.est_run_time == 45


async def test_update_works_when_replies_are_fragmented(wattbox) -> None:
    """Every reply arriving in 8-byte segments must still parse."""
    box, _ = wattbox(chunk_size=8)
    await box.async_get_initial()

    await box.async_update()

    assert box.outlets[1].name == "Media Bridge 1 to 3"
    assert box.power_value == 48.0


async def test_update_works_over_an_echoing_transport(wattbox) -> None:
    """SSH echoes commands; the indexed per-outlet replies are the risk.

    The echo of ``?OutletPowerStatus=1`` is itself a valid ``key=value`` line,
    so a parser taking the first match reads the echo instead of the reading.
    """
    box, _ = wattbox(echo=True)
    await box.async_get_initial()

    await box.async_update()

    assert box.outlets[1].power_value == 17.9
    assert box.outlets[6].power_value == 0.0
