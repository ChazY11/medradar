"""A small, dependency-free JSON-Schema subset engine used by the validator.

Why not ``jsonschema``?
-----------------------
The experiment has to be reproducible in an offline environment and
``pyproject.toml`` deliberately declares **no** runtime dependencies.  The two
schemas in :mod:`..schema` only use a small, explicitly chosen subset of Draft
2020-12, so this module implements exactly that subset instead of pretending to
be a general-purpose engine.  When the real ``jsonschema`` package happens to be
installed, the offline test suite cross-checks this engine against it on a
fixture matrix (``pytest.importorskip``), so the subset's semantics are pinned
to a reference implementation rather than to a comment.

Supported keywords
------------------
* ``$ref`` to a ``$id`` inside the supplied schema document, or to a local
  ``#/...`` JSON pointer (the schemas here only need the former);
* ``type`` -- a string or a list of strings.  ``"integer"`` follows Draft
  2020-12 (a number with zero fractional part: ``1`` and ``1.0`` are integers),
  except that ``True`` is *never* an integer; ``"number"`` means ``int``/``float``
  excluding ``bool``.  Python's ``bool`` is a subclass of ``int`` and silently
  coercing it would hide a real extraction bug, so it is rejected;
* ``required``, ``properties``, ``additionalProperties`` (``false`` or a
  subschema), ``enum``, ``const``, ``pattern``, ``minLength``, ``maxLength``,
  ``minimum``, ``maximum``, ``minItems``, ``maxItems``, ``items``;
* ``allOf`` and ``if``/``then`` (``else`` is also honoured, because it costs a
  few lines and makes the engine predictable).

Any other keyword is ignored, never guessed at.  Validation *never*
mutates the instance.  Findings carry a JSON-pointer path: ``""`` is the
instance root, ``"/evidence/0/quote"`` is the quote of the first evidence span,
etc.  Paths are reported for the reader, not used to poke at the payload.

Typical use::

    from .schema_validator import validate_event_payload, validate_result_payload

    finding_set = validate_event_payload(event.to_dict())
    if not finding_set.valid:
        ...
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

__all__ = [
    "SchemaEngineError",
    "SchemaFinding",
    "SchemaValidation",
    "SchemaValidator",
    "index_schemas",
    "validate_event_payload",
    "validate_result_payload",
]

_MAX_DEPTH = 64
"""Hard recursion limit.  A schema that needs more than this is a bug, and a
cycle through ``$ref`` is reported rather than followed forever."""

_SCHEMA_HINT_KEYS: tuple[str, ...] = (
    "type",
    "properties",
    "required",
    "items",
    "allOf",
    "anyOf",
    "oneOf",
    "enum",
    "const",
    "$ref",
)


class SchemaEngineError(ValueError):
    """The *schema* is malformed or a ``$ref`` cannot be resolved.

    This is never raised for a malformed *instance*: instance problems are
    returned as :class:`SchemaFinding` records so the validator can attach them
    to a quarantined event instead of crashing the whole run.
    """


@dataclass(frozen=True)
class SchemaFinding:
    """One instance/schema mismatch at a JSON-pointer path."""

    path: str
    keyword: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "keyword": self.keyword, "message": self.message}


@dataclass(frozen=True)
class SchemaValidation:
    """The outcome of validating one instance against one schema."""

    valid: bool
    findings: tuple[SchemaFinding, ...] = ()

    def __bool__(self) -> bool:
        return self.valid

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(finding.path for finding in self.findings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "findings": [finding.to_dict() for finding in self.findings],
        }


# --------------------------------------------------------------------- helpers
def _escape_pointer_part(part: Any) -> str:
    return str(part).replace("~", "~0").replace("/", "~1")


def _join_pointer(pointer: str, part: Any) -> str:
    return f"{pointer}/{_escape_pointer_part(part)}"


def _describe(instance: Any) -> str:
    """A short, deterministic description of an instance for a finding."""
    if isinstance(instance, bool):
        return f"boolean {instance!r}"
    if instance is None:
        return "null"
    if isinstance(instance, str):
        if len(instance) > 60:
            return f"string of {len(instance)} characters starting {instance[:40]!r}..."
        return f"string {instance!r}"
    if isinstance(instance, Mapping):
        return f"object with keys {sorted(str(key) for key in instance)}"
    if isinstance(instance, Sequence) and not isinstance(instance, (str, bytes)):
        return f"array of {len(instance)} items"
    return f"{type(instance).__name__} {instance!r}"


def _json_equal(one: Any, two: Any) -> bool:
    """JSON equality, with ``True != 1`` (Python's ``bool``/``int`` trap)."""
    if isinstance(one, bool) or isinstance(two, bool):
        return isinstance(one, bool) and isinstance(two, bool) and one == two
    if isinstance(one, str) or isinstance(two, str):
        return isinstance(one, str) and isinstance(two, str) and one == two
    if isinstance(one, (int, float)) and isinstance(two, (int, float)):
        return one == two
    if isinstance(one, Mapping) and isinstance(two, Mapping):
        if set(one) != set(two):
            return False
        return all(_json_equal(one[key], two[key]) for key in one)
    if (
        isinstance(one, Sequence)
        and isinstance(two, Sequence)
        and not isinstance(one, (str, bytes))
        and not isinstance(two, (str, bytes))
    ):
        if len(one) != len(two):
            return False
        return all(_json_equal(left, right) for left, right in zip(one, two))
    return one == two


def _type_matches(instance: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(instance, dict)
    if expected == "array":
        return isinstance(instance, list)
    if expected == "string":
        return isinstance(instance, str)
    if expected == "boolean":
        return isinstance(instance, bool)
    if expected == "null":
        return instance is None
    if expected == "integer":
        # Draft 2020-12: an integer is a number with a zero fractional part, so
        # ``1.0`` is an integer -- but ``True`` is not (bool subclasses int).
        if isinstance(instance, bool):
            return False
        if isinstance(instance, int):
            return True
        return isinstance(instance, float) and instance.is_integer()
    if expected == "number":
        return isinstance(instance, (int, float)) and not isinstance(instance, bool)
    raise SchemaEngineError(f"unsupported schema type {expected!r}")


def _is_number(instance: Any) -> bool:
    return isinstance(instance, (int, float)) and not isinstance(instance, bool)


def index_schemas(document: Any) -> dict[str, Mapping[str, Any]]:
    """Collect every subschema of ``document`` that carries an ``$id``.

    Also accepts a plain ``{id: schema}`` mapping (keys containing ``/`` whose
    values look like schemas), which keeps :class:`SchemaValidator` usable with
    a hand-assembled document in tests.
    """
    found: dict[str, Mapping[str, Any]] = {}

    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            schema_id = node.get("$id")
            if isinstance(schema_id, str) and schema_id not in found:
                found[schema_id] = node
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(document)
    if isinstance(document, Mapping):
        for key, value in document.items():
            if not isinstance(key, str) or not isinstance(value, Mapping):
                continue
            if key in found:
                continue
            if "/" not in key and not key.startswith("#"):
                continue
            if any(hint in value for hint in _SCHEMA_HINT_KEYS):
                found[key] = value
    return found


def _resolve_pointer(root: Any, pointer: str) -> Any:
    """Resolve a local JSON pointer such as ``#/$defs/x`` against ``root``."""
    if not pointer.startswith("#"):
        raise SchemaEngineError(f"not a local pointer: {pointer!r}")
    fragment = pointer[1:]
    if fragment == "":
        return root
    if not fragment.startswith("/"):
        raise SchemaEngineError(f"unsupported local reference {pointer!r}")
    current = root
    for raw_part in fragment[1:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            raise SchemaEngineError(f"unresolvable JSON pointer {pointer!r} at {part!r}")
    return current


class SchemaValidator:
    """Validate instances against a schema that may ``$ref`` other schemas."""

    def __init__(
        self,
        schema: Mapping[str, Any],
        *,
        document: Mapping[str, Any] | None = None,
        schemas: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> None:
        if not isinstance(schema, Mapping):
            raise SchemaEngineError("schema must be an object")
        self._schema = schema
        self._by_id: dict[str, Mapping[str, Any]] = {}
        if document is not None:
            self._by_id.update(index_schemas(document))
        if schemas:
            self._by_id.update(schemas)
        root_id = schema.get("$id")
        if isinstance(root_id, str):
            self._by_id.setdefault(root_id, schema)

    # -- construction helpers ------------------------------------------------
    @classmethod
    def from_document(cls, document: Mapping[str, Any], *, kind: str = "event") -> "SchemaValidator":
        """Build a validator for ``document[kind]`` (``"event"`` or ``"result"``)."""
        if kind not in ("event", "result"):
            raise SchemaEngineError(f"unknown schema kind {kind!r}; expected 'event' or 'result'")
        root = document.get(kind)
        if not isinstance(root, Mapping):
            raise SchemaEngineError(f"schema document has no {kind!r} schema")
        return cls(root, document=document)

    @property
    def schema(self) -> Mapping[str, Any]:
        return self._schema

    @property
    def known_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_id))

    # -- public API ----------------------------------------------------------
    def validate(self, instance: Any) -> SchemaValidation:
        findings: list[SchemaFinding] = []
        self._validate(
            instance,
            self._schema,
            "",
            findings,
            depth=0,
            ref_stack=(),
        )
        return SchemaValidation(valid=not findings, findings=tuple(findings))

    def is_valid(self, instance: Any) -> bool:
        return self.validate(instance).valid

    # -- internals -----------------------------------------------------------
    def _resolve_ref(self, ref: str) -> tuple[str, Mapping[str, Any]]:
        if ref.startswith("#"):
            target = _resolve_pointer(self._schema, ref)
            if not isinstance(target, Mapping):
                raise SchemaEngineError(f"$ref {ref!r} does not point at a schema object")
            return ref, target
        target = self._by_id.get(ref)
        if target is None:
            raise SchemaEngineError(
                f"unresolvable $ref {ref!r}; known ids: {sorted(self._by_id)}"
            )
        return ref, target

    def _validate(
        self,
        instance: Any,
        schema: Any,
        pointer: str,
        findings: list[SchemaFinding],
        *,
        depth: int,
        ref_stack: tuple[str, ...],
    ) -> None:
        if depth > _MAX_DEPTH:
            raise SchemaEngineError(f"schema recursion exceeds {_MAX_DEPTH} levels at {pointer!r}")
        if not isinstance(schema, Mapping):
            raise SchemaEngineError(f"schema at {pointer!r} is not an object")

        ref = schema.get("$ref")
        if isinstance(ref, str):
            ref_key, target = self._resolve_ref(ref)
            if ref_key in ref_stack:
                raise SchemaEngineError(f"cyclic $ref {ref!r}")
            self._validate(
                instance,
                target,
                pointer,
                findings,
                depth=depth + 1,
                ref_stack=ref_stack + (ref_key,),
            )

        # "type" first: if the kind is wrong the remaining keyword findings would
        # be noise, so stop here (jsonschema reports them, but validity agrees).
        expected_types = schema.get("type")
        if expected_types is not None:
            if isinstance(expected_types, str):
                allowed = (expected_types,)
            elif isinstance(expected_types, Sequence) and not isinstance(expected_types, (str, bytes)):
                allowed = tuple(expected_types)
                if not all(isinstance(item, str) for item in allowed):
                    raise SchemaEngineError(f"'type' list at {pointer!r} must contain strings")
            else:
                raise SchemaEngineError(f"'type' at {pointer!r} must be a string or a list of strings")
            if not any(_type_matches(instance, expected) for expected in allowed):
                findings.append(
                    SchemaFinding(
                        path=pointer,
                        keyword="type",
                        message=f"expected {' or '.join(allowed)}; got {_describe(instance)}",
                    )
                )
                return

        if "const" in schema and not _json_equal(instance, schema["const"]):
            findings.append(
                SchemaFinding(
                    path=pointer,
                    keyword="const",
                    message=f"expected the constant {schema['const']!r}; got {_describe(instance)}",
                )
            )

        enum = schema.get("enum")
        if isinstance(enum, Sequence) and not isinstance(enum, (str, bytes)):
            if not any(_json_equal(instance, option) for option in enum):
                rendered = ", ".join(repr(option) for option in enum[:12])
                if len(enum) > 12:
                    rendered += f", ... ({len(enum)} values)"
                findings.append(
                    SchemaFinding(
                        path=pointer,
                        keyword="enum",
                        message=f"value {_describe(instance)} is not one of: {rendered}",
                    )
                )

        if isinstance(instance, str):
            pattern = schema.get("pattern")
            if isinstance(pattern, str) and re.search(pattern, instance) is None:
                findings.append(
                    SchemaFinding(
                        path=pointer,
                        keyword="pattern",
                        message=f"string {instance!r} does not match pattern {pattern!r}",
                    )
                )
            min_length = schema.get("minLength")
            if isinstance(min_length, int) and len(instance) < min_length:
                findings.append(
                    SchemaFinding(
                        path=pointer,
                        keyword="minLength",
                        message=f"string has {len(instance)} characters; minimum is {min_length}",
                    )
                )
            max_length = schema.get("maxLength")
            if isinstance(max_length, int) and len(instance) > max_length:
                findings.append(
                    SchemaFinding(
                        path=pointer,
                        keyword="maxLength",
                        message=f"string has {len(instance)} characters; maximum is {max_length}",
                    )
                )

        if _is_number(instance):
            minimum = schema.get("minimum")
            if _is_number(minimum) and instance < minimum:
                findings.append(
                    SchemaFinding(
                        path=pointer,
                        keyword="minimum",
                        message=f"number {instance!r} is below the minimum {minimum!r}",
                    )
                )
            maximum = schema.get("maximum")
            if _is_number(maximum) and instance > maximum:
                findings.append(
                    SchemaFinding(
                        path=pointer,
                        keyword="maximum",
                        message=f"number {instance!r} is above the maximum {maximum!r}",
                    )
                )

        if isinstance(instance, list):
            min_items = schema.get("minItems")
            if isinstance(min_items, int) and len(instance) < min_items:
                findings.append(
                    SchemaFinding(
                        path=pointer,
                        keyword="minItems",
                        message=f"array has {len(instance)} items; minimum is {min_items}",
                    )
                )
            max_items = schema.get("maxItems")
            if isinstance(max_items, int) and len(instance) > max_items:
                findings.append(
                    SchemaFinding(
                        path=pointer,
                        keyword="maxItems",
                        message=f"array has {len(instance)} items; maximum is {max_items}",
                    )
                )
            items = schema.get("items")
            if isinstance(items, Mapping):
                for item_index, item in enumerate(instance):
                    self._validate(
                        item,
                        items,
                        _join_pointer(pointer, item_index),
                        findings,
                        depth=depth + 1,
                        ref_stack=ref_stack,
                    )
            elif isinstance(items, list):
                # Tuple/positional form: each position has its own schema.
                for item_index, item_schema in enumerate(items):
                    if item_index >= len(instance):
                        break
                    self._validate(
                        instance[item_index],
                        item_schema,
                        _join_pointer(pointer, item_index),
                        findings,
                        depth=depth + 1,
                        ref_stack=ref_stack,
                    )

        if isinstance(instance, dict):
            required = schema.get("required")
            if isinstance(required, Sequence) and not isinstance(required, (str, bytes)):
                for name in required:
                    if name not in instance:
                        findings.append(
                            SchemaFinding(
                                path=_join_pointer(pointer, name),
                                keyword="required",
                                message=f"required property {name!r} is missing",
                            )
                        )
            properties = schema.get("properties")
            named: Mapping[str, Any] = properties if isinstance(properties, Mapping) else {}
            for name, subschema in named.items():
                if name in instance:
                    self._validate(
                        instance[name],
                        subschema,
                        _join_pointer(pointer, name),
                        findings,
                        depth=depth + 1,
                        ref_stack=ref_stack,
                    )
            additional = schema.get("additionalProperties", True)
            if additional is False:
                for name in instance:
                    if name not in named:
                        findings.append(
                            SchemaFinding(
                                path=_join_pointer(pointer, name),
                                keyword="additionalProperties",
                                message=f"property {name!r} is not allowed by the schema",
                            )
                        )
            elif isinstance(additional, Mapping):
                for name, value in instance.items():
                    if name not in named:
                        self._validate(
                            value,
                            additional,
                            _join_pointer(pointer, name),
                            findings,
                            depth=depth + 1,
                            ref_stack=ref_stack,
                        )

        all_of = schema.get("allOf")
        if isinstance(all_of, Sequence) and not isinstance(all_of, (str, bytes)):
            for subschema in all_of:
                self._validate(
                    instance,
                    subschema,
                    pointer,
                    findings,
                    depth=depth + 1,
                    ref_stack=ref_stack,
                )

        if_schema = schema.get("if")
        if isinstance(if_schema, Mapping):
            probe: list[SchemaFinding] = []
            self._validate(
                instance,
                if_schema,
                pointer,
                probe,
                depth=depth + 1,
                ref_stack=ref_stack,
            )
            if not probe:
                then_schema = schema.get("then")
                if isinstance(then_schema, Mapping):
                    self._validate(
                        instance,
                        then_schema,
                        pointer,
                        findings,
                        depth=depth + 1,
                        ref_stack=ref_stack,
                    )
            else:
                else_schema = schema.get("else")
                if isinstance(else_schema, Mapping):
                    self._validate(
                        instance,
                        else_schema,
                        pointer,
                        findings,
                        depth=depth + 1,
                        ref_stack=ref_stack,
                    )


# ------------------------------------------------------- schemas from schema.py
def _default_document() -> Mapping[str, Any]:
    # Imported lazily so this module has no import-time dependency beyond the
    # standard library and so a caller can pass its own document.
    from .. import schema as schema_module

    return schema_module.schema_document()


def _event_validator() -> SchemaValidator:
    return SchemaValidator.from_document(_default_document(), kind="event")


def _result_validator() -> SchemaValidator:
    return SchemaValidator.from_document(_default_document(), kind="result")


_EVENT_VALIDATOR: SchemaValidator | None = None
_RESULT_VALIDATOR: SchemaValidator | None = None


def _get_event_validator() -> SchemaValidator:
    global _EVENT_VALIDATOR
    if _EVENT_VALIDATOR is None:
        _EVENT_VALIDATOR = _event_validator()
    return _EVENT_VALIDATOR


def _get_result_validator() -> SchemaValidator:
    global _RESULT_VALIDATOR
    if _RESULT_VALIDATOR is None:
        _RESULT_VALIDATOR = _result_validator()
    return _RESULT_VALIDATOR


def validate_event_payload(payload: Any) -> SchemaValidation:
    """Validate one ``EventExtraction.to_dict()`` payload against the event schema."""
    return _get_event_validator().validate(payload)


def validate_result_payload(payload: Any) -> SchemaValidation:
    """Validate one ``ExtractionResult.to_dict()`` payload against the result schema."""
    return _get_result_validator().validate(payload)
