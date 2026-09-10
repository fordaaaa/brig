"""JavaScript LanguageSpec: tree-sitter def/class + import extraction.

Also hosts the shared JS-family walk engine reused by the TypeScript spec
(the tree-sitter javascript/typescript grammars share node names for the
constructs v1 extracts).
"""

from __future__ import annotations

import re
import textwrap
from pathlib import PurePath

import tree_sitter_javascript
from tree_sitter import Language, Node, Parser

from brig.parse import ExtractResult, Symbol

_LANGUAGE = Language(tree_sitter_javascript.language())

_SUFFIXES = frozenset({".js", ".jsx", ".mjs", ".cjs"})

_MAX_SIG = 200
_MAX_DOC = 500

_FUNCTION_TYPES = frozenset({"function_declaration", "generator_function_declaration"})
_CLASS_TYPES = frozenset({"class_declaration", "abstract_class_declaration", "class"})
_FUNCTION_VALUE_TYPES = frozenset(
    {"arrow_function", "function_expression", "function", "generator_function"}
)
_BODY_TYPES = frozenset({"statement_block", "class_body"})
_NAME_TYPES = frozenset({"identifier", "property_identifier", "private_property_identifier"})


def _text(node: Node, data: bytes) -> str:
    return data[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _decl_name(node: Node, data: bytes) -> str | None:
    named = node.child_by_field_name("name")
    if named is not None:
        return _text(named, data)
    for child in node.named_children:
        if child.type in ("identifier", "type_identifier"):
            return _text(child, data)
    return None


def _method_name(node: Node, data: bytes) -> str | None:
    for child in node.named_children:
        if child.type in _NAME_TYPES:
            return _text(child, data)
    return None


def _sig_up_to_body(node: Node, data: bytes) -> str:
    """Source from the keyword/name up to the body brace (excluded)."""
    end = node.end_byte
    for child in node.children:
        if child.type in _BODY_TYPES:
            end = child.start_byte
            break
    raw = data[node.start_byte : end].decode("utf-8", errors="replace")
    return textwrap.dedent(raw).rstrip()[:_MAX_SIG]


def _declarator_sig(node: Node, data: bytes) -> str:
    """Signature for ``name = <fn>`` declarators (cut before a block body)."""
    end = node.end_byte
    stack = list(node.children)
    first_body: Node | None = None
    while stack:
        cur = stack.pop(0)
        if cur.type in _BODY_TYPES:
            first_body = cur
            break
        stack = list(cur.children) + stack
    if first_body is not None:
        end = first_body.start_byte
    raw = data[node.start_byte : end].decode("utf-8", errors="replace")
    return textwrap.dedent(raw).rstrip()[:_MAX_SIG]


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
    """Contiguous comment block immediately preceding *anchor* (cleaned)."""
    chain: list[Node] = []
    cursor_end = anchor.start_byte
    sib = anchor.prev_named_sibling
    while sib is not None and sib.type == "comment":
        if data[sib.end_byte : cursor_end].strip():
            break
        chain.append(sib)
        cursor_end = sib.start_byte
        sib = sib.prev_named_sibling
    chain.reverse()
    return "\n".join(_clean_comment(_text(c, data)) for c in chain)[:_MAX_DOC]


def _string_value(node: Node, data: bytes) -> str:
    frags = [_text(c, data) for c in node.named_children if c.type == "string_fragment"]
    if frags:
        return "".join(frags)
    raw = _text(node, data).strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"', "`"):
        return raw[1:-1]
    return raw


def _single_string_arg(node: Node, data: bytes) -> str | None:
    args = node.child_by_field_name("arguments")
    if args is None:
        return None
    named = args.named_children
    if len(named) == 1 and named[0].type == "string":
        return _string_value(named[0], data)
    return None


class JavaScriptSpec:
    """Extractor for ``.js`` / ``.jsx`` / ``.mjs`` / ``.cjs`` files."""

    def matches(self, path: str) -> bool:
        return PurePath(path).suffix.lower() in _SUFFIXES

    def extract(self, source: str | bytes) -> ExtractResult:
        data = source.encode("utf-8") if isinstance(source, str) else bytes(source)
        return extract_source(data, _LANGUAGE)


def extract_source(data: bytes, language: Language) -> ExtractResult:
    """Run the shared JS-family extraction with *language*."""
    tree = Parser(language).parse(data)
    symbols: list[Symbol] = []
    imports: list[str] = []
    _visit(tree.root_node, [], data, symbols, imports, outer=None)
    return ExtractResult(symbols=symbols, imports=imports)


def _emit(
    symbols: list[Symbol],
    qualname: str,
    kind: str,
    sig: str,
    doc: str,
    node: Node,
) -> None:
    symbols.append(
        Symbol(
            qualname=qualname,
            kind=kind,
            sig=sig,
            doc=doc,
            start_byte=node.start_byte,
            end_byte=node.end_byte,
        )
    )


def _visit(
    node: Node,
    scope: list[str],
    data: bytes,
    symbols: list[Symbol],
    imports: list[str],
    outer: Node | None,
) -> None:
    t = node.type
    if t in _FUNCTION_TYPES:
        name = _decl_name(node, data)
        if name is None:  # anonymous default export: walk body, no symbol
            for child in node.children:
                _visit(child, scope, data, symbols, imports, None)
            return
        anchor = outer if outer is not None else node
        _emit(
            symbols,
            ".".join(scope + [name]),
            "function",
            _sig_up_to_body(node, data),
            _leading_doc(anchor, data),
            node,
        )
        for child in node.children:
            _visit(child, scope + [name], data, symbols, imports, None)
        return
    if t in _CLASS_TYPES:
        name = _decl_name(node, data)
        if name is None:  # anonymous class expression: walk body, no symbol
            for child in node.children:
                _visit(child, scope, data, symbols, imports, None)
            return
        anchor = outer if outer is not None else node
        _emit(
            symbols,
            ".".join(scope + [name]),
            "class",
            _sig_up_to_body(node, data),
            _leading_doc(anchor, data),
            node,
        )
        for child in node.children:
            _visit(child, scope + [name], data, symbols, imports, None)
        return
    if t == "method_definition":
        parent = node.parent
        if parent is not None and parent.type == "class_body":
            name = _method_name(node, data)
            if name is not None:
                _emit(
                    symbols,
                    ".".join(scope + [name]),
                    "method",
                    _sig_up_to_body(node, data),
                    _leading_doc(node, data),
                    node,
                )
                for child in node.children:
                    _visit(child, scope + [name], data, symbols, imports, None)
                return
        # Object-literal methods etc: no symbol, but walk the body.
        for child in node.children:
            _visit(child, scope, data, symbols, imports, None)
        return
    if t == "export_statement":
        eff_outer = outer if outer is not None else node
        for child in node.children:
            if child.type == "string":
                imports.append(_string_value(child, data))  # export ... from '...'
            elif child.is_named and child.type not in ("export_clause", "export_specifier"):
                _visit(child, scope, data, symbols, imports, eff_outer)
        return
    if t == "lexical_declaration":
        for child in node.children:
            if child.type == "variable_declarator":
                _visit_declarator(child, scope, data, symbols, imports, outer)
        return
    if t == "variable_declarator":
        _visit_declarator(node, scope, data, symbols, imports, outer)
        return
    if t == "import_statement":
        for child in node.children:
            if child.type == "string":
                imports.append(_string_value(child, data))
        return
    if t == "call_expression":
        func = node.child_by_field_name("function")
        if func is not None:
            spec = _single_string_arg(node, data)
            if spec is not None:
                if func.type == "import" or (
                    func.type == "identifier" and _text(func, data) == "require"
                ):
                    imports.append(spec)
        for child in node.children:
            _visit(child, scope, data, symbols, imports, None)
        return
    for child in node.children:
        _visit(child, scope, data, symbols, imports, None)


def _visit_declarator(
    node: Node,
    scope: list[str],
    data: bytes,
    symbols: list[Symbol],
    imports: list[str],
    outer: Node | None,
) -> None:
    name_node = node.child_by_field_name("name")
    value = node.child_by_field_name("value")
    if name_node is None or value is None or name_node.type != "identifier":
        for child in node.children:
            _visit(child, scope, data, symbols, imports, None)
        return
    name = _text(name_node, data)
    if value.type in _FUNCTION_VALUE_TYPES:
        anchor = outer if outer is not None else node
        _emit(
            symbols,
            ".".join(scope + [name]),
            "function",
            _declarator_sig(node, data),
            _leading_doc(anchor, data),
            node,
        )
        _visit(value, scope + [name], data, symbols, imports, None)
        return
    if value.type in _CLASS_TYPES:
        anchor = outer if outer is not None else node
        _emit(
            symbols,
            ".".join(scope + [name]),
            "class",
            _sig_up_to_body(value, data),
            _leading_doc(anchor, data),
            value,
        )
        _visit(value, scope + [name], data, symbols, imports, None)
        return
    for child in node.children:
        _visit(child, scope, data, symbols, imports, None)
