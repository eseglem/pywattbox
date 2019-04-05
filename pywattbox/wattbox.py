from enum import IntEnum

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
    # Info, set once
    hardware_version = None
    has_ups = False
    hostname = ''
    number_outlets = 0
    serial_number = ''

    # Status values
    audible_alarm = False
    auto_reboot = False
    cloud_status = False
    mute = False
    power_lost = False

    # Power values
    current_value = 0  # In Amps
    power_value = 0    # In watts
    safe_voltage_status = True
    voltage_value = 0  # In volts

    # Battery values
    battery_charge = 0 # In percent
    battery_health = False
    battery_load = 0   # In percent
    battery_test = False
    est_run_time = 0   # In minutes

    outlets = []

    def __init__(self, ip, port=80, user='wattbox', password='wattbox'):
        self.base_host = "http://{}:{}".format(ip, port)
        self.user = user
        self.password = password

        result = requests.get(
            "{}/wattbox_info.xml".format(self.base_host),
            auth=HTTPBasicAuth(self.user, self.password)
        )
        soup = BeautifulSoup(result.content, 'xml')

        # Set these values once, should never change
        if soup.hardware_version is not None:
            self.hardware_version = soup.hardware_version.text
        if soup.hasUPS is not None:
            self.has_ups = soup.hasUPS.text == '1'
        if soup.host_name is not None:
            self.hostname = soup.host_name.text
        if soup.serial_number is not None:
            self.serial_number = soup.serial_number.text

        if self.hardware_version is not None:
            self.number_outlets = int(self.hardware_version.split('-')[-1])

        # Initialize outlets
        self.outlets.append(MasterSwitch(self))
        for i in range(1, self.number_outlets + 1):
            self.outlets.append(Outlet(i, self))

        # Update all the other values
        self.update()

    def update(self):
        result = requests.get(
            "{}/wattbox_info.xml".format(self.base_host),
            auth=HTTPBasicAuth(self.user, self.password)
        )
        soup = BeautifulSoup(result.content, 'xml')

        # Status values
        if soup.audible_alarm is not None:
            self.audible_alarm = soup.audible_alarm.text == '1'
        if soup.auto_reboot is not None:
            self.auto_reboot = soup.auto_reboot.text == '1'
        if soup.cloud_status is not None:
            self.cloud_status = soup.cloud_status.text == '1'
        if soup.mute is not None:
            self.mute = soup.mute.text == '1'
        if soup.power_lost is not None:
            self.power_lost = soup.power_lost.text == '1'
        if soup.safe_voltage_status is not None:
            self.safe_voltage_status = soup.safe_voltage_status.text == '1'

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
                self.battery_health = soup.battery_health.text == '1'
            if soup.battery_load is not None:
                self.battery_load = int(soup.battery_load.text)
            if soup.battery_test is not None:
                self.battery_test = soup.battery_test.text == '1'
            if soup.est_run_time is not None:
                self.est_run_time = int(soup.est_run_time.text)

        if soup.outlet_method is not None:
            outlet_methods = [_ == '1' for _ in soup.outlet_method.text.split(',')]
        else:
            outlet_methods = [None] * self.number_outlets
        if soup.outlet_name is not None:
            outlet_names = soup.outlet_name.text.split(',')
        else:
            outlet_names = [None] * self.number_outlets
        if soup.outlet_status:
            outlet_statuses = [_ == '1' for _ in soup.outlet_status.text.split(',')]
        else:
            outlet_statuses = [None] * self.number_outlets

        for i in range(1, self.number_outlets + 1):
            self.outlets[i].method = outlet_methods[i - 1]
            self.outlets[i].name = outlet_names[i - 1]
            self.outlets[i].status = outlet_statuses[i - 1]

        # Gather statuses for outlets that have method on
        statuses = [outlet.status for outlet in self.outlets[1:] if outlet.method]
        # Master switch is on if all those outlets are on
        self.outlets[0].status = all(statuses)

    # Will send the command to the specific outlet. 
    def send_command(self, outlet, command):
        _ = requests.get(
            "{}/control.cgi?outlet={}&command={}".format(
                self.base_host,
                outlet,
                command
            ),
            auth=HTTPBasicAuth(self.user, self.password)
        )

    # Simulates pressing the master switch.
    # Will send the command to all outlets with master switch enabled.
    def send_master_command(self, command):
        if command not in (Commands.ON, Commands.OFF):
            raise ValueError(
                "Command ({}) can only be `Commands.ON` or `Commands.OFF`.".format(command)
            )
        for outlet in self.outlets:
            if outlet.method and outlet.status != command:
                self.send_command(outlet.index, command)

    def __str__(self):
        return "{} ({}): {}".format(self.hostname, self.base_host, self.hardware_version)


class Outlet(object):
    def __init__(self, index, wattbox):
        self.index = index
        self.method = None
        self.name = ''
        self.status = None
        self.wattbox = wattbox

    def turn_on(self):
        self.wattbox.send_command(self.index, Commands.ON)

    def turn_off(self):
        self.wattbox.send_command(self.index, Commands.OFF)

    def reset(self):
        self.wattbox.send_command(self.index, Commands.RESET)

    def __str__(self):
        return "{} ({}): {}".format(self.name, self.index, self.status)

class MasterSwitch(Outlet):
    def __init__(self, wattbox):
        super().__init__(0, wattbox)
        self.name = 'Master Switch'
    
    def turn_on(self):
        self.wattbox.send_master_command(Commands.ON)

    def turn_off(self):
        self.wattbox.send_master_command(Commands.OFF)
