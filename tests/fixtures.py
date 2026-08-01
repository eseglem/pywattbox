"""Wire-level fixtures for WB-800-IPVM units, firmware 2.10.0.0.

Response shapes are taken from the captures in eseglem/hass-wattbox#55 (real
WB-800-IPVM-12 and WB-820-IPVM-12) and adapted to a 6-outlet WB-800-IPVM-6.

Two properties of this protocol drive most of the driver's bugs, so the outlet
names here are deliberately realistic rather than tidy:

* values may contain spaces, parentheses and braces (``?OutletName``)
* every reply is a single ``?Key=value`` line terminated by ``\\n``, with no
  trailing CLI prompt and no command echo over raw telnet
"""

from __future__ import annotations

# Outlet names as they actually appear on a deployed unit: spaces, digits,
# parentheses. A driver that reads only up to the first whitespace truncates
# these, which is exactly the failure mode being guarded against.
OUTLET_NAMES = (
    "Media Bridge 1 to 3",
    "Display 07 Study",
    "Free",
    "HDMI Adapter Main Lounge",
    "Media Bridge 1 to 3",
    "Free",
)

WB800_IPVM_6: dict[str, bytes] = {
    "?Model": b"?Model=WB-800-IPVM-6\n",
    "?Firmware": b"?Firmware=2.10.0.0\n",
    "?ServiceTag": b"?ServiceTag=ST000000000000\n",
    "?Hostname": b"?Hostname=WattBox\n",
    "?OutletCount": b"?OutletCount=6\n",
    "?OutletName": (
        "?OutletName=" + ",".join("{" + n + "}" for n in OUTLET_NAMES) + "\n"
    ).encode(),
    "?OutletStatus": b"?OutletStatus=1,1,1,1,1,0\n",
    "?PowerStatus": b"?PowerStatus=0.4,48.0,120.0,0\n",
    "?AutoReboot": b"?AutoReboot=1\n",
    "?UPSConnection": b"?UPSConnection=0\n",
    "?OutletPowerStatus=1": b"?OutletPowerStatus=1,17.9,0.1,120.0\n",
    "?OutletPowerStatus=2": b"?OutletPowerStatus=2,21.4,0.2,120.0\n",
    "?OutletPowerStatus=3": b"?OutletPowerStatus=3,0.0,0.0,120.0\n",
    "?OutletPowerStatus=4": b"?OutletPowerStatus=4,4.2,0.0,120.0\n",
    "?OutletPowerStatus=5": b"?OutletPowerStatus=5,4.5,0.0,120.0\n",
    "?OutletPowerStatus=6": b"?OutletPowerStatus=6,0.0,0.0,120.0\n",
    # PROVISIONAL: the exact reply a unit with no UPS gives to ?UPSStatus has
    # not yet been captured from hardware -- `#Error` is the assumption being
    # tested, and this fixture must be reconciled against captures/ before the
    # upstream PR cites it. The driver is written so that either answer is
    # handled: `update_requests` skips ?UPSStatus entirely unless
    # ?UPSConnection reported a UPS, so this line only exercises the
    # error-reply path of the driver itself.
    "?UPSStatus": b"#Error\n",
}

# Control messages answer with a bare OK. Included so the driver's non-"?"
# path is covered; the tests never send these to real hardware.
CONTROL_OK: dict[str, bytes] = {
    "!OutletSet=1,ON,0": b"OK\n",
    "!OutletSet=1,OFF,0": b"OK\n",
}

LOGIN_BANNER = b"\r\nUsername: "
LOGIN_PASSWORD_PROMPT = b"\r\nPassword: "
LOGIN_SUCCESS = b"\r\nSuccessfully Logged In!\r\n"
