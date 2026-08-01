from __future__ import annotations

import logging
from collections.abc import Callable
from io import BytesIO
from typing import Any

from scrapli.decorators import timeout_modifier
from scrapli.driver import AsyncDriver
from scrapli.exceptions import ScrapliConnectionNotOpened, ScrapliTimeout
from scrapli.response import Response

from . import (
    LOGIN_SUCCESS,
    PASSWORD_PROMPT,
    PROMPTS,
    TELNET_TRANSPORTS,
    USERNAME_PROMPT,
    find_reply,
)

logger = logging.getLogger("pywattbox.async_driver")


async def _read_until_token(driver: WattBoxAsyncDriver, token: bytes) -> bytes:
    """Accumulate channel reads until *token* appears.

    Raises:
        ScrapliTimeout: if the transport stops producing data first.
    """
    buf = b""
    while token not in buf:
        chunk = await driver.channel.read()
        if not chunk:
            raise ScrapliTimeout(
                f"connection closed while waiting for {token!r}, got {buf!r}"
            )
        buf += chunk
    return buf


async def on_open(driver: WattBoxAsyncDriver) -> None:
    """Complete the login handshake.

    Over SSH the transport authenticates and we only need to consume the
    banner. Over telnet the device presents its own ``Username:``/``Password:``
    prompts, which scrapli's in-channel telnet auth does not satisfy (it is
    rejected as ``Invalid Login``), so authentication is bypassed at the
    transport level -- see ``WattBoxAsyncDriver.__init__`` -- and performed
    here instead.
    """
    logger.debug("On Open")
    if driver.transport_name not in TELNET_TRANSPORTS:
        await driver.channel._read_until_prompt()
        return

    await _read_until_token(driver, USERNAME_PROMPT)
    driver.channel.write(driver.auth_username)
    driver.channel.send_return()

    await _read_until_token(driver, PASSWORD_PROMPT)
    driver.channel.write(driver.auth_password)
    driver.channel.send_return()

    await _read_until_token(driver, LOGIN_SUCCESS)
    logger.debug("Telnet login complete")


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
        if transport in TELNET_TRANSPORTS:
            # scrapli's in-channel telnet auth does not satisfy the WattBox
            # login prompt; `on_open` performs the handshake by hand instead.
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
        """Send one request and return its single-line reply.

        Reads until a *complete* reply line for this command arrives, rather
        than relying on scrapli's prompt matching. Three properties of the
        WattBox protocol make prompt matching unsuitable here:

        * replies carry no trailing prompt, so there is nothing to anchor on
        * values contain spaces and commas, so a whitespace-delimited pattern
          truncates them
        * the reply is not echoed over telnet, so its position in the buffer
          is transport dependent

        Args:
            command: request (``?``) or control (``!``) message to send

        Returns:
            Response: scrapli Response whose ``result`` is the reply value

        Raises:
            ScrapliTimeout: if the device sends no usable reply
        """
        await self._open()

        response = Response(
            host=self._base_transport_args.host,
            channel_input=command,
            failed_when_contains="#Error",
        )

        logger.debug("Sending Command: %s", command)

        # Normally handled by the channel's `send_input`, but this protocol has
        # no prompt for scrapli to synchronise on, so the exchange is driven
        # here instead.
        raw_response = b""
        async with self.channel._channel_lock():
            self.channel.write(command)
            self.channel.send_return()

            while True:
                try:
                    chunk = await self.channel.read()
                except ScrapliTimeout:
                    logger.debug("Read timed out for %s", command)
                    break
                if not chunk:
                    logger.debug("Connection closed while reading %s", command)
                    break
                raw_response += chunk
                if find_reply(raw_response, command) is not None:
                    break

        logger.debug("raw_response: %s", raw_response)
        # Fall back to a newline-less match only after reading has stopped, for
        # a device that closes the connection without terminating the line.
        processed_response = find_reply(raw_response, command)
        if processed_response is None:
            processed_response = find_reply(raw_response, command, strict=False)
        if processed_response is None:
            raise ScrapliTimeout(
                f"no reply to {command!r} from {self._base_transport_args.host}; "
                f"read {raw_response!r}"
            )

        logger.debug("processed_response: %s", processed_response)
        response.record_response(processed_response)
        response.raw_result = raw_response
        return response
