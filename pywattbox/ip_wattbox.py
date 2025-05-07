from __future__ import annotations

import logging
from collections.abc import Iterable
from enum import Enum
from typing import (
    Any,
    Final,
    NamedTuple,
    TypeVar,
    Union,
)

from scrapli.exceptions import ScrapliTransportPluginError
from scrapli.response import Response

from .base import BaseWattBox, Commands, Outlet, _async_create_wattbox, _create_wattbox
from .driver.async_driver import WattBoxAsyncDriver
from .driver.sync_driver import WattBoxDriver

logger = logging.getLogger("pywattbox.ip")


class REQUEST_MESSAGES(Enum):
    FIRMWARE = "?Firmware"
    HOSTNAME = "?Hostname"
    SERVICE_TAG = "?ServiceTag"
    MODEL = "?Model"
    OUTLET_COUNT = "?OutletCount"
    OUTLET_STATUS = "?OutletStatus"
    OUTLET_POWER_STATUS = "?OutletPowerStatus={outlet}"
    POWER_STATUS = "?PowerStatus"
    AUTO_REBOOT = "?AutoReboot"
    OUTLET_NAME = "?OutletName"
    UPS_STATUS = "?UPSStatus"
    UPS_CONNECTION = "?UPSConnection"


class CONTROL_MESSAGES(Enum):
    OUTLET_NAME_SET = "!OutletNameSet={outlet},{name}"
    OUTLET_NAME_SET_ALL = "!OutletNameSetAll={names}"  # Comma separated list of names
    OUTLET_SET = "!OutletSet={outlet},{action},{delay}"  # Optional delay
    OUTLET_POWER_ON_DELAY_SET = "!OutletPowerOnDelaySet={outlet},{delay}"
    OUTLET_MODE_SET = "!OutletModeSet={outlet},{mode}"
    OUTLET_REBOOT_SET = "!OutletRebootSet={ops}"  # Comma separate list of ops
    AUTO_REBOOT = "!AutoReboot={state}"
    AUTO_REBOOT_TIMEOUT_SET = (
        "!AutoRebootTimeoutSet={timeout},{count},{ping_delay},{reboot_attempts}"
    )
    FIRMWARE_UPDATE = "!FirmwareUpdate={url}"
    REBOOT = "!Reboot"
    ACCOUNT_SET = "!AccountSet={user},{password}"
    NETWORK_SET = (
        "!NetworkSet={host},{ip},{subnet},{gateway},{dns1},{dns2}"  # DNS 2 is optional
    )
    SCHEDULE_ADD = "!ScheduleAdd={schedule}"
    HOST_ADD = "!HostAdd={name},{ip},{outlets}"
    SET_TELNET = "!SetTelnet={mode}"
    WEB_SERVER_SET = "!WebServerSet={mode}"
    SET_SDDP = "!SetSDDP={mode}"


INITIAL_REQUESTS: Final[tuple[REQUEST_MESSAGES, ...]] = (
    REQUEST_MESSAGES.MODEL,
    REQUEST_MESSAGES.FIRMWARE,
    REQUEST_MESSAGES.UPS_CONNECTION,
    REQUEST_MESSAGES.HOSTNAME,
    REQUEST_MESSAGES.SERVICE_TAG,
    REQUEST_MESSAGES.OUTLET_COUNT,
)


class InitialResponses(NamedTuple):
    hardware_version: Response
    firmware_version: Response
    has_ups: Response
    hostname: Response
    serial_number: Response
    number_outlets: Response


UPDATE_BASE_REQUESTS: Final[tuple[REQUEST_MESSAGES, ...]] = (
    REQUEST_MESSAGES.AUTO_REBOOT,
    REQUEST_MESSAGES.POWER_STATUS,
    REQUEST_MESSAGES.OUTLET_NAME,
    REQUEST_MESSAGES.OUTLET_STATUS,
)


class UpdateBaseResponses(NamedTuple):
    auto_reboot: Response
    power_status: Response
    outlet_name: Response
    outlet_status: Response


_Responses = TypeVar("_Responses", bound=Union[InitialResponses, UpdateBaseResponses])


class DriverUnavailableError(Exception):
    pass


class IpWattBox(BaseWattBox):
    def __init__(
        self,
        host: str,
        user: str,
        password: str,
        port: int = 22,
        transport: str | None = None,
    ) -> None:
        super().__init__(host, user, password, port)

        self.battery_test = None
        self.cloud_status = None
        self.outlet_power_status: bool = False

        conninfo: dict[str, Any] = {
            "host": host,
            "auth_username": user,
            "auth_password": password,
            "port": port,
        }
        if transport is None:
            if port == 22:
                transport = "ssh"
            elif port == 23:
                transport = "telnet"
            else:
                raise ValueError("Non Standard Port, Transport must be set.")

        try:
            self.driver: WattBoxDriver | None = WattBoxDriver(
                **conninfo,
                transport="ssh2" if transport == "ssh" else "telnet",
            )
        except ScrapliTransportPluginError:
            self.driver = None
        try:
            self.async_driver: WattBoxAsyncDriver | None = WattBoxAsyncDriver(
                **conninfo,
                transport="asyncssh" if transport == "ssh" else "asynctelnet",
            )
        except ScrapliTransportPluginError:
            self.async_driver = None

    def send_requests(
        self, requests: Iterable[REQUEST_MESSAGES | str]
    ) -> list[Response]:
        if not self.driver:
            raise DriverUnavailableError
        responses: list[Response] = []
        for request in requests:
            responses.append(
                self.driver._send_command(
                    request.value if isinstance(request, REQUEST_MESSAGES) else request
                )
            )
        return responses

    async def async_send_requests(
        self, requests: Iterable[REQUEST_MESSAGES | str]
    ) -> list[Response]:
        if not self.async_driver:
            raise DriverUnavailableError
        responses: list[Response] = []
        for request in requests:
            responses.append(
                await self.async_driver._send_command(
                    request.value if isinstance(request, REQUEST_MESSAGES) else request
                )
            )
        return responses

    def parse_initial(self, responses: InitialResponses) -> None:
        logger.debug("Parse Initial")
        # TODO: Add if failed logic?
        self.hardware_version = responses.hardware_version.result
        if "150" not in self.hardware_version and "250" not in self.hardware_version:
            self.outlet_power_status = True
        self.firmware_version = responses.firmware_version.result
        self.has_ups = responses.has_ups.result == "1"
        self.hostname = responses.hostname.result
        self.serial_number = responses.serial_number.result
        self.number_outlets = (
            int(count) if (count := responses.number_outlets.result) else 0
        )
        # The index for outlet within WattBox starts at 1.
        self.outlets = {i: Outlet(i, self) for i in range(1, self.number_outlets + 1)}

    def get_initial(self) -> None:
        logger.debug("Get Initial")
        responses = InitialResponses(*self.send_requests(INITIAL_REQUESTS))
        self.parse_initial(responses)

    async def async_get_initial(self) -> None:
        logger.debug("Async Get Initial")
        responses = InitialResponses(
            *(await self.async_send_requests(INITIAL_REQUESTS))
        )
        logger.debug("Responses: %s", responses)
        self.parse_initial(responses)

    def parse_update_base(self, responses: UpdateBaseResponses) -> None:
        logger.debug("Parse Update Base")
        # auto reboot
        self.auto_reboot = responses.auto_reboot.result == "1"
        # power status
        power_status = responses.power_status.result.split(",")
        self.current_value = float(power_status[0])
        self.power_value = float(power_status[1])
        self.voltage_value = float(power_status[2])
        # The light is green and shows as green in the web UI, but strangely
        # the value is "0" in this API call.
        self.safe_voltage_status = power_status[3] == "0"
        # outlet_name
        for i, s in enumerate(responses.outlet_name.result.split(","), start=1):
            self.outlets[i].name = s.lstrip("{").rstrip("}")
        # outlet_status
        for i, s in enumerate(responses.outlet_status.result.split(","), start=1):
            self.outlets[i].status = s == "1"

    def parse_ups_status(self, response: Response) -> None:
        logger.debug("Parse UPS Status")
        ups_status = response.result.split(",")
        self.battery_charge = int(ups_status[0])
        self.battery_load = int(ups_status[1])
        self.battery_health = ups_status[2] == "Good"
        self.power_lost = ups_status[3] == "True"
        self.est_run_time = int(ups_status[4])
        self.audible_alarm = ups_status[5] == "True"
        self.mute = ups_status[6] == "True"

    def parse_outlet_power_statuses(self, responses: Iterable[Response]) -> None:
        logger.debug("Parse Outlet Statuses")
        for response in responses:
            index, power, current, voltage = response.result.split(",")
            # The index in the python list is off by 1 from the WattBox index.
            outlet = self.outlets[int(index)]
            outlet.power_value = float(power)
            outlet.current_value = float(current)
            outlet.voltage_value = float(voltage)

    @property
    def update_requests(self) -> tuple[REQUEST_MESSAGES | str, ...]:
        return (
            *UPDATE_BASE_REQUESTS,
            REQUEST_MESSAGES.UPS_STATUS,
            *(
                (
                    REQUEST_MESSAGES.OUTLET_POWER_STATUS.value.format(
                        outlet=(outlet.index)
                    )
                    for outlet in self.outlets.values()
                )
                if self.outlet_power_status
                else ()
            ),
        )

    def update(self) -> None:
        logger.debug("Update")
        responses = self.send_requests(self.update_requests)
        self.parse_update_base(UpdateBaseResponses(*responses[0:4]))
        self.parse_ups_status(responses[4])
        if self.outlet_power_status:
            self.parse_outlet_power_statuses(responses[5:])

    async def async_update(self) -> None:
        logger.debug("Async Update")
        responses = await self.async_send_requests(self.update_requests)
        self.parse_update_base(UpdateBaseResponses(*responses[0:4]))
        self.parse_ups_status(responses[4])
        if self.outlet_power_status:
            self.parse_outlet_power_statuses(responses[5:])

    def send_command(self, outlet: int, command: Commands) -> None:
        logger.debug("Send Command")
        if not self.driver:
            raise DriverUnavailableError
        self.driver._send_command(
            CONTROL_MESSAGES.OUTLET_SET.value.format(
                outlet=outlet, action=command.name, delay=0
            )
        )
        self.update()

    async def async_send_command(self, outlet: int, command: Commands) -> None:
        logger.debug("Async Send Command")
        if not self.async_driver:
            raise DriverUnavailableError
        await self.async_driver._send_command(
            CONTROL_MESSAGES.OUTLET_SET.value.format(
                outlet=outlet, action=command.name, delay=0
            )
        )
        await self.async_update()

    # String Representation
    def __str__(self) -> str:
        return f"{self.hostname} ({self.host}): {self.hardware_version}"


def create_ip_wattbox(host: str, user: str, password: str, port: int = 22) -> IpWattBox:
    return _create_wattbox(
        IpWattBox, host=host, user=user, password=password, port=port
    )


async def async_create_ip_wattbox(
    host: str, user: str, password: str, port: int = 22
) -> IpWattBox:
    return await _async_create_wattbox(
        IpWattBox, host=host, user=user, password=password, port=port
    )
