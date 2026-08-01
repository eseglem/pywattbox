"""Tests for the synchronous WattBoxDriver.

The sync driver carried exactly the same defects as the async one. It is not
used by Home Assistant, which is presumably why it has been overlooked, but
leaving the two implementations divergent is what allowed the bug to persist in
one of them -- so the behaviour is pinned here too.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import pytest
from scrapli.exceptions import ScrapliTimeout

from pywattbox.driver.sync_driver import WattBoxDriver

from .conftest import FakeDevice
from .fixtures import OUTLET_NAMES, WB800_IPVM_6


class SyncFakeChannel:
    """Synchronous counterpart to conftest.FakeChannel."""

    def __init__(self, device: FakeDevice) -> None:
        self.device = device
        self._pending: list[bytes] = []
        self._partial_command = ""

    @contextmanager
    def _channel_lock(self):
        yield

    def write(self, channel_input: str, **_kwargs: Any) -> None:
        self._partial_command += channel_input

    def send_return(self) -> None:
        command, self._partial_command = self._partial_command, ""
        self._pending.extend(self.device.feed(command))

    def read(self) -> bytes:
        if not self._pending:
            raise ScrapliTimeout("no more data from device")
        return self._pending.pop(0)


@pytest.fixture
def make_sync_driver():
    def _make(device: FakeDevice) -> WattBoxDriver:
        driver = WattBoxDriver(
            host="192.0.2.1",
            port=23,
            auth_username="admin",
            auth_password="secret",
            transport="telnet",
        )
        driver.channel = SyncFakeChannel(device)  # type: ignore[assignment]
        driver._open = lambda force=False: None  # type: ignore[assignment]
        return driver

    return _make


def test_no_echo_returns_value(make_sync_driver) -> None:
    driver = make_sync_driver(FakeDevice(WB800_IPVM_6, echo=False))

    response = driver._send_command("?Model")

    assert response.result == "WB-800-IPVM-6"
    assert not response.failed


def test_outlet_name_with_spaces_is_not_truncated(make_sync_driver) -> None:
    driver = make_sync_driver(FakeDevice(WB800_IPVM_6, echo=False))

    response = driver._send_command("?OutletName")

    assert response.result == ",".join("{" + n + "}" for n in OUTLET_NAMES)


def test_error_reply_is_flagged(make_sync_driver) -> None:
    driver = make_sync_driver(FakeDevice(WB800_IPVM_6, echo=False))

    response = driver._send_command("?UPSStatus")

    assert response.failed


def test_reply_split_across_packets(make_sync_driver) -> None:
    driver = make_sync_driver(FakeDevice(WB800_IPVM_6, echo=False, chunk_size=8))

    response = driver._send_command("?OutletName")

    assert response.result == ",".join("{" + n + "}" for n in OUTLET_NAMES)


def test_silent_device_raises_rather_than_returning_garbage(make_sync_driver) -> None:
    """A request the device ignores must surface as a timeout.

    Returning an empty result instead would push the failure downstream into
    float()/int() parsing, where the cause is far harder to see.
    """
    driver = make_sync_driver(FakeDevice({}, echo=False))

    with pytest.raises(ScrapliTimeout):
        driver._send_command("?Model")


def test_telnet_transport_bypasses_scrapli_auth() -> None:
    """Telnet auth is handled in on_open, so transport auth must be bypassed."""
    driver = WattBoxDriver(
        host="192.0.2.1",
        port=23,
        auth_username="admin",
        auth_password="secret",
        transport="telnet",
    )

    assert driver.auth_bypass is True
