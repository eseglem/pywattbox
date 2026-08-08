from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from io import BytesIO
from typing import Any

from scrapli.decorators import timeout_modifier
from scrapli.driver import AsyncDriver
from scrapli.exceptions import ScrapliAuthenticationFailed, ScrapliConnectionNotOpened
from scrapli.response import Response

from . import PROMPTS

logger = logging.getLogger("pywattbox.async_driver")

# Transports that do not echo the command back before the response.
NON_ECHOING_TRANSPORTS = ("telnet", "asynctelnet")

# Login prompts emitted by the WattBox Integration Protocol. Neither is
# newline-terminated, so they only ever appear at the very end of the buffer.
LOGIN_PROMPT = re.compile(rb"username:\s*$", flags=re.I | re.M)
PASSWORD_PROMPT = re.compile(rb"password:\s*$", flags=re.I | re.M)


async def _read_until(
    channel: Any, pattern: re.Pattern[bytes], timeout: float
) -> bytes:
    """Read from the channel until `pattern` matches, without writing anything."""

    async def _reader() -> bytes:
        buf = b""
        while True:
            buf += await channel.read()
            if pattern.search(buf):
                return buf

    try:
        return await asyncio.wait_for(_reader(), timeout=timeout)
    except asyncio.TimeoutError as err:
        raise ScrapliAuthenticationFailed(
            f"timed out waiting for {pattern.pattern!r} during WattBox login"
        ) from err


async def on_open(driver: WattBoxAsyncDriver) -> None:
    logger.debug("On Open")

    if driver.transport_name in NON_ECHOING_TRANSPORTS:
        # We drive the login ourselves (see `auth_bypass` in __init__).
        #
        # scrapli's in-channel telnet auth periodically writes an unsolicited
        # return character to "kick" devices that need prompting. The WattBox
        # treats *every* newline as a submitted field, so a kick sent before the
        # banner arrives is consumed as an empty username: the device then jumps
        # straight to the password prompt and the real username is submitted as
        # the password, yielding `Invalid Login`. The banner takes ~1.0s on a
        # WB-800VPS-IPVM-12 while scrapli's default kick interval is
        # timeout_ops/10 = 0.5s, so this happened on every connection.
        #
        # Reading without writing keeps the device's field-by-field state
        # machine in step, and does not depend on response timing.
        timeout = getattr(driver, "timeout_ops", 30.0) or 30.0

        logger.debug("Waiting for username prompt")
        await _read_until(driver.channel, LOGIN_PROMPT, timeout)
        driver.channel.write(channel_input=driver.auth_username)
        driver.channel.send_return()

        logger.debug("Waiting for password prompt")
        await _read_until(driver.channel, PASSWORD_PROMPT, timeout)
        driver.channel.write(channel_input=driver.auth_password, redacted=True)
        driver.channel.send_return()

    # Consumes the post-login banner (`Successfully Logged In!`).
    await driver.channel._read_until_prompt()


async def on_close(driver: WattBoxAsyncDriver) -> None:
    try:
        driver.channel.write("!Exit")
        driver.channel.send_return()
    except ScrapliConnectionNotOpened:
        pass


class WattBoxAsyncDriver(AsyncDriver):
    def __init__(
        self,
        host: str,
        port: int | None = 22,
        auth_username: str = "",
        auth_password: str = "",
        auth_private_key: str = "",
        auth_private_key_passphrase: str = "",
        auth_strict_key: bool = False,
        auth_bypass: bool = False,
        timeout_socket: float = 5.0,
        timeout_transport: float = 5.0,
        timeout_ops: float = 5.0,
        comms_prompt_pattern: str = PROMPTS,
        comms_return_char: str = "\n",
        ssh_config_file: str | bool = False,
        ssh_known_hosts_file: str | bool = False,
        on_init: Callable[..., Any] | None = None,
        on_open: Callable[..., Any] | None = on_open,
        on_close: Callable[..., Any] | None = on_close,
        transport: str = "asyncssh",
        transport_options: dict[str, Any] | None = None,
        channel_log: str | bool | BytesIO = False,
        channel_log_mode: str = "write",
        channel_lock: bool = True,
        logging_uid: str = "",
    ) -> None:
        if transport in NON_ECHOING_TRANSPORTS:
            # Skip scrapli's in-channel telnet auth; `on_open` performs the
            # login instead. See the comment there for why.
            auth_bypass = True

        super().__init__(
            host=host,
            port=port,
            auth_username=auth_username,
            auth_password=auth_password,
            auth_private_key=auth_private_key,
            auth_private_key_passphrase=auth_private_key_passphrase,
            auth_strict_key=auth_strict_key,
            auth_bypass=auth_bypass,
            timeout_socket=timeout_socket,
            timeout_transport=timeout_transport,
            timeout_ops=timeout_ops,
            comms_prompt_pattern=comms_prompt_pattern,
            comms_return_char=comms_return_char,
            ssh_config_file=ssh_config_file,
            ssh_known_hosts_file=ssh_known_hosts_file,
            on_init=on_init,
            on_open=on_open,
            on_close=on_close,
            transport=transport,
            transport_options=transport_options,
            channel_log=channel_log,
            channel_log_mode=channel_log_mode,
            channel_lock=channel_lock,
            logging_uid=logging_uid,
        )

    async def _open(self, force: bool = False) -> None:
        if force or not self.transport.isalive():
            await self.open()

    @timeout_modifier
    async def _send_command(
        self,
        command: str,
    ) -> Response:
        """Send a command.

        Based on:
            scrapli.driver.generic.async_driver.GenericDriver: send_command and _send_command
            scrapli.channel.async_channel.Channel: send_input

        Args:
            command: string to send to device in privilege exec mode
            failed_when_contains: string or list of strings indicating failure if found in response

        Returns:
            Response: Scrapli Response object
        """
        await self._open()

        response = Response(
            host=self._base_transport_args.host,
            channel_input=command,
            failed_when_contains="#Error",
        )

        logger.debug("Sending Command: %s", command)

        # `self.transport` is the transport *instance*; comparing it against
        # transport name strings is never equal, so these checks used to be
        # unconditionally true. `self.transport_name` is the string.
        expects_echo = self.transport_name not in NON_ECHOING_TRANSPORTS

        # Normally handled in the channel `send_input`, but WattBox is special and doesn't work
        # with that function. Pulled it all into the Driver for simplicity.
        async with self.channel._channel_lock():
            self.channel.write(command)
            self.channel.send_return()
            raw_response = await self.channel._read_until_prompt()

            logger.debug("raw_response: %s", raw_response)
            split_response = raw_response.strip().splitlines()
            logger.debug("split_response: %s", split_response)
            if expects_echo and len(split_response) < 2:
                logger.debug("Not enough lines: %s. Getting more", len(split_response))
                raw_response += await self.channel._read_until_prompt()
                logger.debug("raw_response: %s", raw_response)
                split_response = raw_response.strip().splitlines()
                logger.debug("split_response: %s", split_response)

        if expects_echo and split_response[0] != command.encode():
            logger.error("Doesn't match command: %s - %s", command, split_response[0])

        if command.startswith("?"):
            if not split_response[-1].startswith(command.encode()):
                logger.error(
                    "Expected response to start with: %s, Got %s",
                    command,
                    split_response[-1],
                )
            # Use the last line rather than index 1. Devices that echo put the
            # reply there too, but non-echoing units (WB-800 series over telnet)
            # return a single line and index 1 raised IndexError on every command.
            processed_response = split_response[-1].split(b"=")[-1]
        else:
            processed_response = split_response[-1]

        logger.debug("processed_response: %s", processed_response)
        response.record_response(processed_response)
        response.raw_result = raw_response
        return response
