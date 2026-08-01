"""Test fixtures for the WattBox IP driver.

The fake channel below mirrors the parts of ``scrapli.channel.AsyncChannel``
that the driver actually uses, and deliberately reuses scrapli's *real* prompt
matching helpers (``_get_prompt_pattern`` and ``_process_read_buf``). That
matters: the driver's bugs live in how its prompt pattern interacts with those
helpers, so a hand-rolled approximation would hide them.

Device behaviour is scripted from wire captures of real WB-800-IPVM units on
firmware 2.10.0.0 -- see tests/fixtures.py.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from io import SEEK_END, BytesIO
from typing import Callable

import pytest
from scrapli.channel.base_channel import BaseChannel, BaseChannelArgs
from scrapli.exceptions import ScrapliTimeout


class FakeDevice:
    """Scripted WattBox.

    Args:
        replies: maps a command string to the bytes the device emits in
            response. A command absent from the mapping produces no reply at
            all, which is how these units answer some unsupported requests.
        echo: whether the device echoes the command back before replying.
            The 800s do not echo over raw telnet; they do over SSH.
        chunk_size: if set, split each reply into chunks of this size to
            simulate a response arriving across several packets.
    """

    def __init__(
        self,
        replies: dict[str, bytes],
        *,
        echo: bool = False,
        chunk_size: int | None = None,
    ) -> None:
        self.replies = replies
        self.echo = echo
        self.chunk_size = chunk_size
        self.received: list[str] = []

    def feed(self, command: str) -> list[bytes]:
        """Return the chunks the device would put on the wire for *command*."""
        self.received.append(command)
        out = b""
        if self.echo:
            out += command.encode() + b"\r\n"
        out += self.replies.get(command, b"")
        if not out:
            return []
        if self.chunk_size:
            return [
                out[i : i + self.chunk_size]
                for i in range(0, len(out), self.chunk_size)
            ]
        return [out]


class FakeChannel:
    """Stand-in for scrapli's AsyncChannel, backed by a FakeDevice."""

    def __init__(self, device: FakeDevice, comms_prompt_pattern: str) -> None:
        self.device = device
        self._pending: list[bytes] = []
        self._partial_command = ""
        self._channel_args = BaseChannelArgs(comms_prompt_pattern=comms_prompt_pattern)
        # BaseChannel._process_read_buf only touches _base_channel_args, so a
        # minimal stand-in is enough to borrow the real implementation.
        self._search_depth = self._channel_args.comms_prompt_search_depth

    # -- scrapli Channel surface used by the driver -------------------------
    @asynccontextmanager
    async def _channel_lock(self):
        yield

    def write(self, channel_input: str, **_kwargs) -> None:
        self._partial_command += channel_input

    def send_return(self) -> None:
        command, self._partial_command = self._partial_command, ""
        self._pending.extend(self.device.feed(command))

    async def read(self) -> bytes:
        """Return the next chunk, or time out if the device has gone quiet.

        A real transport blocks here until data arrives or the transport
        timeout fires; raising ScrapliTimeout is the faithful equivalent and
        keeps a hung driver from hanging the test suite.
        """
        if not self._pending:
            raise ScrapliTimeout("no more data from device")
        await asyncio.sleep(0)
        return self._pending.pop(0)

    async def _read_until_prompt(self, buf: bytes = b"") -> bytes:
        """Faithful copy of scrapli's AsyncChannel._read_until_prompt."""
        search_pattern = BaseChannel._get_prompt_pattern(
            class_pattern=self._channel_args.comms_prompt_pattern
        )
        read_buf = BytesIO(buf)
        while True:
            read_buf.write(await self.read())
            search_buf = self._process_read_buf(read_buf)
            if search_pattern.search(search_buf):
                return read_buf.getvalue()

    def _process_read_buf(self, read_buf: BytesIO) -> bytes:
        """Faithful copy of scrapli's BaseChannel._process_read_buf."""
        read_buf.seek(-self._search_depth, SEEK_END)
        search_buf = read_buf.read()
        before, _, search_buf = search_buf.partition(b"\n")
        if not search_buf:
            search_buf = before
        return search_buf


@pytest.fixture
def make_driver() -> Callable:
    """Build a WattBoxAsyncDriver wired to a FakeDevice, with no real socket."""
    from pywattbox.driver.async_driver import WattBoxAsyncDriver

    def _make(device: FakeDevice, transport: str = "asynctelnet") -> WattBoxAsyncDriver:
        driver = WattBoxAsyncDriver(
            host="192.0.2.1",
            port=23 if transport == "asynctelnet" else 22,
            auth_username="admin",
            auth_password="secret",
            transport=transport,
        )
        driver._fake_channel = FakeChannel(  # type: ignore[attr-defined]
            device, driver.channel._base_channel_args.comms_prompt_pattern
        )
        driver.channel = driver._fake_channel  # type: ignore[assignment]

        async def _noop_open(force: bool = False) -> None:
            return None

        driver._open = _noop_open  # type: ignore[assignment]
        return driver

    return _make
