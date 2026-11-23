"""Minimal PDF text-layer extraction, standard library only.

Why this exists
---------------
The most valuable document class in this project is the FDA 510(k) Summary and the PMA
SSED: they are the only public place where a manufacturer states, in its own words, what
the device does, which predicate it compares itself to, which bench tests it ran and how
it judged them. Nobody sells that as a corpus, and the core package has no third-party
dependencies, so it has to be read here.

What this is not
----------------
Not a PDF parser. It does not resolve the object graph, does not expand xref streams, and
does not run OCR. It walks the byte stream for content streams, undoes the transport-level
compression, and pulls the text-showing operators out of them. That is enough for the
born-digital PDFs the FDA publishes, and it is explicitly not enough for a scanned filing.

The extractor therefore never guesses. When it cannot find a text layer it returns
``has_text_layer=False`` with a machine-readable ``reason`` so the caller can record
"this document exists but needs OCR" instead of silently storing an empty record. An empty
string is a fact about our extractor; ``has_text_layer=False`` is a fact about the document.

Tested failure modes, named so a reader can tell which one they hit:

``not_a_pdf``          the payload has no ``%PDF`` header (usually an HTML error page)
``encrypted``          ``/Encrypt`` is present; the content is unreadable without a password
``no_content_stream``  no ``stream`` object was found at all
``no_text_operators``  content streams decoded but contain no ``Tj``/``TJ`` text operator
``text_too_short``     text was found but is below the plausible-document threshold,
                       which is the signature of a scanned image with a stub text layer
"""

from __future__ import annotations

import re
import zlib
from dataclasses import dataclass, field

#: A born-digital regulatory summary is thousands of characters. Anything below this is
#: almost certainly a scan stub ("Page 1 of 12") or a cover sheet.
MIN_PLAUSIBLE_CHARS = 200

#: Nested object streams (/ObjStm) are one compression level deep in practice. Two levels
#: covers a PDF 1.5 content stream without letting a malformed file drive unbounded work.
MAX_NESTING_DEPTH = 2

_STREAM_RE = re.compile(rb"stream\r?\n", re.DOTALL)
_ENDSTREAM_RE = re.compile(rb"\r?\nendstream")
_ENCRYPT_RE = re.compile(rb"/Encrypt\b")
_FILTER_RE = re.compile(rb"/Filter\s*(\[[^\]]*\]|/\w+)")
_ROOT_FILTER_RE = re.compile(rb"/FlateDecode")

_OCTAL_RE = re.compile(rb"\\([0-7]{1,3})")
_SIMPLE_ESCAPES = {
    b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f",
    b"(": b"(", b")": b")", b"\\": b"\\",
}


@dataclass
class PdfText:
    """The result of one extraction attempt."""

    text: str = ""
    has_text_layer: bool = False
    reason: str | None = None
    streams_found: int = 0
    streams_decoded: int = 0
    bytes_seen: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def char_count(self) -> int:
        return len(self.text)

    def summary(self) -> dict[str, object]:
        """A JSON-safe projection for ``RawRecord.extra``. Never carries the text itself."""
        return {
            "has_text_layer": self.has_text_layer,
            "reason": self.reason,
            "char_count": self.char_count,
            "streams_found": self.streams_found,
            "streams_decoded": self.streams_decoded,
            "extractor": "medradar.radar.pdf/1",
        }


def extract_text(data: bytes, *, min_chars: int = MIN_PLAUSIBLE_CHARS) -> PdfText:
    """Extract the text layer from a PDF payload.

    Returns a :class:`PdfText` and never raises on malformed input: a document we cannot
    read is a recorded outcome, not an exception that stops a 176k-document sweep.
    """
    result = PdfText(bytes_seen=len(data or b""))
    if not data:
        result.reason = "not_a_pdf"
        return result
    if b"%PDF" not in data[:1024]:
        result.reason = "not_a_pdf"
        return result
    if _ENCRYPT_RE.search(data[:200_000]):
        result.reason = "encrypted"
        return result

    streams = _iter_content_streams(data, depth=0, result=result)
    result.streams_found = result.streams_decoded
    if not result.streams_found:
        result.reason = "no_content_stream"
        return result

    pieces: list[str] = []
    for payload in streams:
        pieces.append(_text_from_content_stream(payload))
    text = _tidy("\n".join(piece for piece in pieces if piece))

    if not text:
        result.reason = "no_text_operators"
        return result
    if len(text) < min_chars:
        result.text = text
        result.reason = "text_too_short"
        return result
    result.text = text
    result.has_text_layer = True
    return result


# --------------------------------------------------------------------------- internals
def _iter_content_streams(data: bytes, *, depth: int, result: PdfText) -> list[bytes]:
    """Yield decompressed stream payloads, following one level of /ObjStm nesting."""
    payloads: list[bytes] = []
    cursor = 0
    while True:
        match = _STREAM_RE.search(data, cursor)
        if match is None:
            break
        start = match.end()
        end_match = _ENDSTREAM_RE.search(data, start)
        if end_match is None:
            result.notes.append("stream without endstream")
            break
        raw = data[start:end_match.start()]
        cursor = end_match.end()
        dictionary = data[max(0, match.start() - 800):match.start()]
        decoded = _decode_stream(raw, dictionary, result)
        if decoded is None:
            continue
        # The marker check has to run on the DECODED payload, not only on uncompressed streams.
        # Measured: a Flate stream inflating to a font or image blob passed the size cap and still
        # went to the operator regex, pinning a core. An image has no text object after inflating
        # either, so asking the question once, here, covers both cases.
        if not _looks_like_content_stream(decoded):
            continue
        result.streams_decoded += 1
        payloads.append(decoded)
        if depth + 1 < MAX_NESTING_DEPTH and b"/ObjStm" in dictionary:
            payloads.extend(_iter_content_streams(decoded, depth=depth + 1, result=result))
    return payloads


def _decode_stream(raw: bytes, dictionary: bytes, result: PdfText) -> bytes | None:
    filter_match = _FILTER_RE.search(dictionary)
    applies = bool(filter_match and _ROOT_FILTER_RE.search(filter_match.group(1))) or (
        filter_match is None and _ROOT_FILTER_RE.search(dictionary)
    )
    if not applies:
        # An uncompressed stream is still worth scanning: some generators skip Flate. But only
        # when it is actually a text content stream — see _CONTENT_MARKERS for the measured cost
        # of getting this wrong.
        candidate = raw.strip()
        if not candidate:
            return None
        if not _looks_like_content_stream(candidate):
            return None
        return candidate[:MAX_STREAM_BYTES]
    stripped = raw.strip(b"\r\n")
    for candidate in (stripped, raw):
        try:
            decoded = zlib.decompress(candidate)
        except zlib.error:
            continue
        # A Flate stream can also be an inflate bomb. Bound it rather than trusting the producer.
        return decoded[:MAX_STREAM_BYTES]
    # Raw deflate without the zlib wrapper.
    try:
        return zlib.decompressobj(-15).decompress(stripped)[:MAX_STREAM_BYTES]
    except zlib.error:
        result.notes.append("flate stream failed to decompress")
        return None


_OP_RE = re.compile(
    rb"""
      (?P<arr>\[[^\]\\]*(?:\\.[^\]\\]*)*\])\s*TJ
    | (?P<lit>\([^\\()]*(?:\\.[^\\()]*)*\))\s*(?:Tj|'|")
    | (?P<hex><[0-9A-Fa-f\s]+>)\s*Tj
    | (?P<td>-?[\d.]+\s+-?[\d.]+\s+(?:Td|TD))
    | (?P<tm>-?[\d.]+\s+-?[\d.]+\s+-?[\d.]+\s+-?[\d.]+\s+(-?[\d.]+)\s+(-?[\d.]+)\s+Tm)
    | (?P<star>T\*)
    """,
    re.VERBOSE | re.DOTALL,
)

#: Below this horizontal displacement two consecutive text runs are the same word: PDF
#: generators emit one run per glyph when letter-spacing is applied, and a space inserted
#: there turns "Food" into "F o o d". A quarter of the font size is a safe stand-in for
#: character width without resolving the font resource.
GLUE_DX = 2.5
#: Above this horizontal displacement the runs are separate cells and a space is real.
SPACE_DX = 8.0
#: Vertical displacement that constitutes a new line of the rendered page.
NEWLINE_DY = 1.5


#: A stream that is not Flate-compressed is still worth scanning, but only if it actually looks
#: like a text content stream. Measured failure: a scanned 510(k) carries multi-megabyte JPEG
#: image streams, and the previous code returned those as content streams, ran the operator
#: regex over binary data, and pinned one core for **fifteen minutes on a single document**
#: (py-spy stack: extract_text -> _text_from_content_stream). A text stream always opens a text
#: object and always shows something.
_CONTENT_MARKERS = (b"BT",)
_SHOW_MARKERS = (b"Tj", b"TJ")

#: Hard ceiling on bytes handed to the operator regex. A real text layer is tens to hundreds of
#: kilobytes; anything past this is an image or a font program wearing a stream's clothes.
MAX_STREAM_BYTES = 2_000_000

#: Hard ceiling on operators processed per stream. The regex cannot backtrack pathologically on
#: text, but a bound makes the worst case O(1) instead of "until the document ends".
MAX_OPERATORS = 400_000


def _looks_like_content_stream(payload: bytes) -> bool:
    if not payload:
        return False
    if not any(marker in payload for marker in _CONTENT_MARKERS):
        return False
    return any(marker in payload for marker in _SHOW_MARKERS)


def _text_from_content_stream(payload: bytes) -> str:
    """Walk the content stream once, in stream order, tracking the text position.

    The earlier version collected all text operators first and then tried to re-insert the
    breaks afterwards. That is unrecoverable: the break positions are a property of where
    the operator sat between two runs, and PDF generators that letter-space a heading emit
    one run per glyph, so re-insertion produced "U. S . F o o d". Reading in order and
    measuring the displacement keeps a heading a heading.
    """
    out: list[str] = []
    last_x: float | None = None
    last_y: float | None = None
    operators = 0

    for match in _OP_RE.finditer(payload):
        operators += 1
        if operators > MAX_OPERATORS:
            out.append("\n")
            break
        if match.group("arr") is not None:
            segment = _array_text(match.group("arr"))
            if segment:
                out.append(segment)
            continue
        if match.group("lit") is not None:
            out.append(_decode_literal(match.group("lit")))
            continue
        if match.group("hex") is not None:
            out.append(_decode_hex(match.group("hex")[1:-1]))
            continue
        if match.group("td") is not None:
            numbers = match.group("td").split()
            dx, dy = _float(numbers[0]), _float(numbers[1])
            last_x = None if last_x is None else last_x + dx
            last_y = None if last_y is None else last_y + dy
            out.append(_separator(dx, dy, absolute=False))
            continue
        if match.group("tm") is not None:
            x, y = _float(match.group(6)), _float(match.group(7))
            dx = 0.0 if last_x is None else x - last_x
            dy = 0.0 if last_y is None else y - last_y
            last_x, last_y = x, y
            out.append(_separator(dx, dy, absolute=True))
            continue
        if match.group("star") is not None:
            out.append("\n")

    return _tidy("".join(part for part in out if part))


def _array_text(array: bytes) -> str:
    """A TJ array holds strings and kerning numbers; the numbers encode the gaps."""
    pieces: list[str] = []
    for token in re.finditer(rb"\((?:\\.|[^\\()])*\)|<[0-9A-Fa-f\s]+>|-?[\d.]+", array):
        value = token.group(0)
        if value.startswith(b"("):
            pieces.append(_decode_literal(value))
        elif value.startswith(b"<"):
            pieces.append(_decode_hex(value[1:-1]))
        else:
            kern = _float(value)
            # A large negative kern is the generator's way of writing a word space.
            if kern <= -120:
                pieces.append(" ")
    return "".join(pieces)


def _separator(dx: float, dy: float, *, absolute: bool) -> str:
    if absolute:
        # An absolute jump to a new baseline is a new line; sideways is a space.
        if abs(dy) > NEWLINE_DY:
            return "\n"
        if abs(dx) > SPACE_DX:
            return " "
        return ""
    if abs(dy) > NEWLINE_DY:
        return "\n"
    if abs(dx) > SPACE_DX:
        return " "
    if abs(dx) > GLUE_DX:
        return ""
    return ""


def _float(raw: bytes | str) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _decode_literal(token: bytes) -> str:
    body = token[1:-1]
    body = _OCTAL_RE.sub(lambda m: bytes([int(m.group(1), 8) & 0xFF]), body)
    for escape, replacement in _SIMPLE_ESCAPES.items():
        body = body.replace(b"\\" + escape, replacement)
    return body.decode("latin-1", "replace")


def _decode_hex(token: bytes) -> str:
    digits = re.sub(rb"\s", b"", token)
    if len(digits) % 2:
        digits += b"0"
    try:
        raw = bytes.fromhex(digits.decode("ascii"))
    except (ValueError, UnicodeDecodeError):
        return ""
    # A UTF-16BE string is the common case for a hex operand; latin-1 is the fallback.
    if len(raw) >= 2 and len(raw) % 2 == 0 and (raw[0] == 0 or raw[1] == 0):
        try:
            return raw.decode("utf-16-be")
        except UnicodeDecodeError:
            pass
    return raw.decode("latin-1", "replace")


def _tidy(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line).strip()


__all__ = ["MIN_PLAUSIBLE_CHARS", "PdfText", "extract_text"]
