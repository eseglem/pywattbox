from __future__ import annotations

from io import BytesIO
from typing import Any, Callable, Dict, Optional, Union

from scrapli.decorators import timeout_modifier
from scrapli.driver import Driver
from scrapli.exceptions import ScrapliConnectionNotOpened
from scrapli.response import Response

from . import PROMPTS


def on_open(driver: WattBoxDriver) -> None:
    if driver.transport_name not in ("telnet", "asynctelnet"):
        driver.channel._read_until_prompt()


def on_close(driver: WattBoxDriver) -> None:
    try:
        driver.channel.write("!Exit")
        driver.channel.send_return()
    except ScrapliConnectionNotOpened:
        pass


class WattBoxDriver(Driver):
    def __init__(
        self,
        host: str,
        port: Optional[int] = 22,
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
        ssh_config_file: Union[str, bool] = False,
        ssh_known_hosts_file: Union[str, bool] = False,
        on_init: Optional[Callable[..., Any]] = None,
        on_open: Optional[Callable[..., Any]] = on_open,
        on_close: Optional[Callable[..., Any]] = on_close,
        transport: str = "ssh2",
        transport_options: Optional[Dict[str, Any]] = None,
        channel_log: Union[str, bool, BytesIO] = False,
        channel_log_mode: str = "write",
        channel_lock: bool = True,
        logging_uid: str = "",
    ) -> None:
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

    def _open(self, force: bool = False) -> None:
        if force or not self.transport.isalive():
            self.open()

    @timeout_modifier
    def _send_command(
        self,
        command: str,
    ) -> Response:
        """Send a command.

        Based on:
            scrapli.driver.generic.sync_driver.GenericDriver: send_command and _send_command
            scrapli.channel.sync_channel.Channel: send_input

        Args:
            command: string to send to device in privilege exec mode
            failed_when_contains: string or list of strings indicating failure if found in response

        Returns:
            Response: Scrapli Response object
        """
        self._open()

        response = Response(
            host=self._base_transport_args.host,
            channel_input=command,
            failed_when_contains="#Error",
        )

        # Normally handled in the channel `send_input`, but WattBox is special and doesn't work
        # with that function. Pulled it all into the Driver for simplicity.
        with self.channel._channel_lock():
            self.channel.write(command)
            self.channel.send_return()
            raw_response = self.channel._read_until_prompt()

        processed_response = raw_response.splitlines()[-1].split(b"=")[-1]

        response.record_response(processed_response)
        response.raw_result = raw_response
        return response
