"""Shared protocol helpers for the WattBox IP (telnet/SSH) drivers.

The WattBox "Integration Protocol" is line oriented. Every message is a single
line terminated by ``\\n``:

* ``?Key=value``  -- reply to a ``?`` request message
* ``OK``          -- reply to a ``!`` control message
* ``#Error``      -- the request was rejected or is unsupported

Two properties of real hardware shape everything below, both confirmed against
WB-800-IPVM units on firmware 2.10.0.0:

* **Values may contain spaces, commas, braces and parentheses.** Outlet names
  are user supplied, e.g. ``?OutletName={Media Bridge 1 to 3},{Free}``.
* **Commands are not echoed over raw telnet.** They are echoed over SSH. Any
  parsing that assumes a fixed line index therefore breaks on one transport or
  the other.
"""

from __future__ import annotations

import re
from typing import Final, Pattern

#: Channel prompt pattern, compiled by scrapli with ``re.M | re.I``.
#:
#: Used by ``_read_until_prompt`` during login. Note that scrapli's
#: ``_process_read_buf`` partitions the buffer on ``\n`` and searches what
#: remains, so the trailing newline is *not* visible to this pattern -- a
#: pattern requiring ``\n`` can never match, which is why the old ``#Error``
#: branch never fired. Each alternative is wrapped in a non-capturing group so
#: that ``^`` and ``$`` anchor all of them; without the group, alternation
#: binds looser than the anchors and every branch except the first and last
#: floats free, matching mid-line.
PROMPTS: Final[str] = (
    r"^(?:"
    r"(?:.*Successfully Logged In!)"  # After login
    r"|(?:\?\w+(?:=[^\r\n]*)?)"  # Response to a `?` request message
    r"|(?:OK)"  # Response to a `!` control message
    r"|(?:#Error)"  # Error message
    r")[ \t]*\r?$"
)

#: Transport names that speak plain telnet rather than SSH. Compare against
#: ``driver.transport_name``; ``driver.transport`` is a transport *object* and
#: will never equal any of these strings.
TELNET_TRANSPORTS: Final[tuple[str, ...]] = ("telnet", "asynctelnet")

#: Login prompts presented in-channel by the 800 series.
USERNAME_PROMPT: Final[bytes] = b"Username:"
PASSWORD_PROMPT: Final[bytes] = b"Password:"
LOGIN_SUCCESS: Final[bytes] = b"Successfully Logged In"

ERROR_MESSAGE: Final[str] = "#Error"


def _reply_body(command: str) -> bytes:
    """Regex body matching a valid reply line for *command*."""
    if command.startswith("?"):
        # `?OutletPowerStatus=1` requests carry an argument; the reply repeats
        # the key, so match on the key alone.
        key = re.escape(command.split("=", 1)[0].encode())
        return rb"(?:" + key + rb"=(?P<value>[^\r\n]*)|(?P<error>#Error))"
    return rb"(?:(?P<value>OK)|(?P<error>#Error))"


def reply_patterns(command: str) -> tuple[Pattern[bytes], Pattern[bytes]]:
    """Return ``(strict, lenient)`` patterns matching a reply to *command*.

    The strict pattern requires the terminating newline, which is what makes
    incremental reads safe: without it a reply still arriving in pieces --
    ``?OutletName={Media Brid`` -- looks like a complete line and would be
    accepted truncated.

    The lenient pattern drops that requirement and is used only as a fallback
    once reading has stopped, for a device that closes without a final newline.
    """
    body = _reply_body(command)
    strict = re.compile(rb"(?m)^" + body + rb"[ \t]*\r?\n")
    lenient = re.compile(rb"(?m)^" + body + rb"[ \t]*\r?$")
    return strict, lenient


def find_reply(buffer: bytes, command: str, *, strict: bool = True) -> bytes | None:
    """Extract the reply value for *command* from *buffer*, or ``None``.

    Skips a line that is merely the echoed command. This matters for requests
    carrying an argument: the echo of ``?OutletPowerStatus=1`` is itself a
    syntactically valid ``key=value`` line, so taking the first match would
    return the echo instead of the reading.
    """
    pattern = reply_patterns(command)[0 if strict else 1]
    encoded = command.encode()
    for match in pattern.finditer(buffer):
        if match.group(0).strip() == encoded:
            continue  # echoed command, not the reply
        if match.group("error") is not None:
            return ERROR_MESSAGE.encode()
        return match.group("value")
    return None
