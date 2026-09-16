# c#: finds classes, methods and usings.

from __future__ import annotations

import re
import textwrap
from pathlib import PurePath

import tree_sitter_c_sharp
from tree_sitter import Language, Node, Parser

from brig.parse import ExtractResult, Symbol

_LANGUAGE = Language(tree_sitter_c_sharp.language())

_SUFFIXES = frozenset({".cs"})

_MAX_SIG = 200
_MAX_DOC = 500


def _text(node: Node, data: bytes) -> str:
    return data[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _clean_comment(text: str) -> str:
    t = text.strip()
    if t.startswith("///"):
        return t[3:].strip()
    if t.startswith("//"):
        return t[2:].strip()
    if t.startswith("/*"):
        inner = t[2:]
        if inner.endswith("*/"):
            inner = inner[:-2]
        lines = [re.sub(r"^\s*\*\s?", "", ln) for ln in inner.splitlines()]
        return "\n".join(lines).strip()
    return t


def _leading_doc(anchor: Node, data: bytes) -> str:
    chain: list[Node] = []
    cursor_end = anchor.start_byte
    sib = anchor.prev_named_sibling
    while sib is not None and sib.type == "comment":
        if data[sib.end_byte : cursor_end].strip(b" \t\r\n"):
            break
        chain.append(sib)
        cursor_end = sib.start_byte
        sib = sib.prev_named_sibling
    chain.reverse()
    return "\n".join(_clean_comment(_text(c, data)) for c in chain)[:_MAX_DOC]


def _sig_up_to_body(node: Node, data: bytes) -> str:
    end = node.end_byte
    for child in node.children:
        if child.type in ("block", "declaration_list", ";"):
            end = child.start_byte
            break
    raw = data[node.start_byte : end].decode("utf-8", errors="replace")
    return textwrap.dedent(raw).strip()[:_MAX_SIG]


def _name(node: Node, data: bytes) -> str | None:
    named = node.child_by_field_name("name")
    if named is not None:
        return _text(named, data)
    for child in node.named_children:
        if child.type == "identifier":
            return _text(child, data)
    return None


def _using_spec(node: Node, data: bytes) -> str | None:
    for child in node.named_children:
        if child.type in ("identifier", "qualified_name"):
            return _text(child, data)
    return None


class CSharpSpec:
    # handles .cs files.

    def matches(self, path: str) -> bool:
        return PurePath(path).suffix.lower() in _SUFFIXES

    def extract(self, source: str | bytes) -> ExtractResult:
        data = source.encode("utf-8") if isinstance(source, str) else bytes(source)
        tree = Parser(_LANGUAGE).parse(data)
        symbols: list[Symbol] = []
        imports: list[str] = []
        _visit(tree.root_node, [], data, symbols, imports)
        return ExtractResult(symbols=symbols, imports=imports)


def _emit(symbols, scope, name, kind, sig, doc, node) -> None:
    symbols.append(
        Symbol(
            qualname=".".join(scope + [name]),
            kind=kind,
            sig=sig,
            doc=doc,
            start_byte=node.start_byte,
            end_byte=node.end_byte,
        )
    )


def _visit(node: Node, scope: list[str], data: bytes,
           symbols: list[Symbol], imports: list[str]) -> None:
    t = node.type
    if t in ("namespace_declaration", "namespace_definition"):
        name = _name(node, data)
        inner = scope + [name] if name else scope
        for child in node.children:
            _visit(child, inner, data, symbols, imports)
        return
    if t in ("class_declaration", "interface_declaration", "record_declaration",
             "struct_declaration", "enum_declaration"):
        name = _name(node, data)
        if name is None:
            for child in node.children:
                _visit(child, scope, data, symbols, imports)
            return
        _emit(symbols, scope, name, "class",
              _sig_up_to_body(node, data), _leading_doc(node, data), node)
        for child in node.children:
            _visit(child, scope + [name], data, symbols, imports)
        return
    if t in ("method_declaration", "constructor_declaration", "destructor_declaration"):
        name = _name(node, data)
        if name is None:
            # ctors keep their name right on the node.
            for child in node.named_children:
                if child.type == "identifier":
                    name = _text(child, data)
                    break
        if name is not None:
            _emit(symbols, scope, name, "method",
                  _sig_up_to_body(node, data), _leading_doc(node, data), node)
            return
        for child in node.children:
            _visit(child, scope, data, symbols, imports)
        return
    if t == "using_directive":
        # only real imports, not 'using var x = ...' lines.
        has_eq = any(c.type == "=" for c in node.children)
        if not has_eq:
            spec = _using_spec(node, data)
            if spec and "=" not in spec:
                imports.append(spec)
        return
    for child in node.children:
        _visit(child, scope, data, symbols, imports)
