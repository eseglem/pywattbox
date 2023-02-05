from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from enum import IntEnum
from typing import TYPE_CHECKING, List, Optional, Type, TypeVar

logger = logging.getLogger("pywattbox")


class Commands(IntEnum):
    """Commands Enum for Convenience.

    HTTP API uses the values.
    Integration Protocol uses the names.
    """

    OFF = 0
    ON = 1
    RESET = 3
    # Only used for HTTP
    AUTO_REBOOT_ON = 4
    AUTO_REBOOT_OFF = 5
    # Only used for Integration Protocol
    TOGGLE = 6


# Type Checking doesn't like ABC for TypeVar
if TYPE_CHECKING:
    Base = object
else:
    Base = ABC


class BaseWattBox(Base):
    """Base WattBox that defines the"""

    def __init__(self, host: str, user: str, password: str, port: int) -> None:
        self.host: str = host
        self.port: Optional[int] = port
        self.user: str = user
        self.password: str = password

        # Info, set once
        self.hardware_version: Optional[str] = None
        self.firmware_version: Optional[str] = None
        self.has_ups: bool = False
        self.hostname: str = ""
        self.number_outlets: int = 0
        self.serial_number: str = ""

        # Status values
        self.audible_alarm: bool = False
        self.auto_reboot: bool = False
        self.cloud_status: Optional[bool] = False
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
        self.battery_test: Optional[bool] = False
        self.est_run_time: int = 0  # In minutes

        # Outlets list
        self.outlets: List[Outlet] = []

    @abstractmethod
    def get_initial(self) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def async_get_initial(self) -> None:
        raise NotImplementedError()

    @abstractmethod
    def update(self) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def async_update(self) -> None:
        raise NotImplementedError()

    @abstractmethod
    def send_command(self, outlet: int, command: Commands) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def async_send_command(self, outlet: int, command: Commands) -> None:
        raise NotImplementedError()


_T_WattBox = TypeVar("_T_WattBox", bound=BaseWattBox)


def _create_wattbox(
    type_: Type[_T_WattBox], host: str, user: str, password: str, port: int
) -> _T_WattBox:
    wattbox = type_(host=host, user=user, password=password, port=port)
    wattbox.get_initial()
    return wattbox


async def _async_create_wattbox(
    type_: Type[_T_WattBox], host: str, user: str, password: str, port: int
) -> _T_WattBox:
    wattbox = type_(host=host, user=user, password=password, port=port)
    await wattbox.async_get_initial()
    return wattbox


class Outlet(object):
    def __init__(self, index: int, wattbox: BaseWattBox) -> None:
        self.index: int = index
        self.method: Optional[bool] = None
        self.name: Optional[str] = ""
        self.status: Optional[bool] = None
        self.wattbox: BaseWattBox = wattbox

    def turn_on(self) -> None:
        self.wattbox.send_command(self.index, Commands.ON)

    async def async_turn_on(self) -> None:
        await self.wattbox.async_send_command(self.index, Commands.ON)

    def turn_off(self) -> None:
        self.wattbox.send_command(self.index, Commands.OFF)

    async def async_turn_off(self) -> None:
        await self.wattbox.async_send_command(self.index, Commands.OFF)

    def reset(self) -> None:
        self.wattbox.send_command(self.index, Commands.RESET)

    async def async_reset(self) -> None:
        await self.wattbox.async_send_command(self.index, Commands.RESET)

    def __str__(self) -> str:
        return f"{self.name} ({self.index}): {self.status}"
