from typing import Final

PROMPTS: Final[str] = (
    r"^"  # Start of the string
    r"(.*Successfully Logged In!)|"  # After Login
    r"(\?\w+=\S+)|"  # Response to `?` request message
    r"(OK)|"  # Response to `!` control message
    r"(#Error)"  # Error Message
    r"\n$"  # Newline / End of String
)
