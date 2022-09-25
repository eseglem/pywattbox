# Temporary fix until a new release of `h11`` makes it upstream to `httpx`
# See: https://github.com/python-hyper/h11/issues/133
# And: https://github.com/encode/httpx/discussions/1735

import re
import h11._readers
from h11._abnf import chunk_ext, chunk_header, chunk_size

# Add OWS from: https://github.com/python-hyper/h11/blob/master/h11/_abnf.py#L8
OWS = r"[ \t]*"
# Seperated this out so it can stay a raw string
END = r"\r\n"
# chunk_header from https://github.com/python-hyper/h11/blob/master/h11/_abnf.py#L125
# but as an f string
patched_chunk_header = (
    f"(?P<chunk_size>{chunk_size})(?P<chunk_ext>{chunk_ext})?{OWS}{END}"
)


def monkeypatch_h11() -> None:
    """Monkeypatch h11 to allow whitespace in chunk_header."""
    h11._readers.chunk_header_re = re.compile(patched_chunk_header.encode("ascii"))


def restore_h11() -> None:
    """Reset h11 to original chunk_header regex."""
    h11._readers.chunk_header_re = re.compile(chunk_header.encode("ascii"))
