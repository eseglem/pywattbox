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
        self.hardware_version = soup.request.hardware_version.text
        self.has_ups = bool(soup.hasUPS.text)
        self.hostname = soup.host_name.text
        self.number_outlets = int(self.hardware_version.split('-')[-1])
        self.serial_number = soup.serial_number.text

        # Initialize outlets
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
        self.audible_alarm = soup.audible_alarm.text == '1'
        self.auto_reboot = soup.auto_reboot.text == '1'
        self.cloud_status = soup.cloud_status.text == '1'
        self.mute = soup.mute.text == '1'
        self.power_lost = soup.power_lost.text == '1'
        self.safe_voltage_status = soup.safe_voltage_status.text == '1'

        # Power values
        self.power_value = int(soup.power_value.text)
        # Api returns these two as tenths
        self.current_value = int(soup.current_value.text) / 10
        self.voltage_value = int(soup.voltage_value.text) / 10

        # Battery values
        if self.has_ups:
            self.battery_charge = int(soup.battery_charge.text)
            self.battery_health = soup.battery_health.text == '1'
            self.battery_load = int(soup.battery_load.text)
            self.battery_test = soup.battery_test.text == '1'
            self.est_run_time = int(soup.est_run_time.text)

        outlet_methods = [_ == '1' for _ in soup.outlet_method.text.split(',')]
        outlet_names = soup.outlet_name.text.split(',')
        outlet_statuses = [_ == '1' for _ in soup.outlet_status.text.split(',')]
        for i in range(self.number_outlets):
            self.outlets[i].method = outlet_methods[i]
            self.outlets[i].name = outlet_names[i]
            self.outlets[i].status = outlet_statuses[i]

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
    def master_switch(self, command):
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

    def __str__(self):
        return "{} ({}): {}".format(self.name, self.index, self.status)
