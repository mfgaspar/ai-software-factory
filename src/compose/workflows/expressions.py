"""The ``{{ }}`` expression language used in workflow definitions.

Deliberately small: lookups, literals, comparisons, ``in``, ``and``/``or``/``not``, and
filters. No arithmetic, no function calls, no attribute access on Python objects.

* A template that is exactly one ``{{ expr }}`` evaluates to the typed value.
* Any other template renders to a string.
* Looking up a missing key gives *undefined*: it is falsy, ``default`` replaces it, and
  rendering it is an error. An unknown top-level name (e.g. ``input`` for ``inputs``)
  is always an error.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any


class ExpressionError(Exception):
    """An expression cannot be parsed or evaluated."""


# --------------------------------------------------------------------------- values


class Undefined:
    """The result of looking up something that isn't there."""

    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return f"Undefined({self.name!r})"


def _require(value: Any, what: str) -> Any:
    if isinstance(value, Undefined):
        raise ExpressionError(f"{value.name} is undefined ({what})")
    return value


def to_text(value: Any) -> str:
    """How a value appears inside a larger string."""
    _require(value, "rendered into text")
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    return json.dumps(value)


# -------------------------------------------------------------------------- filters

Filter = Callable[..., Any]


def _f_default(value: Any, fallback: Any = "") -> Any:
    return fallback if isinstance(value, Undefined) or value is None else value


def _f_join(value: Any, sep: str = ",") -> str:
    return str(sep).join(to_text(v) for v in _seq(value, "join"))


def _f_contains(value: Any, item: Any) -> bool:
    value = _require(value, "contains")
    if isinstance(value, str):
        return to_text(item) in value
    return item in value


def _f_map(value: Any, key: str) -> list[Any]:
    out = []
    for element in _seq(value, "map"):
        if not isinstance(element, Mapping) or key not in element:
            raise ExpressionError(f"map: element has no key {key!r}")
        out.append(element[key])
    return out


def _f_from_json(value: Any) -> Any:
    try:
        return json.loads(_str(value, "from_json"))
    except json.JSONDecodeError as exc:
        raise ExpressionError(f"from_json: invalid JSON ({exc})") from exc


def _f_to_json(value: Any) -> str:
    return json.dumps(_require(value, "to_json"))


def _f_split(value: Any, sep: str | None = None) -> list[str]:
    return _str(value, "split").split(sep)


def _f_length(value: Any) -> int:
    value = _require(value, "length")
    try:
        return len(value)
    except TypeError as exc:
        raise ExpressionError(f"length: {type(value).__name__} has no length") from exc


def _seq(value: Any, what: str) -> Sequence[Any]:
    value = _require(value, what)
    if not isinstance(value, list | tuple):
        raise ExpressionError(f"{what}: expected a list, got {type(value).__name__}")
    return value


def _str(value: Any, what: str) -> str:
    value = _require(value, what)
    if not isinstance(value, str):
        raise ExpressionError(f"{what}: expected a string, got {type(value).__name__}")
    return value


FILTERS: dict[str, Filter] = {
    "default": _f_default,
    "join": _f_join,
    "contains": _f_contains,
    "map": _f_map,
    "from_json": _f_from_json,
    "to_json": _f_to_json,
    "upper": lambda v: _str(v, "upper").upper(),
    "lower": lambda v: _str(v, "lower").lower(),
    "split": _f_split,
    "length": _f_length,
}


def register_filter(name: str, func: Filter) -> None:
    FILTERS[name] = func


# --------------------------------------------------------------------------- tokens

_TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<number>-?\d+(?:\.\d+)?)
  | (?P<string>'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")
  | (?P<op>==|!=|>=|<=|>|<|\||\(|\)|\[|\]|,|\.)
  | (?P<name>[A-Za-z_][A-Za-z0-9_-]*)
    """,
    re.VERBOSE,
)
_KEYWORDS = {"and", "or", "not", "in", "true", "false", "null", "none", "True", "False", "None"}


@dataclass(frozen=True)
class _Tok:
    kind: str
    text: str
    pos: int


def _tokenize(source: str) -> list[_Tok]:
    tokens: list[_Tok] = []
    pos = 0
    while pos < len(source):
        match = _TOKEN_RE.match(source, pos)
        if match is None:
            raise ExpressionError(f"unexpected character {source[pos]!r} at {pos} in {source!r}")
        kind = match.lastgroup or ""
        text = match.group()
        if kind != "ws":
            if kind == "name" and text in _KEYWORDS:
                kind = "kw"
            tokens.append(_Tok(kind, text, pos))
        pos = match.end()
    tokens.append(_Tok("end", "", len(source)))
    return tokens


# ----------------------------------------------------------------------------- AST


class _Node:
    def eval(self, ctx: Mapping[str, Any]) -> Any:  # pragma: no cover - abstract
        raise NotImplementedError

    def paths(self) -> list[tuple[str, ...]]:
        return []


@dataclass
class _Literal(_Node):
    value: Any

    def eval(self, ctx: Mapping[str, Any]) -> Any:
        return self.value


@dataclass
class _ListLit(_Node):
    items: list[_Node]

    def eval(self, ctx: Mapping[str, Any]) -> Any:
        return [_require(i.eval(ctx), "list item") for i in self.items]

    def paths(self) -> list[tuple[str, ...]]:
        return [p for i in self.items for p in i.paths()]


@dataclass
class _Path(_Node):
    root: str
    segments: list[str | int | _Node] = field(default_factory=list)

    def eval(self, ctx: Mapping[str, Any]) -> Any:
        if self.root not in ctx:
            known = ", ".join(sorted(ctx)) or "none"
            raise ExpressionError(f"unknown name {self.root!r} (known: {known})")
        value: Any = ctx[self.root]
        label = self.root
        for seg in self.segments:
            key = seg.eval(ctx) if isinstance(seg, _Node) else seg
            label += f"[{key!r}]" if isinstance(seg, _Node) else f".{key}"
            value = _lookup(value, key, label)
        return value

    def paths(self) -> list[tuple[str, ...]]:
        static: list[str] = [self.root]
        for seg in self.segments:
            if isinstance(seg, _Node):
                break
            static.append(str(seg))
        nested = [p for s in self.segments if isinstance(s, _Node) for p in s.paths()]
        return [tuple(static), *nested]


def _lookup(value: Any, key: Any, label: str) -> Any:
    if isinstance(value, Undefined):
        return value
    if isinstance(value, Mapping):
        return value[key] if key in value else Undefined(label)
    if isinstance(value, list | tuple) and isinstance(key, int) and not isinstance(key, bool):
        return value[key] if -len(value) <= key < len(value) else Undefined(label)
    return Undefined(label)


@dataclass
class _FilterCall(_Node):
    target: _Node
    name: str
    args: list[_Node]

    def eval(self, ctx: Mapping[str, Any]) -> Any:
        func = FILTERS.get(self.name)
        if func is None:
            raise ExpressionError(f"unknown filter {self.name!r}")
        args = [_require(a.eval(ctx), f"argument of {self.name}") for a in self.args]
        try:
            return func(self.target.eval(ctx), *args)
        except TypeError as exc:
            raise ExpressionError(f"{self.name}: {exc}") from exc

    def paths(self) -> list[tuple[str, ...]]:
        return self.target.paths() + [p for a in self.args for p in a.paths()]


@dataclass
class _Not(_Node):
    operand: _Node

    def eval(self, ctx: Mapping[str, Any]) -> Any:
        return not self.operand.eval(ctx)

    def paths(self) -> list[tuple[str, ...]]:
        return self.operand.paths()


@dataclass
class _BoolOp(_Node):
    op: str
    left: _Node
    right: _Node

    def eval(self, ctx: Mapping[str, Any]) -> Any:
        left = self.left.eval(ctx)
        if self.op == "and":
            return self.right.eval(ctx) if left else left
        return left if left else self.right.eval(ctx)

    def paths(self) -> list[tuple[str, ...]]:
        return self.left.paths() + self.right.paths()


@dataclass
class _Compare(_Node):
    op: str
    left: _Node
    right: _Node

    def eval(self, ctx: Mapping[str, Any]) -> Any:
        left = _undef_to_none(self.left.eval(ctx))
        right = _undef_to_none(self.right.eval(ctx))
        if self.op == "==":
            return left == right
        if self.op == "!=":
            return left != right
        if self.op in ("in", "not in"):
            if right is None:
                found = False
            elif isinstance(right, str):
                found = to_text(left) in right
            elif isinstance(right, Mapping | list | tuple):
                found = left in right
            else:
                raise ExpressionError("'in' needs a list, mapping or string on the right")
            return found if self.op == "in" else not found
        try:
            if self.op == ">":
                return left > right
            if self.op == "<":
                return left < right
            if self.op == ">=":
                return left >= right
            return left <= right
        except TypeError as exc:
            raise ExpressionError(
                f"cannot compare {type(left).__name__} {self.op} {type(right).__name__}"
            ) from exc

    def paths(self) -> list[tuple[str, ...]]:
        return self.left.paths() + self.right.paths()


def _undef_to_none(value: Any) -> Any:
    return None if isinstance(value, Undefined) else value


# -------------------------------------------------------------------------- parser


class _Parser:
    def __init__(self, source: str) -> None:
        self.source = source
        self.tokens = _tokenize(source)
        self.i = 0

    def peek(self, offset: int = 0) -> _Tok:
        return self.tokens[min(self.i + offset, len(self.tokens) - 1)]

    def take(self) -> _Tok:
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def accept(self, kind: str, text: str | None = None) -> _Tok | None:
        tok = self.peek()
        if tok.kind == kind and (text is None or tok.text == text):
            return self.take()
        return None

    def expect(self, kind: str, text: str | None = None) -> _Tok:
        tok = self.accept(kind, text)
        if tok is None:
            got = self.peek()
            want = text or kind
            raise ExpressionError(
                f"expected {want!r} at {got.pos} in {self.source!r}, got {got.text or 'end'!r}"
            )
        return tok

    def parse(self) -> _Node:
        if self.peek().kind == "end":
            raise ExpressionError("empty expression")
        node = self.or_()
        if self.peek().kind != "end":
            tok = self.peek()
            raise ExpressionError(f"unexpected {tok.text!r} at {tok.pos} in {self.source!r}")
        return node

    def or_(self) -> _Node:
        node = self.and_()
        while self.accept("kw", "or"):
            node = _BoolOp("or", node, self.and_())
        return node

    def and_(self) -> _Node:
        node = self.not_()
        while self.accept("kw", "and"):
            node = _BoolOp("and", node, self.not_())
        return node

    def not_(self) -> _Node:
        if self.accept("kw", "not"):
            return _Not(self.not_())
        return self.compare()

    def compare(self) -> _Node:
        left = self.filtered()
        tok = self.peek()
        if tok.kind == "op" and tok.text in ("==", "!=", ">", "<", ">=", "<="):
            self.take()
            return _Compare(tok.text, left, self.filtered())
        if self.accept("kw", "in"):
            return _Compare("in", left, self.filtered())
        if tok.kind == "kw" and tok.text == "not" and self.peek(1).text == "in":
            self.take()
            self.take()
            return _Compare("not in", left, self.filtered())
        return left

    def filtered(self) -> _Node:
        node = self.primary()
        while self.accept("op", "|"):
            name = self.expect("name").text
            args: list[_Node] = []
            if self.accept("op", "(") and not self.accept("op", ")"):
                args.append(self.or_())
                while self.accept("op", ","):
                    args.append(self.or_())
                self.expect("op", ")")
            node = _FilterCall(node, name, args)
        return node

    def primary(self) -> _Node:
        tok = self.take()
        if tok.kind == "number":
            return _Literal(float(tok.text) if "." in tok.text else int(tok.text))
        if tok.kind == "string":
            return _Literal(_unquote(tok.text))
        if tok.kind == "kw":
            if tok.text in ("true", "True"):
                return _Literal(True)
            if tok.text in ("false", "False"):
                return _Literal(False)
            if tok.text in ("null", "none", "None"):
                return _Literal(None)
        if tok.kind == "op" and tok.text == "(":
            node = self.or_()
            self.expect("op", ")")
            return node
        if tok.kind == "op" and tok.text == "[":
            items: list[_Node] = []
            if not self.accept("op", "]"):
                items.append(self.or_())
                while self.accept("op", ","):
                    items.append(self.or_())
                self.expect("op", "]")
            return _ListLit(items)
        if tok.kind == "name":
            return self.path(tok.text)
        raise ExpressionError(f"unexpected {tok.text or 'end'!r} at {tok.pos} in {self.source!r}")

    def path(self, root: str) -> _Node:
        node = _Path(root)
        while True:
            if self.accept("op", "."):
                seg = self.take()
                if seg.kind in ("name", "kw"):
                    node.segments.append(seg.text)
                elif seg.kind == "number" and seg.text.isdigit():
                    node.segments.append(int(seg.text))
                else:
                    raise ExpressionError(f"expected a key after '.' at {seg.pos}")
            elif self.accept("op", "["):
                node.segments.append(self.or_())
                self.expect("op", "]")
            else:
                return node


def _unquote(text: str) -> str:
    body = text[1:-1]
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), body)


# ------------------------------------------------------------------------ templates

_EXPR_RE = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)


@dataclass(frozen=True)
class Template:
    """A parsed template: literal text and expressions."""

    source: str
    parts: tuple[str | _Node, ...]

    @property
    def is_lone(self) -> bool:
        return len(self.parts) == 1 and isinstance(self.parts[0], _Node)

    @property
    def has_expressions(self) -> bool:
        return any(isinstance(p, _Node) for p in self.parts)

    def render(self, ctx: Mapping[str, Any]) -> Any:
        if self.is_lone:
            node = self.parts[0]
            assert isinstance(node, _Node)
            return _require(node.eval(ctx), f"in {self.source!r}")
        return "".join(p if isinstance(p, str) else to_text(p.eval(ctx)) for p in self.parts)

    def references(self) -> list[tuple[str, ...]]:
        """Static lookup paths used, e.g. ``("inputs", "spec")``."""
        return [path for p in self.parts if isinstance(p, _Node) for path in p.paths()]


@lru_cache(maxsize=2048)
def compile_template(source: str) -> Template:
    parts: list[str | _Node] = []
    stripped = source.strip()
    lone = _EXPR_RE.fullmatch(stripped)
    if lone and "{{" not in lone.group(1):
        return Template(source, (_Parser(lone.group(1).strip()).parse(),))
    pos = 0
    for match in _EXPR_RE.finditer(source):
        if match.start() > pos:
            parts.append(source[pos : match.start()])
        parts.append(_Parser(match.group(1).strip()).parse())
        pos = match.end()
    if pos < len(source):
        parts.append(source[pos:])
    text_parts = [p for p in parts if isinstance(p, str)]
    if any("{{" in p or "}}" in p for p in text_parts):
        raise ExpressionError(f"unbalanced '{{{{' / '}}}}' in {source!r}")
    return Template(source, tuple(parts))


@lru_cache(maxsize=2048)
def compile_expression(source: str) -> _Node:
    return _Parser(source.strip()).parse()


def render(template: str, ctx: Mapping[str, Any]) -> Any:
    """Render a template; a lone ``{{ expr }}`` returns the typed value."""
    return compile_template(template).render(ctx)


def evaluate(expression: str, ctx: Mapping[str, Any]) -> Any:
    """Evaluate a bare expression (no braces)."""
    return _require(compile_expression(expression).eval(ctx), f"in {expression!r}")


def evaluate_condition(text: str | bool, ctx: Mapping[str, Any]) -> bool:
    """A condition written either as ``{{ expr }}`` or as a bare expression."""
    if isinstance(text, bool):
        return text
    if "{{" in text:
        template = compile_template(text)
        if template.is_lone:
            node = template.parts[0]
            assert isinstance(node, _Node)
            return bool(node.eval(ctx))
        return bool(template.render(ctx))
    return bool(compile_expression(text).eval(ctx))


def references(text: str, *, bare: bool = False) -> list[tuple[str, ...]]:
    """Static lookup paths in a template (or a bare expression)."""
    if bare and "{{" not in text:
        return compile_expression(text).paths()
    return compile_template(text).references()
