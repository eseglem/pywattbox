"""Tests for the channel prompt pattern.

scrapli compiles ``PROMPTS`` with ``re.M | re.I`` and searches it against the
read buffer to decide when a reply is complete. Two properties therefore
matter, and neither held before this change:

1. every alternative must be anchored, or the pattern matches mid-line
2. a ``?Key=value`` reply must match in full, or the driver treats a truncated
   prefix as a complete response
"""

from __future__ import annotations

import re

import pytest

from pywattbox.driver import PROMPTS

from .fixtures import WB800_IPVM_6

PATTERN = re.compile(PROMPTS.encode(), flags=re.M | re.I)


def _line(command: str) -> bytes:
    """The reply line as the channel sees it: no trailing newline.

    scrapli's ``_process_read_buf`` partitions the buffer on ``\\n`` before
    searching, so the pattern is applied to the bare line.
    """
    return WB800_IPVM_6[command].rstrip(b"\r\n")


@pytest.mark.parametrize(
    "command",
    [
        "?Model",
        "?Firmware",
        "?ServiceTag",
        "?Hostname",
        "?OutletCount",
        "?OutletStatus",
        "?PowerStatus",
        "?AutoReboot",
        "?UPSConnection",
        "?OutletPowerStatus=1",
    ],
)
def test_simple_replies_match_in_full(command: str) -> None:
    line = _line(command)
    match = PATTERN.search(line)
    assert match is not None, f"no match for {line!r}"
    assert match.group(0) == line, (
        f"matched only {match.group(0)!r} of {line!r} -- a partial match makes "
        "the channel return a truncated buffer"
    )


def test_outlet_name_with_spaces_matches_in_full() -> None:
    """The regression that breaks every poll on a deployed unit.

    ``?OutletName`` is in UPDATE_BASE_REQUESTS, and real outlet names contain
    spaces. With ``\\S+`` the pattern matched only ``?OutletName={Apple``.
    """
    line = _line("?OutletName")
    assert b" " in line, "fixture must exercise a value containing spaces"

    match = PATTERN.search(line)
    assert match is not None, f"no match for {line!r}"
    assert match.group(0) == line, f"matched only {match.group(0)!r} of {line!r}"


def test_error_reply_matches() -> None:
    assert PATTERN.search(b"#Error") is not None


def test_control_ok_matches() -> None:
    assert PATTERN.search(b"OK") is not None


def test_login_success_matches() -> None:
    assert PATTERN.search(b"Successfully Logged In!") is not None


def test_alternatives_are_anchored() -> None:
    """A reply must not match part-way through a line.

    Without a non-capturing group around the alternation, ``^`` binds only to
    the first alternative and ``\\n$`` only to the last, leaving the
    ``?Key=value`` branch free to match anywhere in the buffer.
    """
    assert PATTERN.search(b"trailing junk ?Model=X") is None
    assert PATTERN.search(b"login banner text OK to proceed") is None


def test_value_containing_a_question_mark_matches_in_full() -> None:
    """Outlet names are user supplied and may contain anything printable."""
    line = b"?OutletName={What? Yes},{Free}"
    match = PATTERN.search(line)
    assert match is not None
    assert match.group(0) == line
