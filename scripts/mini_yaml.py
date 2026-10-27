"""Small, dependency-free YAML subset loader (MIT, Redirhan Labs).

Used when PyYAML is not installed. Supports what this skill's files use:
block mappings and sequences (2-space indents), sequences of mappings ("- key: value"),
plain / 'single' / "double" quoted scalars, flow lists ([a, "b", 3]), block scalars (| and >,
with optional - chomping), comments, int / float / true / false / null.
Dates stay strings (PyYAML would turn them into date objects; callers use str()).
"""
from __future__ import annotations

import re

__all__ = ["load", "loads", "YamlError"]


class YamlError(ValueError):
    pass


def load(path):
    with open(path, encoding="utf-8") as fh:
        return loads(fh.read())


def loads(text: str):
    lines = text.replace("\r\n", "\n").replace("\t", "  ").split("\n")
    parser = _Parser(lines)
    return parser.parse()


_INT = re.compile(r"^[-+]?\d+$")
_FLOAT = re.compile(r"^[-+]?(\d+\.\d*|\.\d+|\d+)([eE][-+]?\d+)?$")


def _strip_comment(s: str) -> str:
    """Remove a trailing ' # comment' outside quotes."""
    out, q, i = [], None, 0
    while i < len(s):
        c = s[i]
        if q:
            out.append(c)
            if q == "'" and c == "'" and i + 1 < len(s) and s[i + 1] == "'":
                out.append("'")
                i += 2
                continue
            if q == '"' and c == "\\" and i + 1 < len(s):
                out.append(s[i + 1])
                i += 2
                continue
            if c == q:
                q = None
        else:
            if c in "'\"" and (i == 0 or s[i - 1] in " [,:-"):
                q = c
            elif c == "#" and (i == 0 or s[i - 1] == " "):
                break
            out.append(c)
        i += 1
    return "".join(out).rstrip()


def _scalar(tok: str):
    tok = tok.strip()
    if tok == "" or tok in ("~", "null", "Null", "NULL"):
        return None
    if tok[0] == '"':
        if not tok.endswith('"') or len(tok) < 2:
            raise YamlError(f"unterminated string: {tok}")
        body = tok[1:-1]
        return re.sub(r'\\(["\\/nt])', lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), body)
    if tok[0] == "'":
        if not tok.endswith("'") or len(tok) < 2:
            raise YamlError(f"unterminated string: {tok}")
        return tok[1:-1].replace("''", "'")
    if tok[0] == "[":
        return _flow_list(tok)
    if tok in ("true", "True", "TRUE"):
        return True
    if tok in ("false", "False", "FALSE"):
        return False
    if _INT.match(tok):
        return int(tok)
    if _FLOAT.match(tok) and any(ch.isdigit() for ch in tok):
        return float(tok)
    return tok


def _flow_list(tok: str):
    if not tok.endswith("]"):
        raise YamlError(f"unterminated flow list: {tok}")
    body = tok[1:-1]
    items, cur, q = [], [], None
    i = 0
    while i < len(body):
        c = body[i]
        if q:
            cur.append(c)
            if q == '"' and c == "\\" and i + 1 < len(body):
                cur.append(body[i + 1])
                i += 2
                continue
            if c == q:
                if q == "'" and i + 1 < len(body) and body[i + 1] == "'":
                    cur.append("'")
                    i += 2
                    continue
                q = None
        elif c in "'\"":
            q = c
            cur.append(c)
        elif c == ",":
            items.append("".join(cur))
            cur = []
        else:
            cur.append(c)
        i += 1
    if "".join(cur).strip():
        items.append("".join(cur))
    return [_scalar(x) for x in items]


def _split_key(s: str):
    """'key: value' -> (key, value) ; returns None if not a mapping line."""
    q = None
    for i, c in enumerate(s):
        if q:
            if c == q:
                q = None
            continue
        if c in "'\"" and i == 0:
            q = c
            continue
        if c == ":" and (i + 1 == len(s) or s[i + 1] == " "):
            key = s[:i].strip()
            if key.startswith(("'", '"')):
                key = _scalar(key)
            return key, s[i + 1:].strip()
    return None


class _Parser:
    def __init__(self, lines):
        self.lines = lines
        self.i = 0

    # -- helpers -------------------------------------------------------
    def _next_content(self):
        """Advance past blank/comment lines; return (indent, text) or None."""
        while self.i < len(self.lines):
            raw = self.lines[self.i]
            stripped = raw.strip()
            if stripped == "" or stripped.startswith("#") or stripped in ("---", "..."):
                self.i += 1
                continue
            return len(raw) - len(raw.lstrip(" ")), raw.strip()
        return None

    def parse(self):
        nc = self._next_content()
        if nc is None:
            return None
        return self._block(nc[0])

    def _block(self, indent):
        nc = self._next_content()
        if nc is None:
            return None
        ind, text = nc
        if text.startswith("- ") or text == "-":
            return self._seq(ind)
        return self._map(ind)

    def _block_scalar(self, header, parent_indent):
        folded = header.startswith(">")
        strip_trailing = header.endswith("-")
        self.i += 1
        body, block_indent = [], None
        while self.i < len(self.lines):
            raw = self.lines[self.i]
            if raw.strip() == "":
                body.append("")
                self.i += 1
                continue
            ind = len(raw) - len(raw.lstrip(" "))
            if block_indent is None:
                if ind <= parent_indent:
                    break
                block_indent = ind
            if ind < block_indent:
                break
            body.append(raw[block_indent:])
            self.i += 1
        while body and body[-1] == "":
            body.pop()
        if folded:
            # plain folding: lines of a paragraph join with a space, each blank line -> one newline
            text, para = "", []
            for ln in body:
                if ln == "":
                    if para:
                        text += " ".join(para)
                        para = []
                    text += "\n"
                else:
                    para.append(ln.strip())
            text += " ".join(para)
            value = text
        else:
            value = "\n".join(body)
        if strip_trailing:
            return value
        return value + "\n"  # clip and keep both end with exactly one newline here

    def _value_after_key(self, rest, key_indent):
        """Value for 'key:' given the remainder of the line."""
        rest = _strip_comment(rest)
        if rest in ("|", "|-", "|+", ">", ">-", ">+"):
            return self._block_scalar(rest, key_indent)
        self.i += 1
        if rest != "":
            return _scalar(rest)
        nc = self._next_content()
        if nc is None:
            return None
        ind, text = nc
        if ind > key_indent:
            return self._block(ind)
        if ind == key_indent and (text.startswith("- ") or text == "-"):
            return self._seq(ind)  # YAML allows a sequence at the key's own indent
        return None

    def _map(self, indent):
        out = {}
        while True:
            nc = self._next_content()
            if nc is None:
                break
            ind, text = nc
            if ind < indent:
                break
            if ind > indent:
                raise YamlError(f"line {self.i + 1}: unexpected indent")
            if text.startswith("- ") or text == "-":
                break
            kv = _split_key(_strip_comment(text))
            if kv is None:
                raise YamlError(f"line {self.i + 1}: expected 'key: value', got {text!r}")
            key, rest = kv
            out[key] = self._value_after_key(rest, indent)
        return out

    def _seq(self, indent):
        out = []
        while True:
            nc = self._next_content()
            if nc is None:
                break
            ind, text = nc
            if ind != indent or not (text.startswith("- ") or text == "-"):
                if ind > indent:
                    raise YamlError(f"line {self.i + 1}: unexpected indent in list")
                break
            item = text[1:].strip()
            item_indent = indent + 2
            if item == "":
                self.i += 1
                nc2 = self._next_content()
                out.append(self._block(nc2[0]) if nc2 and nc2[0] > indent else None)
                continue
            kv = _split_key(_strip_comment(item)) if not item.startswith(("'", '"', "[")) else None
            if kv is None:
                ic = _strip_comment(item)
                if ic in ("|", "|-", "|+", ">", ">-", ">+"):
                    out.append(self._block_scalar(ic, indent))
                else:
                    out.append(_scalar(ic))
                    self.i += 1
                continue
            # sequence of mappings: first key on the dash line, rest indented by 2
            key, rest = kv
            mapping = {key: self._value_after_key(rest, item_indent)}
            nc2 = self._next_content()
            if nc2 is not None and nc2[0] == item_indent and not nc2[1].startswith("- "):
                mapping.update(self._map(item_indent))
            out.append(mapping)
        return out
