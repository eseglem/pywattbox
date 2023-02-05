from __future__ import annotations

from io import BytesIO
from typing import Any, Callable, Dict, List, Optional, Union

from scrapli.decorators import timeout_modifier
from scrapli.driver import Driver
from scrapli.response import Response
from scrapli.driver.generic.base_driver import BaseGenericDriver

from . import PROMPTS


def on_open(driver: WattBoxDriver) -> None:
    if driver.transport_name not in ("telnet", "asynctelnet"):
        driver.channel._read_until_prompt()


def on_close(driver: WattBoxDriver) -> None:
    driver.channel.write("!Exit")
    driver.channel.send_return()


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
        channel_lock: bool = False,
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

    @timeout_modifier
    def _send_command(
        self,
        command: str,
        *,
        strip_prompt: bool = False,
        failed_when_contains: Optional[Union[str, List[str]]] = "#Error",
        timeout_ops: Optional[float] = None,
    ) -> Response:
        """Send a command.

        Based on:
            scrapli.driver.generic.sync_driver.GenericDriver: send_command and _send_command
            scrapli.channel.sync_channel.Channel: send_input

        Args:
            command: string to send to device in privilege exec mode
            strip_prompt: strip prompt or not, defaults to True (yes, strip the prompt)
            failed_when_contains: string or list of strings indicating failure if found in response
            timeout_ops: timeout ops value for this operation; only sets the timeout_ops value for
                the duration of the operation, value is reset to initial value after operation is
                completed

        Returns:
            Response: Scrapli Response object
        """

        response = BaseGenericDriver._pre_send_command(
            host=self._base_transport_args.host,
            command=command,
            failed_when_contains=failed_when_contains,
        )

        channel_input = command.encode()

        # Normally handled in the channel `send_input`, but WattBox is special and doesn't work
        # with that function. Pulled it all into the Driver for simplicity.
        with self.channel._channel_lock():
            self.channel.write(command)
            self.channel.send_return()
            if self.transport_name not in ("telnet", "asynctelnet"):
                self.channel._read_until_input(channel_input=channel_input)
            raw_response = self.channel._read_until_prompt()

        processed_response = self.channel._process_output(
            raw_response, strip_prompt
        ).lstrip(channel_input + b"=")

        return BaseGenericDriver._post_send_command(
            raw_response=raw_response,
            processed_response=processed_response,
            response=response,
        )
