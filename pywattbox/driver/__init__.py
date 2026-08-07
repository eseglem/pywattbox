from typing import Final

# Every message the WattBox Integration Protocol sends is LF-terminated, so each
# alternative below requires a trailing newline. The previous pattern relied on
# `^` / `\n$` written outside the alternation, which (because `|` has the lowest
# precedence) anchored only the first and last branches -- the middle branches
# could match mid-stream and cause `_read_until_prompt` to return a truncated
# buffer.
#
# The value part is `[^\n]*` rather than `\S+` because values legitimately
# contain spaces, e.g. a WB-800VPS-IPVM-12 replies:
#   ?OutletName={Synology},{VMWare},{USB Drive 1},{Outlet 4},...
# `\S+` stops at the first space, so the prompt never matched the full line.
PROMPTS: Final[str] = (
    r"(?:"
    r"(?:.*Successfully Logged In!)"  # After Login
    r"|(?:\?\w+=[^\n]*)"  # Response to `?` request message
    r"|(?:OK)"  # Response to `!` control message
    r"|(?:#Error)"  # Error Message
    r")\n"  # All responses are newline terminated
)
