"""Minimal YAML-subset reader/writer (Python standard library only).

Why this exists
---------------
The governance files are *hand-edited YAML*, but this repository must stay
stdlib-only (no PyYAML dependency, not even for tooling). This module implements
exactly the YAML subset those files use and rejects everything else loudly
instead of guessing.

Documented subset
-----------------
* one document per file; a leading ``---`` and/or trailing ``...`` is allowed;
* ``#`` comments outside quotes (``#`` must start the line or follow
  whitespace);
* block mappings ``key: value`` with space indentation; quoted keys allowed;
* block sequences ``- item``, including ``- key: value`` mapping items;
* nesting by indentation (spaces only; tabs in indentation are rejected); any
  consistent step is accepted, a dedent must return to an enclosing level;
* scalars: plain, single-quoted (``''`` escapes a quote) and double-quoted
  (``\\n \\t \\r \\" \\\\ \\uXXXX`` escapes);
* plain scalar types: ``true``/``false`` (case-insensitive), ``null``/``~``,
  decimal integers, decimal floats; everything else is a string;
* block scalars ``|`` (literal) and ``>`` (folded) with ``-``/``+`` chomping;
* duplicate mapping keys are rejected.

Explicitly NOT supported (raises :class:`YamlSubsetError`)
----------------------------------------------------------
flow collections (``[a, b]``, ``{a: b}``), anchors/aliases/tags, merge keys,
multiple documents, tabs used for indentation, multi-line quoted scalars,
indentation indicators on block scalars.

Errors always carry the file path and 1-based line number so a gate failure
points at the edit that broke the file.
"""

from __future__ import annotations

import re

__all__ = ["YamlSubsetError", "loads", "load", "dumps"]


class YamlSubsetError(ValueError):
    """Raised when a file leaves the documented YAML subset."""

    def __init__(self, message: str, path: str | None = None, line: int | None = None) -> None:
        self.message = message
        self.path = path
        self.line = line
        where = ""
        if path is not None:
            where = path
            if line is not None:
                where = "%s:%d" % (path, line)
            where += ": "
        elif line is not None:
            where = "line %d: " % line
        super().__init__(where + message)


_INT_RE = re.compile(r"-?(?:0|[1-9][0-9]*)\Z")
_FLOAT_RE = re.compile(r"-?(?:0|[1-9][0-9]*)\.[0-9]+(?:[eE][-+]?[0-9]+)?\Z")
_NULLS = {"~", "null", "Null", "NULL"}
_FLOW_START = set("[{")
_RESERVED_START = set("&*!@`]},%")


def _strip_comment(text: str) -> str:
    """Remove a YAML comment, ignoring ``#`` inside quoted scalars."""
    quote = None
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if quote == "'":
            if ch == "'":
                if i + 1 < n and text[i + 1] == "'":
                    i += 2
                    continue
                quote = None
        elif quote == '"':
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                quote = None
        else:
            if ch in "'\"":
                quote = ch
            elif ch == "#" and (i == 0 or text[i - 1] in " \t"):
                return text[:i]
        i += 1
    return text


def _find_pair_colon(text: str) -> int:
    """Return the index of the ``:`` that separates a mapping key, or -1."""
    quote = None
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if quote == "'":
            if ch == "'":
                if i + 1 < n and text[i + 1] == "'":
                    i += 2
                    continue
                quote = None
        elif quote == '"':
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                quote = None
        else:
            if ch in "'\"":
                quote = ch
            elif ch == ":" and (i + 1 == n or text[i + 1] in " \t"):
                return i
        i += 1
    return -1


def _parse_single_quoted(text: str, path: str | None, line: int) -> tuple[str, int]:
    out = []
    i = 1
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "'":
            if i + 1 < n and text[i + 1] == "'":
                out.append("'")
                i += 2
                continue
            return "".join(out), i + 1
        out.append(ch)
        i += 1
    raise YamlSubsetError("unterminated single-quoted scalar", path, line)


_ESCAPES = {
    "\\": "\\",
    '"': '"',
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "0": "\0",
}


def _parse_double_quoted(text: str, path: str | None, line: int) -> tuple[str, int]:
    out = []
    i = 1
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == '"':
            return "".join(out), i + 1
        if ch == "\\":
            if i + 1 >= n:
                raise YamlSubsetError("dangling escape in double-quoted scalar", path, line)
            esc = text[i + 1]
            if esc in _ESCAPES:
                out.append(_ESCAPES[esc])
                i += 2
                continue
            if esc == "u":
                hexpart = text[i + 2 : i + 6]
                if len(hexpart) != 4 or not all(c in "0123456789abcdefABCDEF" for c in hexpart):
                    raise YamlSubsetError("bad \\u escape in double-quoted scalar", path, line)
                out.append(chr(int(hexpart, 16)))
                i += 6
                continue
            raise YamlSubsetError("unsupported escape \\%s" % esc, path, line)
        out.append(ch)
        i += 1
    raise YamlSubsetError("unterminated double-quoted scalar", path, line)


def _parse_quoted_scalar(text: str, path: str | None, line: int) -> tuple[str, int]:
    if text[0] == "'":
        value, end = _parse_single_quoted(text, path, line)
    else:
        value, end = _parse_double_quoted(text, path, line)
    rest = text[end:].strip()
    if rest:
        raise YamlSubsetError(
            "unexpected text after quoted scalar: %r" % rest, path, line
        )
    return value, end


def _parse_scalar(text: str, path: str | None, line: int) -> object:
    s = _strip_comment(text).strip()
    if s == "":
        return None
    if s[0] == "'":
        return _parse_quoted_scalar(s, path, line)[0]
    if s[0] == '"':
        return _parse_quoted_scalar(s, path, line)[0]
    low = s.lower()
    if low in _NULLS or s in _NULLS:
        return None
    if low == "true":
        return True
    if low == "false":
        return False
    if _INT_RE.match(s):
        return int(s)
    if _FLOAT_RE.match(s):
        return float(s)
    if s == "[]":
        return []
    if s == "{}":
        return {}
    if s[0] in _FLOW_START:
        raise YamlSubsetError(
            "flow collections are not supported by the governance YAML subset: %r"
            % s,
            path,
            line,
        )
    if s[0] in _RESERVED_START:
        raise YamlSubsetError(
            "reserved YAML indicator %r is not supported: %r" % (s[0], s), path, line
        )
    if s[0] in "-?:" and (len(s) == 1 or s[1] in " \t"):
        raise YamlSubsetError("ambiguous plain scalar: %r" % s, path, line)
    if ": " in s:
        raise YamlSubsetError(
            "plain scalar contains ': ' (colon-space), which is ambiguous: %r" % s,
            path,
            line,
        )
    return s


def _is_sequence_line(text: str) -> bool:
    return text == "-" or text.startswith("- ")


class _Parser:
    def __init__(self, text: str, path: str | None) -> None:
        self.path = path
        # Normalise CRLF so a CR cannot leak into scalars or block content.
        self.raw_lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        self.i = 0
        self.n = len(self.raw_lines)

    # -- line helpers -----------------------------------------------------

    def _error(self, message: str, line: int | None = None) -> "YamlSubsetError":
        return YamlSubsetError(message, self.path, line if line is not None else self.i + 1)

    def _indent_text(self, index: int) -> tuple[int, str]:
        raw = self.raw_lines[index]
        leading = raw[: len(raw) - len(raw.lstrip(" \t"))]
        if "\t" in leading:
            raise self._error("tabs are not allowed in indentation", index + 1)
        indent = len(leading)
        return indent, raw[indent:].rstrip()

    def _skip(self) -> None:
        while self.i < self.n:
            text = self.raw_lines[self.i].strip()
            if text == "" or text.startswith("#"):
                self.i += 1
                continue
            return

    def _peek(self) -> tuple[int, str] | None:
        self._skip()
        if self.i >= self.n:
            return None
        return self._indent_text(self.i)

    # -- entry point ------------------------------------------------------

    def parse(self) -> object:
        self._skip()
        if self.i < self.n and self.raw_lines[self.i].strip() == "---":
            self.i += 1
        self._skip()
        if self.i >= self.n:
            return None
        indent, text = self._indent_text(self.i)
        if indent != 0:
            raise self._error("document must start at column 0")
        value = self._parse_block(0)
        self._skip()
        if self.i < self.n and self.raw_lines[self.i].strip() == "...":
            self.i += 1
            self._skip()
        if self.i < self.n:
            raise self._error(
                "unexpected content after the document (line %d)"
                % (self.i + 1)
            )
        return value

    def _parse_block(self, indent: int) -> object:
        if self.i >= self.n:
            return None
        got_indent, text = self._indent_text(self.i)
        if got_indent != indent:
            raise self._error(
                "inconsistent indentation: expected %d spaces, found %d"
                % (indent, got_indent)
            )
        if _is_sequence_line(text):
            return self._parse_sequence(indent)
        return self._parse_mapping(indent)

    # -- mappings ---------------------------------------------------------

    def _split_pair(self, text: str, line: int) -> tuple[str, str]:
        idx = _find_pair_colon(text)
        if idx < 0:
            raise self._error("expected 'key: value', found %r" % text, line)
        key_text = text[:idx].strip()
        if key_text == "":
            raise self._error("empty mapping key", line)
        if key_text[0] in "'\"":
            key, end = _parse_quoted_scalar(key_text, self.path, line)
            if key_text[end:].strip():
                raise self._error("unexpected text after quoted key", line)
        else:
            if any(ch in "[]{}#" for ch in key_text):
                raise self._error(
                    "unsupported character in mapping key %r" % key_text, line
                )
            key = key_text
        return key, text[idx + 1 :].strip()

    def _parse_mapping(self, indent: int) -> dict:
        result: dict = {}
        while True:
            peek = self._peek()
            if peek is None:
                break
            got_indent, text = peek
            if got_indent < indent:
                break
            if got_indent > indent:
                raise self._error(
                    "unexpected indentation: expected %d spaces, found %d"
                    % (indent, got_indent)
                )
            line = self.i + 1
            if _is_sequence_line(text):
                raise self._error("sequence item where a mapping key was expected", line)
            key, rest = self._split_pair(text, line)
            if key in result:
                raise self._error("duplicate mapping key %r" % key, line)
            self.i += 1
            if rest == "" or rest.startswith("#"):
                nxt = self._peek()
                if nxt is not None and nxt[0] > indent:
                    value = self._parse_block(nxt[0])
                else:
                    value = None
            elif rest[0] in "|>":
                value = self._parse_block_scalar(rest, indent, line)
            else:
                value = _parse_scalar(rest, self.path, line)
            result[key] = value
        return result

    # -- sequences --------------------------------------------------------

    def _parse_sequence(self, indent: int) -> list:
        items: list = []
        while True:
            peek = self._peek()
            if peek is None:
                break
            got_indent, text = peek
            if got_indent < indent:
                break
            if got_indent > indent:
                raise self._error(
                    "unexpected indentation in sequence: expected %d, found %d"
                    % (indent, got_indent)
                )
            if not _is_sequence_line(text):
                break
            line = self.i + 1
            rest = "" if text == "-" else text[2:].strip()
            self.i += 1
            if rest == "" or rest.startswith("#"):
                nxt = self._peek()
                if nxt is not None and nxt[0] > indent:
                    items.append(self._parse_block(nxt[0]))
                else:
                    items.append(None)
            elif rest[0] in "|>":
                raise self._error(
                    "block scalar sequence items are not supported; use '- key: value'",
                    line,
                )
            elif _find_pair_colon(rest) > 0:
                items.append(self._parse_inline_mapping_item(rest, indent, line))
            else:
                items.append(_parse_scalar(rest, self.path, line))
        return items

    def _parse_inline_mapping_item(self, rest: str, seq_indent: int, line: int) -> dict:
        key, tail = self._split_pair(rest, line)
        item: dict = {}
        if tail == "" or tail.startswith("#"):
            raise self._error(
                "a sequence mapping item must have an inline value on the '- ' line",
                line,
            )
        if tail[0] in "|>":
            raise self._error(
                "block scalar as the first value of a sequence mapping item is unsupported",
                line,
            )
        item[key] = _parse_scalar(tail, self.path, line)
        nxt = self._peek()
        if nxt is not None and nxt[0] > seq_indent:
            continuation = self._parse_mapping(nxt[0])
            for extra_key, extra_value in continuation.items():
                if extra_key in item:
                    raise self._error(
                        "duplicate mapping key %r" % extra_key, self.i + 1
                    )
                item[extra_key] = extra_value
        return item

    # -- block scalars ----------------------------------------------------

    def _parse_block_scalar(self, header: str, parent_indent: int, line: int) -> str:
        header = _strip_comment(header).strip()
        style = header[0]
        chomp = ""
        for ch in header[1:]:
            if ch in "+-":
                chomp = ch
            elif ch in "123456789":
                raise self._error(
                    "block scalar indentation indicators are not supported", line
                )
            elif ch != " ":
                raise self._error("bad block scalar header %r" % header, line)
        content: list[str] = []
        content_indent: int | None = None
        while self.i < self.n:
            raw = self.raw_lines[self.i]
            if raw.strip() == "":
                content.append("")
                self.i += 1
                continue
            leading = raw[: len(raw) - len(raw.lstrip(" \t"))]
            if "\t" in leading:
                raise self._error(
                    "tabs are not allowed in block scalar indentation", self.i + 1
                )
            indent = len(leading)
            if indent <= parent_indent:
                break
            if content_indent is None:
                content_indent = indent
            if indent < content_indent:
                raise self._error(
                    "inconsistent block scalar indentation (expected >= %d spaces)"
                    % content_indent,
                    self.i + 1,
                )
            content.append(raw[content_indent:])
            self.i += 1
        # Trim trailing blank lines that only mark the end of the block; the
        # chomping indicator decides how many newlines survive.
        while content and content[-1] == "":
            content.pop()
        if style == "|":
            text = "\n".join(content)
        else:
            folded: list[str] = []
            for piece in content:
                if piece == "":
                    folded.append("\n")
                elif folded and folded[-1] not in ("\n",) and not folded[-1].endswith(" "):
                    folded.append(" " + piece)
                else:
                    folded.append(piece)
            text = "".join(folded)
        if not content:
            return ""
        if chomp == "-":
            return text.rstrip("\n")
        if chomp == "+":
            return text + "\n"
        return text.rstrip("\n") + "\n"


def loads(text: str, path: str | None = None) -> object:
    """Parse a YAML-subset document. Raises :class:`YamlSubsetError`."""
    if not isinstance(text, str):
        raise TypeError("loads() expects str, got %r" % type(text).__name__)
    return _Parser(text, path).parse()


def load(path: str) -> object:
    """Parse the UTF-8 file at *path*."""
    with open(path, "r", encoding="utf-8") as handle:
        return loads(handle.read(), path=path)


# -- minimal deterministic writer ----------------------------------------

_PLAIN_SAFE = re.compile(r"[A-Za-z0-9_./@+-][A-Za-z0-9_./@+ :#()-]*\Z")
_LOOKS_TYPED = re.compile(
    r"(?:true|false|null|~|-?[0-9]+(?:\.[0-9]+)?)\Z", re.IGNORECASE
)


def _needs_quotes(value: str) -> bool:
    if value == "":
        return True
    if value != value.strip():
        return True
    if not _PLAIN_SAFE.match(value):
        return True
    if _LOOKS_TYPED.match(value):
        return True
    if ": " in value or " #" in value or value.startswith(("#", "- ", "? ", ": ")):
        return True
    return False


def _quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    escaped = escaped.replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r")
    return '"%s"' % escaped


def _format_scalar(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value) if isinstance(value, float) else str(value)
    if isinstance(value, str):
        return _quote(value) if _needs_quotes(value) else value
    if isinstance(value, list) and not value:
        return "[]"
    if isinstance(value, dict) and not value:
        return "{}"
    raise TypeError("cannot serialise %r" % (value,))


def _dump_block(value: object, indent: int, lines: list[str]) -> None:
    pad = " " * indent
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("mapping keys must be strings, got %r" % (key,))
            key_text = key if _PLAIN_SAFE.match(key) and ": " not in key else _quote(key)
            if isinstance(item, dict) and item:
                lines.append("%s%s:" % (pad, key_text))
                _dump_block(item, indent + 2, lines)
            elif isinstance(item, list) and item:
                lines.append("%s%s:" % (pad, key_text))
                _dump_block(item, indent + 2, lines)
            else:
                lines.append("%s%s: %s" % (pad, key_text, _format_scalar(item)))
        return
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict) and item:
                first_key = next(iter(item))
                first_value = item[first_key]
                if isinstance(first_value, (dict, list)) and first_value:
                    raise TypeError("nested non-scalar first key in sequence item")
                key_text = (
                    first_key
                    if _PLAIN_SAFE.match(first_key) and ": " not in first_key
                    else _quote(first_key)
                )
                lines.append(
                    "%s- %s: %s" % (pad, key_text, _format_scalar(first_value))
                )
                rest = {k: v for k, v in item.items() if k != first_key}
                _dump_block(rest, indent + 2, lines)
            elif isinstance(item, (dict, list)):
                raise TypeError("empty collection sequence items are unsupported")
            else:
                lines.append("%s- %s" % (pad, _format_scalar(item)))
        return
    raise TypeError("cannot serialise %r" % (value,))


def dumps(value: object) -> str:
    """Serialise a mapping/list of scalars to the documented YAML subset."""
    lines: list[str] = []
    if isinstance(value, dict):
        _dump_block(value, 0, lines)
    elif isinstance(value, list):
        _dump_block(value, 0, lines)
    else:
        return _format_scalar(value) + "\n"
    return "\n".join(lines) + "\n"
