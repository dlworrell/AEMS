"""Dependency-free JSON and constrained-YAML loading.

AES-003 names ``aes-manifest.yaml`` as the standard repository entry point.
AEMS therefore cannot require every inspected repository to preinstall a YAML
package.  This module accepts JSON and the conservative YAML subset used by
Catalyst manifests: indentation-based mappings and sequences, scalar values,
and inline empty collections.

Unsupported YAML features fail closed with a line-numbered diagnostic instead
of being guessed.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any


class StructuredDataError(ValueError):
    """Raised when a structured input cannot be parsed safely."""


@dataclass(frozen=True)
class _Line:
    number: int
    indent: int
    text: str


_INTEGER = re.compile(r"[-+]?(?:0|[1-9][0-9]*)\Z")
_FLOAT = re.compile(
    r"[-+]?(?:[0-9]+\.[0-9]*|[0-9]*\.[0-9]+)(?:[eE][-+]?[0-9]+)?\Z"
)
_KEY = re.compile(r"[A-Za-z0-9_.-]+\Z")


def _strip_comment(text: str) -> str:
    quote: str | None = None
    escaped = False
    for index, character in enumerate(text):
        if escaped:
            escaped = False
            continue
        if character == "\\" and quote == '"':
            escaped = True
            continue
        if character in {"'", '"'}:
            if quote is None:
                quote = character
            elif quote == character:
                quote = None
            continue
        if character == "#" and quote is None:
            if index == 0 or text[index - 1].isspace():
                return text[:index].rstrip()
    return text.rstrip()


def _tokenize(text: str) -> list[_Line]:
    lines: list[_Line] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise StructuredDataError(f"line {number}: tabs are not valid indentation")
        stripped = _strip_comment(raw)
        if not stripped.strip() or stripped.lstrip().startswith("---"):
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        lines.append(_Line(number, indent, stripped.strip()))
    return lines


def _split_mapping(text: str, number: int) -> tuple[str, str]:
    quote: str | None = None
    escaped = False
    for index, character in enumerate(text):
        if escaped:
            escaped = False
            continue
        if character == "\\" and quote == '"':
            escaped = True
            continue
        if character in {"'", '"'}:
            if quote is None:
                quote = character
            elif quote == character:
                quote = None
            continue
        if (
            character == ":"
            and quote is None
            and (index + 1 == len(text) or text[index + 1].isspace())
        ):
            key = text[:index].strip()
            value = text[index + 1 :].strip()
            if not key:
                raise StructuredDataError(f"line {number}: empty mapping key")
            if not (_KEY.fullmatch(key) or key[:1] in {"'", '"'}):
                raise StructuredDataError(
                    f"line {number}: unsupported mapping key syntax: {key!r}"
                )
            return str(_parse_scalar(key, number)), value
    raise StructuredDataError(f"line {number}: expected a mapping entry")


def _parse_scalar(value: str, number: int) -> Any:
    value = value.strip()
    if not value:
        raise StructuredDataError(f"line {number}: missing scalar value")
    if value in {"null", "Null", "NULL", "~"}:
        return None
    if value in {"true", "True", "TRUE"}:
        return True
    if value in {"false", "False", "FALSE"}:
        return False
    if value == "[]":
        return []
    if value == "{}":
        return {}
    if value.startswith("[") or value.startswith("{"):
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise StructuredDataError(
                f"line {number}: inline collections must use JSON syntax: {exc.msg}"
            ) from exc
    if value.startswith('"'):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise StructuredDataError(
                f"line {number}: invalid quoted scalar: {exc.msg}"
            ) from exc
        if not isinstance(parsed, str):
            raise StructuredDataError(f"line {number}: expected a string scalar")
        return parsed
    if value.startswith("'"):
        if len(value) < 2 or not value.endswith("'"):
            raise StructuredDataError(f"line {number}: unterminated quoted scalar")
        return value[1:-1].replace("''", "'")
    if _INTEGER.fullmatch(value):
        return int(value)
    if _FLOAT.fullmatch(value):
        return float(value)
    if value.startswith(("&", "*", "!", "|", ">", "{", "[")):
        raise StructuredDataError(
            f"line {number}: YAML anchors, tags, block scalars, and flow syntax are unsupported"
        )
    return value


class _Parser:
    def __init__(self, lines: list[_Line]):
        self.lines = lines

    def parse(self) -> Any:
        if not self.lines:
            return {}
        value, index = self._parse_block(0, self.lines[0].indent)
        if index != len(self.lines):
            line = self.lines[index]
            raise StructuredDataError(
                f"line {line.number}: unexpected indentation or trailing content"
            )
        return value

    def _parse_block(self, index: int, indent: int) -> tuple[Any, int]:
        line = self.lines[index]
        if line.indent != indent:
            raise StructuredDataError(
                f"line {line.number}: expected indentation {indent}, found {line.indent}"
            )
        if line.text == "-" or line.text.startswith("- "):
            return self._parse_sequence(index, indent)
        return self._parse_mapping(index, indent)

    def _parse_mapping(
        self,
        index: int,
        indent: int,
        initial: tuple[str, str, int] | None = None,
    ) -> tuple[dict[str, Any], int]:
        result: dict[str, Any] = {}
        pending = initial
        while pending is not None or index < len(self.lines):
            if pending is None:
                line = self.lines[index]
                if line.indent < indent:
                    break
                if line.indent != indent or line.text == "-" or line.text.startswith("- "):
                    break
                key, raw_value = _split_mapping(line.text, line.number)
                number = line.number
                index += 1
            else:
                key, raw_value, number = pending
                pending = None

            if key in result:
                raise StructuredDataError(f"line {number}: duplicate key {key!r}")
            if raw_value:
                result[key] = _parse_scalar(raw_value, number)
                continue

            if index >= len(self.lines) or self.lines[index].indent <= indent:
                result[key] = None
                continue
            child_indent = self.lines[index].indent
            value, index = self._parse_block(index, child_indent)
            result[key] = value
        return result, index

    def _parse_sequence(self, index: int, indent: int) -> tuple[list[Any], int]:
        result: list[Any] = []
        while index < len(self.lines):
            line = self.lines[index]
            if line.indent < indent:
                break
            if line.indent != indent or not (
                line.text == "-" or line.text.startswith("- ")
            ):
                break
            content = line.text[1:].strip()
            index += 1
            if not content:
                if index >= len(self.lines) or self.lines[index].indent <= indent:
                    result.append(None)
                    continue
                value, index = self._parse_block(index, self.lines[index].indent)
                result.append(value)
                continue

            try:
                key, raw_value = _split_mapping(content, line.number)
            except StructuredDataError:
                result.append(_parse_scalar(content, line.number))
                continue

            item_indent = (
                self.lines[index].indent
                if index < len(self.lines) and self.lines[index].indent > indent
                else indent + 2
            )
            item, index = self._parse_mapping(
                index,
                item_indent,
                initial=(key, raw_value, line.number),
            )
            result.append(item)
        return result, index


def loads_structured(text: str, *, source: str = "<memory>") -> Any:
    """Load JSON or the supported YAML subset from ``text``."""

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        return _Parser(_tokenize(text)).parse()
    except StructuredDataError as exc:
        raise StructuredDataError(f"{source}: {exc}") from exc


def load_structured(path: Path) -> Any:
    """Load a JSON or YAML document from ``path``."""

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise StructuredDataError(f"{path}: {exc}") from exc
    return loads_structured(text, source=str(path))


def canonical_json(value: Any) -> str:
    """Return stable, newline-terminated JSON suitable for evidence hashing."""

    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
