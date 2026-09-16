# c++: finds classes, methods, functions and #includes. (.h belongs to c.)

from __future__ import annotations

import re
import textwrap
from pathlib import PurePath

import tree_sitter_cpp
from tree_sitter import Language, Node, Parser

from brig.parse import ExtractResult, Symbol

_LANGUAGE = Language(tree_sitter_cpp.language())

_SUFFIXES = frozenset({".cpp", ".hpp", ".cc", ".cxx", ".hh", ".h++"})

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
        if child.type in ("compound_statement", "field_declaration_list",
                          "declaration_list", ";"):
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


def _func_name_in(node: Node, data: bytes) -> str | None:
    decl = node.child_by_field_name("declarator")
    if decl is None:
        for child in node.children:
            if child.type in ("function_declarator", "parenthesized_declarator",
                              "pointer_declarator", "reference_declarator",
                              "array_declarator"):
                decl = child
                break
    if decl is None:
        # the declarator sits right on these nodes.
        if node.type in ("declaration", "field_declaration"):
            decl = node
        else:
            return None
    ident = _find_first(
        decl, frozenset({"identifier", "field_identifier", "destructor_name"})
    )
    if ident is None:
        return None
    t = _text(ident, data)
    # the ~ in front is already included.
    return t


def _type_name(node: Node, data: bytes) -> str | None:
    named = node.child_by_field_name("name")
    if named is not None:
        return _text(named, data)
    for child in node.named_children:
        if child.type in ("type_identifier", "namespace_identifier"):
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


class CppSpec:
    # handles c++ files (not .h, that's c's).

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
    if t == "namespace_definition":
        name = _type_name(node, data)
        inner = scope + [name] if name else scope
        for child in node.children:
            _visit(child, inner, data, symbols, imports)
        return
    if t in ("class_specifier", "struct_specifier", "union_specifier",
             "enum_specifier"):
        name = _type_name(node, data)
        if name is None:
            for child in node.children:
                _visit(child, scope, data, symbols, imports)
            return
        _emit(symbols, scope, name, "class",
              _sig_up_to_body(node, data), _leading_doc(node, data), node)
        for child in node.children:
            _visit(child, scope + [name], data, symbols, imports)
        return
    if t == "template_declaration":
        doc = _leading_doc(node, data)
        for child in node.children:
            if child.type in ("function_definition", "class_specifier",
                              "struct_specifier", "declaration"):
                _visit_template_child(child, scope, data, symbols, imports, node, doc)
            elif child.is_named and child.type not in (
                    "template", "template_parameter_list"):
                _visit(child, scope, data, symbols, imports)
        return
    if t == "function_definition":
        name = _func_name_in(node, data)
        if name is None:
            for child in node.children:
                _visit(child, scope, data, symbols, imports)
            return
        # nested function under a class = method; under a namespace = function.
        kind = "method" if scope and _in_class(node) else "function"
        _emit(symbols, scope, name, kind,
              _sig_up_to_body(node, data), _leading_doc(node, data) or "", node)
        return
    if t in ("declaration", "field_declaration"):
        # method declarations inside a class. skip plain fields.
        has_fn = _find_first(node, frozenset({"function_declarator"})) is not None
        if has_fn and scope:
            name = _func_name_in(node, data)
            if name is not None:
                _emit(symbols, scope, name, "method",
                      _sig_up_to_body(node, data), _leading_doc(node, data), node)
                return
        for child in node.children:
            _visit(child, scope, data, symbols, imports)
        return
    if t == "preproc_include":
        spec = _import_spec(node, data)
        if spec:
            imports.append(spec)
        return
    for child in node.children:
        _visit(child, scope, data, symbols, imports)


def _in_class(node: Node) -> bool:
    p = node.parent
    while p is not None:
        if p.type in ("class_specifier", "struct_specifier", "field_declaration_list"):
            return True
        if p.type in ("namespace_definition", "translation_unit"):
            return False
        p = p.parent
    return False


def _visit_template_child(child: Node, scope: list[str], data: bytes,
                          symbols: list[Symbol], imports: list[str],
                          outer: Node, outer_doc: str) -> None:
    if child.type == "function_definition":
        name = _func_name_in(child, data)
        if name is None:
            return
        doc = _leading_doc(child, data) or outer_doc
        _emit(symbols, scope, name, "function",
              _sig_up_to_body(child, data), doc, child)
        return
    if child.type in ("class_specifier", "struct_specifier"):
        name = _type_name(child, data)
        if name is None:
            return
        doc = _leading_doc(child, data) or outer_doc
        _emit(symbols, scope, name, "class",
              _sig_up_to_body(child, data), doc, child)
        for c in child.children:
            _visit(c, scope + [name], data, symbols, imports)
        return
    _visit(child, scope, data, symbols, imports)
