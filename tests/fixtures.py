"""Wire-level fixtures for WB-800-IPVM-6, firmware 2.10.0.0.

Transcribed from a live capture of a deployed unit (dropbear_2025.88 SSH
server, telnet API on port 23). Response *shapes*, field counts, numeric
formats and framing are verbatim. The service tag and outlet names are
substitutes chosen to preserve the properties under test -- embedded spaces,
digits, varying lengths and repeated values -- without identifying a real
site.

What the capture established, some of it contrary to
eseglem/hass-wattbox#55:

* **No echo over telnet.** Each request produces exactly one line: the reply.
  Nothing else is sent.
* **Login is LF-framed, not CRLF**, and arrives as
  ``Please Login to Continue\\n`` then ``Username: `` then ``Password: `` then
  ``Successfully Logged In!\\n``. There is no telnet IAC option negotiation at
  all -- it is a raw line protocol.
* **Values contain spaces.** ``?OutletName`` returns brace-wrapped names such
  as ``{Media Bridge 1 to 3}``.
* **A unit with no UPS still answers ``?UPSStatus`` with a valid tuple**, not
  an error. ``?UPSConnection=0`` and ``?UPSStatus=0,0,Good,False,0,False,False``
  coexist happily.
* **No request in the read-only set produced ``#Error``.** The error path is
  still handled by the driver because the protocol documents it, but it is not
  exercised by this hardware and is covered separately below.
"""

from __future__ import annotations

# Brace wrapped, comma separated, with embedded spaces and digits. A parser
# that reads only up to the first whitespace truncates these.
OUTLET_NAMES = (
    "Media Bridge 1 to 3",
    "Streaming Box 06 Study",
    "HDMI Adapter Main Lounge",
    "Display 07 Study",
    "Free",
    "Free",
)

WB800_IPVM_6: dict[str, bytes] = {
    "?Model": b"?Model=WB-800-IPVM-6\n",
    "?Firmware": b"?Firmware=2.10.0.0\n",
    "?ServiceTag": b"?ServiceTag=ST000000000000\n",
    # The 800s report a generic hostname unless one has been configured.
    "?Hostname": b"?Hostname=WattBox\n",
    "?OutletCount": b"?OutletCount=6\n",
    "?OutletName": (
        "?OutletName=" + ",".join("{" + n + "}" for n in OUTLET_NAMES) + "\n"
    ).encode(),
    "?OutletStatus": b"?OutletStatus=1,1,1,1,1,1\n",
    # current, power, voltage, safe-voltage flag. The flag reads 0 while the
    # unit's own indicator is green, which is why IpWattBox inverts it.
    "?PowerStatus": b"?PowerStatus=0.43,68.87,119.88,0\n",
    "?AutoReboot": b"?AutoReboot=0\n",
    "?UPSConnection": b"?UPSConnection=0\n",
    # Captured from a unit with no UPS attached.
    "?UPSStatus": b"?UPSStatus=0,0,Good,False,0,False,False\n",
    # index, power, current, voltage
    "?OutletPowerStatus=1": b"?OutletPowerStatus=1,12.62,0.09,119.88\n",
    "?OutletPowerStatus=2": b"?OutletPowerStatus=2,21.40,0.18,119.88\n",
    "?OutletPowerStatus=3": b"?OutletPowerStatus=3,4.20,0.04,119.88\n",
    "?OutletPowerStatus=4": b"?OutletPowerStatus=4,29.86,0.25,119.88\n",
    "?OutletPowerStatus=5": b"?OutletPowerStatus=5,0.00,0.00,119.88\n",
    "?OutletPowerStatus=6": b"?OutletPowerStatus=6,0.79,0.00,119.88\n",
}

#: Not observed on WB-800-IPVM-6 / fw 2.10.0.0, but documented by the protocol
#: and reported by other integrators. Used to pin the driver's error handling
#: so an unsupported request degrades to a failed response rather than hanging.
ERROR_REPLIES: dict[str, bytes] = {"?UPSStatus": b"#Error\n"}

#: Control messages answer with a bare OK. Never sent to real hardware.
CONTROL_OK: dict[str, bytes] = {
    "!OutletSet=1,ON,0": b"OK\n",
    "!OutletSet=1,OFF,0": b"OK\n",
}

# Login sequence, verbatim from the capture. Note LF, not CRLF.
LOGIN_BANNER = b"Please Login to Continue\n"
LOGIN_USERNAME_PROMPT = b"Username: "
LOGIN_PASSWORD_PROMPT = b"Password: "
LOGIN_SUCCESS = b"Successfully Logged In!\n"
