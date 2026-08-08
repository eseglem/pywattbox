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
    r")\n?$"  # Optional trailing newline, anchored to end of line
)
# The trailing newline must stay OPTIONAL: scrapli's `_process_read_buf`
# partitions the read buffer on the first newline and hands the regex only the
# remainder, so by the time a single-line response is searched its terminating
# newline has already been stripped. Requiring `\n` here makes the prompt never
# match and every read blocks until the transport times out.
