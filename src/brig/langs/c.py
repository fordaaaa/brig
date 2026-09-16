"""C LanguageSpec: tree-sitter function/struct/enum + include extraction."""

from __future__ import annotations

import re
import textwrap
from pathlib import PurePath

import tree_sitter_c
from tree_sitter import Language, Node, Parser

from brig.parse import ExtractResult, Symbol

_LANGUAGE = Language(tree_sitter_c.language())

_SUFFIXES = frozenset({".c", ".h"})

_MAX_SIG = 200
_MAX_DOC = 500


def _text(node: Node, data: bytes) -> str:
    return data[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _clean_comment(text: str) -> str:
    t = text.strip()
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
        if child.type in ("compound_statement", ";"):
            end = child.start_byte
            break
    raw = data[node.start_byte : end].decode("utf-8", errors="replace")
    return textwrap.dedent(raw).strip()[:_MAX_SIG]


def _find_first(node: Node, types: frozenset[str]) -> Node | None:
    stack = [node]
    while stack:
        cur = stack.pop(0)
        if cur.type in types:
            return cur
        stack = list(cur.children) + stack
    return None


def _func_name(node: Node, data: bytes) -> str | None:
    decl = node.child_by_field_name("declarator")
    if decl is None:
        for child in node.children:
            if child.type in ("function_declarator", "parenthesized_declarator",
                              "pointer_declarator", "array_declarator"):
                decl = child
                break
    if decl is None:
        return None
    ident = _find_first(decl, frozenset({"identifier", "field_identifier"}))
    if ident is None:
        return None
    return _text(ident, data)


def _type_name(node: Node, data: bytes) -> str | None:
    named = node.child_by_field_name("name")
    if named is not None:
        return _text(named, data)
    for child in node.named_children:
        if child.type == "type_identifier":
            return _text(child, data)
    return None


def _import_spec(node: Node, data: bytes) -> str | None:
    for child in node.children:
        if child.type == "system_lib_string":
            t = _text(child, data).strip()
            if t.startswith("<") and t.endswith(">"):
                return t[1:-1].strip()
            return t
        if child.type == "string_literal":
            t = _text(child, data).strip()
            if len(t) >= 2 and t[0] == '"' and t[-1] == '"':
                return t[1:-1]
            return t
    return None


class CSpec:
    """Extractor for ``.c`` / ``.h`` files."""

    def matches(self, path: str) -> bool:
        return PurePath(path).suffix.lower() in _SUFFIXES

    def extract(self, source: str | bytes) -> ExtractResult:
        data = source.encode("utf-8") if isinstance(source, str) else bytes(source)
        tree = Parser(_LANGUAGE).parse(data)
        symbols: list[Symbol] = []
        imports: list[str] = []
        _visit(tree.root_node, data, symbols, imports)
        return ExtractResult(symbols=symbols, imports=imports)


def _visit(node: Node, data: bytes, symbols: list[Symbol], imports: list[str]) -> None:
    t = node.type
    if t == "function_definition":
        name = _func_name(node, data)
        if name is not None:
            symbols.append(
                Symbol(
                    qualname=name,
                    kind="function",
                    sig=_sig_up_to_body(node, data),
                    doc=_leading_doc(node, data),
                    start_byte=node.start_byte,
                    end_byte=node.end_byte,
                )
            )
        return
    if t in ("struct_specifier", "enum_specifier", "union_specifier"):
        name = _type_name(node, data)
        if name is not None:
            # Anonymous structs/enums (no name) are skipped as symbols.
            symbols.append(
                Symbol(
                    qualname=name,
                    kind="class",
                    sig=_sig_up_to_body(node, data),
                    doc=_leading_doc(node, data),
                    start_byte=node.start_byte,
                    end_byte=node.end_byte,
                )
            )
        return
    if t == "preproc_include":
        spec = _import_spec(node, data)
        if spec:
            imports.append(spec)
        return
    for child in node.children:
        _visit(child, data, symbols, imports)
