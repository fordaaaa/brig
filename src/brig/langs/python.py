# python: finds defs, classes and imports.

from __future__ import annotations

import textwrap
from pathlib import PurePath

import tree_sitter_python
from tree_sitter import Language, Node, Parser

from brig.parse import ExtractResult, Symbol

_LANGUAGE = Language(tree_sitter_python.language())

_SUFFIXES = frozenset({".py"})

_MAX_SIG = 200
_MAX_DOC = 500


def _bytes(node: Node, data: bytes) -> bytes:
    return data[node.start_byte : node.end_byte]


def _text(node: Node, data: bytes) -> str:
    return _bytes(node, data).decode("utf-8", errors="replace")


def _signature(node: Node, data: bytes) -> str:
    # text from def/class up to the colon.
    end = node.end_byte
    for child in node.children:
        if child.type == ":":
            end = child.end_byte
            break
    raw = data[node.start_byte : end].decode("utf-8", errors="replace")
    return textwrap.dedent(raw).strip()[:_MAX_SIG]


def _docstring(node: Node, data: bytes) -> str:
    # first string in the body, or nothing.
    body = node.child_by_field_name("body")
    if body is None or not body.named_children:
        return ""
    first = body.named_children[0]
    if first.type != "expression_statement" or not first.named_children:
        return ""
    lit = first.named_children[0]
    if lit.type != "string":
        return ""
    parts: list[str] = []

    def _collect(n: Node) -> None:
        if n.type == "string_content":
            parts.append(_text(n, data))
        for c in n.children:
            _collect(c)

    _collect(lit)
    return "".join(parts)[:_MAX_DOC]


def _module_of_import_from(node: Node, data: bytes) -> str | None:
    for child in node.children:
        if child.type in ("dotted_name", "relative_import"):
            return _text(child, data)
    return None


class PythonSpec:
    # handles .py files.

    def matches(self, path: str) -> bool:
        return PurePath(path).suffix.lower() in _SUFFIXES

    def extract(self, source: str | bytes) -> ExtractResult:
        data = source.encode("utf-8") if isinstance(source, str) else bytes(source)
        tree = Parser(_LANGUAGE).parse(data)
        symbols: list[Symbol] = []
        imports: list[str] = []
        _visit(tree.root_node, [], data, symbols, imports)
        return ExtractResult(symbols=symbols, imports=imports)


def _visit(
    node: Node,
    scope: list[tuple[str, str]],
    data: bytes,
    symbols: list[Symbol],
    imports: list[str],
) -> None:
    t = node.type
    if t == "function_definition":
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _text(name_node, data)
        kind = "method" if scope and scope[-1][1] == "class" else "function"
        symbols.append(
            Symbol(
                qualname=".".join([n for n, _ in scope] + [name]),
                kind=kind,
                sig=_signature(node, data),
                doc=_docstring(node, data),
                start_byte=node.start_byte,
                end_byte=node.end_byte,
            )
        )
        for child in node.children:
            _visit(child, scope + [(name, kind)], data, symbols, imports)
        return
    if t == "class_definition":
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _text(name_node, data)
        symbols.append(
            Symbol(
                qualname=".".join([n for n, _ in scope] + [name]),
                kind="class",
                sig=_signature(node, data),
                doc=_docstring(node, data),
                start_byte=node.start_byte,
                end_byte=node.end_byte,
            )
        )
        for child in node.children:
            _visit(child, scope + [(name, "class")], data, symbols, imports)
        return
    if t == "import_statement":
        for child in node.children:
            if child.type == "dotted_name":
                imports.append(_text(child, data))
            elif child.type == "aliased_import":
                for sub in child.children:
                    if sub.type == "dotted_name":
                        imports.append(_text(sub, data))
                        break
        return
    if t == "import_from_statement":
        mod = _module_of_import_from(node, data)
        if mod:
            imports.append(mod)
        return
    for child in node.children:
        _visit(child, scope, data, symbols, imports)
