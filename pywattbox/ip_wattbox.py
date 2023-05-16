from __future__ import annotations

from typing import (
    Any,
    Dict,
    Final,
    Iterable,
    List,
    NamedTuple,
    Optional,
    Tuple,
    TypeVar,
    Union,
)
from enum import Enum
from scrapli.response import Response

from .driver.async_driver import WattBoxAsyncDriver
from .driver.sync_driver import WattBoxDriver

from .base import (
    BaseWattBox,
    Commands,
    Outlet,
    _async_create_wattbox,
    _create_wattbox,
    logger,
)


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
    OUTLET_NAME_SET = "!OutletNameSet={outlet}{name}"
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


INITIAL_REQUESTS: Final[Tuple[REQUEST_MESSAGES, ...]] = (
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


UPDATE_BASE_REQUESTS: Final[Tuple[REQUEST_MESSAGES, ...]] = (
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


class IpWattBox(BaseWattBox):
    def __init__(
        self,
        host: str,
        user: str,
        password: str,
        port: int = 22,
        transport: Optional[str] = None,
    ) -> None:
        super().__init__(host, user, password, port)

        self.battery_test = None
        self.cloud_status = None

        conninfo: Dict[str, Any] = {
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

        self.driver = WattBoxDriver(
            **conninfo,
            transport="ssh2" if transport == "ssh" else "telnet",
        )
        self.async_driver = WattBoxAsyncDriver(
            **conninfo,
            transport="asyncssh" if transport == "ssh" else "asynctelnet",
        )

    def send_requests(self, requests: Iterable[REQUEST_MESSAGES]) -> List[Response]:
        responses: List[Response] = []
        with self.driver as conn:
            for request in requests:
                responses.append(conn._send_command(request.value))
        return responses

    async def async_send_requests(
        self, requests: Iterable[REQUEST_MESSAGES]
    ) -> List[Response]:
        responses: List[Response] = []
        async with self.async_driver as conn:
            for request in requests:
                responses.append(await conn._send_command(request.value))
        return responses

    def parse_initial(self, responses: InitialResponses) -> None:
        logger.debug("Parse Initial")
        # TODO: Add if failed logic?
        self.hardware_version = responses.hardware_version.result
        self.firmware_version = responses.firmware_version.result
        self.has_ups = responses.has_ups.result == "1"
        self.hostname = responses.hostname.result
        self.serial_number = responses.serial_number.result
        self.number_outlets = (
            int(count) if (count := responses.number_outlets.result) else 0
        )
        # TODO: Master?
        for i in range(self.number_outlets):
            self.outlets.append(Outlet(i, self))

    def get_initial(self) -> None:
        logger.debug("Get Initial")
        responses = InitialResponses(*self.send_requests(INITIAL_REQUESTS))
        self.parse_initial(responses)

    async def async_get_initial(self) -> None:
        logger.debug("Async Get Initial")
        responses = InitialResponses(
            *(await self.async_send_requests(INITIAL_REQUESTS))
        )
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
        self.safe_voltage_status = power_status[3] == "1"
        # outlet_name
        for i, s in enumerate(responses.outlet_name.result.split(",")):
            self.outlets[i].name = s.lstrip("{").rstrip("}")
        # outlet_status
        for i, s in enumerate(responses.outlet_status.result.split(",")):
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

    def update(self) -> None:
        logger.debug("Update")
        base_responses = UpdateBaseResponses(*self.send_requests(UPDATE_BASE_REQUESTS))
        self.parse_update_base(base_responses)
        ups_status = self.send_requests((REQUEST_MESSAGES.UPS_STATUS,))
        self.parse_ups_status(ups_status[0])

    async def async_update(self) -> None:
        logger.debug("Async Update")
        base_responses = UpdateBaseResponses(
            *(await self.async_send_requests(UPDATE_BASE_REQUESTS))
        )
        self.parse_update_base(base_responses)
        ups_status = await self.async_send_requests((REQUEST_MESSAGES.UPS_STATUS,))
        self.parse_ups_status(ups_status[0])
        # TODO: Outlets have individual power status?

    def send_command(self, outlet: int, command: Commands) -> None:
        logger.debug("Send Command")
        with self.driver as conn:
            conn._send_command(
                CONTROL_MESSAGES.OUTLET_SET.value.format(
                    outlet=outlet, action=command.name, delay=0
                )
            )
        self.update()

    async def async_send_command(self, outlet: int, command: Commands) -> None:
        logger.debug("Async Send Command")
        async with self.async_driver as conn:
            await conn._send_command(
                CONTROL_MESSAGES.OUTLET_SET.value.format(
                    outlet=outlet, action=command.name, delay=0
                )
            )
        await self.async_update()


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
