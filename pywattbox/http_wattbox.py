from __future__ import annotations

import logging

import httpx
from bs4 import BeautifulSoup

from .base import BaseWattBox, Commands, Outlet, _async_create_wattbox, _create_wattbox

logger = logging.getLogger("pywattbox.http")


class HttpWattBox(BaseWattBox):
    def __init__(self, host: str, user: str, password: str, port: int = 80) -> None:
        super().__init__(host, user, password, port)
        self.base_host: str = f"http://{host}:{port}"

    # Get Initial Data
    def get_initial(self) -> None:
        logger.debug("Get Initial")
        response = httpx.get(
            f"{self.base_host}/wattbox_info.xml",
            auth=(self.user, self.password),
        )
        logger.debug(f"    Status: {response.status_code}")
        response.raise_for_status()
        self.parse_initial(response)
        self.parse_update(response)

    async def async_get_initial(self) -> None:
        logger.debug("Async Get Initial")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_host}/wattbox_info.xml",
                auth=(self.user, self.password),
            )
            logger.debug(f"    Status: {response.status_code}")
            response.raise_for_status()
        self.parse_initial(response)
        self.parse_update(response)

    # Parse Initial Data
    def parse_initial(self, response: httpx.Response) -> None:
        logger.debug("Parse Initial")
        # Parse with BeautifulSoup
        soup = BeautifulSoup(response.content, "xml")
        logger.debug(soup)

        # Set these values once, should never change
        if soup.hardware_version is not None:
            self.hardware_version = soup.hardware_version.text
        if soup.hasUPS is not None:
            self.has_ups = soup.hasUPS.text == "1"
        if soup.host_name is not None:
            self.hostname = soup.host_name.text
        if soup.serial_number is not None:
            self.serial_number = soup.serial_number.text

        # Some hardware versions have plugs that are always on, so using the
        # hardware version doesn't work well. Just split the outlets.
        # Additional logic shouldn't ever get used, but there just in case
        if soup.outlet_status is not None:
            self.number_outlets = len(soup.outlet_status.text.split(","))
        elif self.hardware_version is not None:
            self.number_outlets = int(self.hardware_version.split("-")[-1])
        else:
            self.number_outlets = 0

        # Initialize outlets
        self.outlets = {i: Outlet(i, self) for i in range(1, self.number_outlets + 1)}
        self.master_outlet = MasterSwitch(self)

    # Get Update Data
    def update(self) -> None:
        logger.debug("Update")
        response = httpx.get(
            f"{self.base_host}/wattbox_info.xml",
            auth=(self.user, self.password),
        )
        logger.debug(f"    Status: {response.status_code}")
        response.raise_for_status()
        self.parse_update(response)

    async def async_update(self) -> None:
        logger.debug("Async Update")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_host}/wattbox_info.xml",
                auth=(self.user, self.password),
            )
            logger.debug(f"    Status: {response.status_code}")
            response.raise_for_status()
        self.parse_update(response)

    # Parse Update Data
    def parse_update(self, response: httpx.Response) -> None:
        logger.debug("Parse Update")
        # Parse with BeautifulSoup
        soup = BeautifulSoup(response.content, "xml")
        logger.debug(soup)

        # Status values
        if soup.audible_alarm is not None:
            self.audible_alarm = soup.audible_alarm.text == "1"
        if soup.auto_reboot is not None:
            self.auto_reboot = soup.auto_reboot.text == "1"
        if soup.cloud_status is not None:
            self.cloud_status = soup.cloud_status.text == "1"
        if soup.mute is not None:
            self.mute = soup.mute.text == "1"
        if soup.power_lost is not None:
            self.power_lost = soup.power_lost.text == "1"
        if soup.safe_voltage_status is not None:
            self.safe_voltage_status = soup.safe_voltage_status.text == "1"

        # Power values
        if soup.power_value is not None:
            self.power_value = int(soup.power_value.text)
        # Api returns these two as tenths
        if soup.current_value is not None:
            self.current_value = int(soup.current_value.text) / 10
        if soup.voltage_value is not None:
            self.voltage_value = int(soup.voltage_value.text) / 10

        # Battery values
        if self.has_ups:
            if soup.battery_charge is not None:
                self.battery_charge = int(soup.battery_charge.text)
            if soup.battery_health is not None:
                self.battery_health = soup.battery_health.text == "1"
            if soup.battery_load is not None:
                self.battery_load = int(soup.battery_load.text)
            if soup.battery_test is not None:
                self.battery_test = soup.battery_test.text == "1"
            if soup.est_run_time is not None:
                self.est_run_time = int(soup.est_run_time.text)

        # Outlets
        if soup.outlet_method is not None:
            for i, s in enumerate(soup.outlet_method.text.split(","), start=1):
                self.outlets[i].method = s == "1"

        if soup.outlet_name is not None:
            for i, s in enumerate(soup.outlet_name.text.split(","), start=1):
                self.outlets[i].name = s

        if soup.outlet_status is not None:
            for i, s in enumerate(soup.outlet_status.text.split(","), start=1):
                self.outlets[i].status = s == "1"

        # Master switch is on if all those outlets are on
        if self.master_outlet is not None:
            # Gather statuses for outlets that have method on
            statuses: list[bool | None] = [
                outlet.status for outlet in self.outlets.values() if outlet.method
            ]
            self.master_outlet.status = all(statuses)

    # Send command
    def send_command(self, outlet: int, command: Commands) -> None:
        logger.debug("Send Command")
        response = httpx.get(
            f"{self.base_host}/control.cgi",
            params={"outlet": outlet, "command": command.value},
            auth=(self.user, self.password),
        )
        logger.debug(f"    Status: {response.status_code}")
        response.raise_for_status()

    async def async_send_command(self, outlet: int, command: Commands) -> None:
        logger.debug("Async Send Command")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_host}/control.cgi",
                params={"outlet": outlet, "command": command.value},
                auth=(self.user, self.password),
            )
            logger.debug(f"    Status: {response.status_code}")
            response.raise_for_status()

    # Verify command is master eligible
    def check_master_command(self, command: Commands) -> None:
        if command not in (Commands.ON, Commands.OFF):
            raise ValueError(
                f"Command ({command}) can only be `Commands.ON` or `Commands.OFF`."
            )

    # Simulates pressing the master switch.
    # Will send the command to all outlets with master switch enabled.
    def send_master_command(self, command: Commands) -> None:
        logger.debug("Send Master Command(s)")
        self.check_master_command(command)
        for outlet in self.outlets.values():
            if outlet.method and outlet.status != command:
                self.send_command(outlet.index, command)
        logger.debug("Send Master Command(s)")

    async def async_send_master_command(self, command: Commands) -> None:
        logger.debug("Send Master Command(s)")
        self.check_master_command(command)
        for outlet in self.outlets.values():
            if outlet.method and outlet.status != command:
                await self.async_send_command(outlet.index, command)
        logger.debug("Send Master Command(s)")

    # String Representation
    def __str__(self) -> str:
        return f"{self.hostname} ({self.base_host}): {self.hardware_version}"


def create_http_wattbox(
    host: str, user: str, password: str, port: int = 80
) -> HttpWattBox:
    return _create_wattbox(
        HttpWattBox, host=host, user=user, password=password, port=port
    )


async def async_create_http_wattbox(
    host: str, user: str, password: str, port: int = 80
) -> HttpWattBox:
    return await _async_create_wattbox(
        HttpWattBox, host=host, user=user, password=password, port=port
    )


class MasterSwitch(Outlet):
    """Special Outlet that mimics the Master Switch.

    Only works with HTTP API.
    """

    # Override to tell it that it only works on WattBox and not BaseWattBox
    wattbox: HttpWattBox

    def __init__(self, wattbox: HttpWattBox) -> None:
        super().__init__(0, wattbox)
        self.name = "Master Switch"

    def turn_on(self) -> None:
        self.wattbox.send_master_command(Commands.ON)

    async def async_turn_on(self) -> None:
        await self.wattbox.async_send_master_command(Commands.ON)

    def turn_off(self) -> None:
        self.wattbox.send_master_command(Commands.OFF)

    async def async_turn_of(self) -> None:
        await self.wattbox.async_send_master_command(Commands.OFF)
