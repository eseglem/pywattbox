from __future__ import annotations

from enum import IntEnum
from typing import List, Optional, Union

import requests
from bs4 import BeautifulSoup
from requests.auth import HTTPBasicAuth


class Commands(IntEnum):
    OFF = 0
    ON = 1
    RESET = 3
    AUTO_REBOOT_ON = 4
    AUTO_REBOOT_OFF = 5


class WattBox(object):
    def __init__(
        self, ip: str, port: int = 80, user: str = "wattbox", password: str = "wattbox"
    ) -> None:
        self.base_host: str = f"http://{ip}:{port}"
        self.user: str = user
        self.password: str = password

        # Info, set once
        self.hardware_version: Optional[str] = None
        self.has_ups: bool = False
        self.hostname: str = ""
        self.number_outlets: int = 0
        self.serial_number: str = ""

        # Status values
        self.audible_alarm: bool = False
        self.auto_reboot: bool = False
        self.cloud_status: bool = False
        self.mute: bool = False
        self.power_lost: bool = False

        # Power values
        self.current_value: float = 0.0  # In Amps
        self.power_value: float = 0.0  # In watts
        self.safe_voltage_status: bool = True
        self.voltage_value: float = 0.0  # In volts

        # Battery values
        self.battery_charge: int = 0  # In percent
        self.battery_health: bool = False
        self.battery_load: int = 0  # In percent
        self.battery_test: bool = False
        self.est_run_time: int = 0  # In minutes

        self.outlets: List[Outlet] = []

        result = requests.get(
            f"{self.base_host}/wattbox_info.xml",
            auth=HTTPBasicAuth(self.user, self.password),
        )
        soup = BeautifulSoup(result.content, "xml")

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
        # hardware version doesn't work well. Just split the outlests.
        # Additional logic shouldn't ever get used, but there just in case
        if soup.outlet_status is not None:
            self.number_outlets = len(soup.outlet_status.text.split(","))
        elif self.hardware_version is not None:
            self.number_outlets = int(self.hardware_version.split("-")[-1])
        else:
            self.number_outlets = 0

        # Initialize outlets
        self.outlets.append(MasterSwitch(self))
        for i in range(1, self.number_outlets + 1):
            self.outlets.append(Outlet(i, self))

        # Update all the other values
        self.update()

    def update(self) -> None:
        result = requests.get(
            f"{self.base_host}/wattbox_info.xml",
            auth=HTTPBasicAuth(self.user, self.password),
        )
        soup = BeautifulSoup(result.content, "xml")

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

        outlet_methods: Union[List[bool], List[None]]
        if soup.outlet_method is not None:
            outlet_methods = [_ == "1" for _ in soup.outlet_method.text.split(",")]
        else:
            outlet_methods = [None] * self.number_outlets

        outlet_names: Union[List[str], List[None]]
        if soup.outlet_name is not None:
            outlet_names = soup.outlet_name.text.split(",")
        else:
            outlet_names = [None] * self.number_outlets

        outlet_statuses: Union[List[bool], List[None]]
        if soup.outlet_status:
            outlet_statuses = [_ == "1" for _ in soup.outlet_status.text.split(",")]
        else:
            outlet_statuses = [None] * self.number_outlets

        # self.outlets[0] is master so start at 1
        for i in range(1, self.number_outlets + 1):
            self.outlets[i].method = outlet_methods[i - 1]
            self.outlets[i].name = outlet_names[i - 1]
            self.outlets[i].status = outlet_statuses[i - 1]

        # Gather statuses for outlets that have method on
        statuses: List[Optional[bool]] = [
            outlet.status for outlet in self.outlets[1:] if outlet.method
        ]
        # Master switch is on if all those outlets are on
        self.outlets[0].status = all(statuses)

    # Will send the command to the specific outlet.
    def send_command(self, outlet, command) -> None:
        _ = requests.get(
            f"{self.base_host}/control.cgi?outlet={outlet}&command={command}",
            auth=HTTPBasicAuth(self.user, self.password),
        )

    # Simulates pressing the master switch.
    # Will send the command to all outlets with master switch enabled.
    def send_master_command(self, command) -> None:
        if command not in (Commands.ON, Commands.OFF):
            raise ValueError(
                "Command ({}) can only be `Commands.ON` or `Commands.OFF`.".format(
                    command
                )
            )
        for outlet in self.outlets:
            if outlet.method and outlet.status != command:
                self.send_command(outlet.index, command)

    def __str__(self):
        return f"{self.hostname} ({self.base_host}): {self.hardware_version}"


class Outlet(object):
    def __init__(self, index, wattbox) -> None:
        self.index = index
        self.method: Optional[bool] = None
        self.name: Optional[str] = ""
        self.status: Optional[bool] = None
        self.wattbox = wattbox

    def turn_on(self) -> None:
        self.wattbox.send_command(self.index, Commands.ON)

    def turn_off(self) -> None:
        self.wattbox.send_command(self.index, Commands.OFF)

    def reset(self) -> None:
        self.wattbox.send_command(self.index, Commands.RESET)

    def __str__(self) -> str:
        return f"{self.name} ({self.index}): {self.status}"


class MasterSwitch(Outlet):
    def __init__(self, wattbox) -> None:
        super().__init__(0, wattbox)
        self.name = "Master Switch"

    def turn_on(self) -> None:
        self.wattbox.send_master_command(Commands.ON)

    def turn_off(self) -> None:
        self.wattbox.send_master_command(Commands.OFF)
