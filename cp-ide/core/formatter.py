"""A C++ source code formatter.

The formatter tokenises the source first and then re-emits it with a
consistent layout:

* indentation driven by the brace nesting, with proper handling of
  ``switch``/``case`` blocks, class bodies and access specifiers,
* spaces around binary operators, after commas and keywords,
* no space before ``;``, ``,``, ``)`` and ``]``,
* pointer/reference declarations written as ``int *p`` / ``int &ref``,
* string literals, character literals, raw strings and comments are never
  modified,
* preprocessor directives are copied verbatim,
* trailing comments of consecutive lines are aligned.

The implementation is intentionally self contained so that it works without
any external dependency such as ``clang-format``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Set, Tuple

# --------------------------------------------------------------------------- #
#  keyword tables
# --------------------------------------------------------------------------- #
CONTROL_KEYWORDS = {
    "if", "else", "for", "while", "do", "switch", "case", "default",
    "break", "continue", "return", "goto", "try", "catch", "throw",
}

TYPE_KEYWORDS = {
    "void", "bool", "char", "short", "int", "long", "float", "double",
    "signed", "unsigned", "auto", "const", "volatile", "static", "extern",
    "inline", "register", "wchar_t", "char8_t", "char16_t", "char32_t",
    "size_t", "ssize_t", "ptrdiff_t", "nullptr_t",
}

KEYWORDS = CONTROL_KEYWORDS | TYPE_KEYWORDS | {
    "class", "struct", "union", "enum", "namespace", "template", "typename",
    "using", "new", "delete", "sizeof", "alignof", "decltype", "noexcept",
    "operator", "this", "public", "private", "protected", "friend",
    "explicit", "virtual", "override", "final", "mutable", "constexpr",
    "consteval", "constinit", "concept", "requires", "co_await", "co_return",
    "co_yield", "static_assert", "asm", "typeid", "true", "false",
}

ACCESS_SPECIFIERS = {"public", "private", "protected"}

#: Keywords that are followed by a space and then a parenthesised expression.
PAREN_SPACE_KEYWORDS = {"if", "for", "while", "switch", "catch", "return", "case", "else", "do"}
#: Keywords that are directly followed by a parenthesised expression.
PAREN_NO_SPACE_KEYWORDS = {"sizeof", "alignof", "decltype", "new", "delete", "throw", "co_await"}

#: Keywords after which an operator is applied to a single operand.
UNARY_KEYWORDS = {
    "return", "case", "delete", "new", "throw", "else", "do", "co_return",
    "co_await", "sizeof", "alignof", "decltype", "true", "false", "nullptr",
}

OPERATORS = [
    ">>>=", "<<=", ">>=", "<=>", "->*", "...",
    "->", "++", "--", "<<", ">>", "<=", ">=", "==", "!=", "&&", "||",
    "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "::", ".*", "##",
    "+", "-", "*", "/", "%", "=", "<", ">", "!", "~", "&", "|", "^",
    "?", ":", ";", ",", ".", "(", ")", "[", "]", "{", "}", "#", "@",
]


# --------------------------------------------------------------------------- #
#  tokens
# --------------------------------------------------------------------------- #
@dataclass
class Token:
    kind: str      # ident | number | string | char | comment | op | pp
    text: str
    line: int
    col: int
    end_line: int = 0

    @property
    def is_comment(self) -> bool:
        return self.kind == "comment"

    @property
    def is_line_comment(self) -> bool:
        return self.kind == "comment" and self.text.startswith("//")


@dataclass
class FormatOptions:
    indent_size: int = 4
    use_tabs: bool = False
    brace_style: str = "allman"      # allman | kr
    space_around_operators: bool = True
    align_trailing_comments: bool = True
    max_blank_lines: int = 1
    keep_blank_lines: bool = True
    space_after_comma: bool = True
    space_before_brace: bool = True

    def to_dict(self) -> dict:
        return {
            "indent_size": self.indent_size,
            "use_tabs": self.use_tabs,
            "brace_style": self.brace_style,
            "space_around_operators": self.space_around_operators,
            "align_trailing_comments": self.align_trailing_comments,
            "max_blank_lines": self.max_blank_lines,
            "keep_blank_lines": self.keep_blank_lines,
            "space_after_comma": self.space_after_comma,
            "space_before_brace": self.space_before_brace,
        }


# --------------------------------------------------------------------------- #
#  tokeniser
# --------------------------------------------------------------------------- #
def _is_ident_start(ch: str) -> bool:
    return ch.isalpha() or ch == "_" or ord(ch) > 127


def _is_ident_part(ch: str) -> bool:
    return ch.isalnum() or ch == "_" or ord(ch) > 127


def tokenize(src: str) -> List[Token]:
    """Split *src* into a flat list of tokens (whitespace is dropped)."""
    tokens: List[Token] = []
    i = 0
    n = len(src)
    line = 1
    col = 1
    at_line_start = True

    def advance(text: str) -> None:
        nonlocal line, col
        nl = text.count("\n")
        if nl:
            line += nl
            col = len(text) - text.rfind("\n")
        else:
            col += len(text)

    while i < n:
        ch = src[i]

        if ch in " \t\r\n":
            j = i
            while j < n and src[j] in " \t\r\n":
                j += 1
            chunk = src[i:j]
            advance(chunk)
            i = j
            at_line_start = chunk.endswith("\n")
            continue

        if at_line_start and ch == "#":
            # Preprocessor directive: copy the raw text verbatim.
            j = i
            while j < n:
                end_of_line = src.find("\n", j)
                if end_of_line == -1:
                    end_of_line = n
                segment = src[j:end_of_line]
                if not segment.rstrip().endswith("\\"):
                    j = end_of_line
                    break
                j = end_of_line + 1
                if j > n:
                    j = n
                    break
            raw = src[i:j]
            tokens.append(Token("pp", raw, line, col))
            advance(raw)
            i = j
            at_line_start = False
            continue

        at_line_start = False
        start_line, start_col = line, col

        # comments
        if ch == "/" and i + 1 < n and src[i + 1] == "/":
            end = src.find("\n", i)
            if end == -1:
                end = n
            text = src[i:end].rstrip("\r")
            tokens.append(Token("comment", text, start_line, start_col))
            advance(src[i:end])
            i = end
            continue
        if ch == "/" and i + 1 < n and src[i + 1] == "*":
            end = src.find("*/", i + 2)
            end = n if end == -1 else end + 2
            text = src[i:end]
            tokens.append(Token("comment", text, start_line, start_col, line))
            advance(text)
            i = end
            continue

        # raw string literals: R"delim(...)delim"
        raw_match = re.match(r'(?:u8|u|U|L)?R"([^()\\ ]{0,16})\(', src[i:])
        if raw_match:
            delim = raw_match.group(1)
            terminator = ')' + delim + '"'
            end = src.find(terminator, i + raw_match.end())
            end = n if end == -1 else end + len(terminator)
            text = src[i:end]
            tokens.append(Token("string", text, start_line, start_col, line))
            advance(text)
            i = end
            continue

        # normal string literal (with an optional encoding prefix)
        if ch == '"' or (ch in "u8uUL" and i + 1 < n and src[i + 1] == '"'):
            j = i + 1 if ch != '"' else i
            j += 1
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == '"':
                    j += 1
                    break
                if src[j] == "\n":
                    break
                j += 1
            text = src[i:j]
            tokens.append(Token("string", text, start_line, start_col, line))
            advance(text)
            i = j
            continue

        # character literal
        if ch == "'" or (ch in "uUL" and i + 1 < n and src[i + 1] == "'"):
            j = i + 1 if ch != "'" else i
            j += 1
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == "'":
                    j += 1
                    break
                if src[j] == "\n":
                    break
                j += 1
            text = src[i:j]
            tokens.append(Token("char", text, start_line, start_col, line))
            advance(text)
            i = j
            continue

        # number
        if ch.isdigit() or (ch == "." and i + 1 < n and src[i + 1].isdigit()):
            j = i
            while j < n:
                c = src[j]
                if c.isalnum() or c == ".":
                    j += 1
                    continue
                if c in "+-" and j > i and src[j - 1] in "eEpP" and src[j - 1] not in "xX":
                    j += 1
                    continue
                break
            text = src[i:j]
            tokens.append(Token("number", text, start_line, start_col))
            advance(text)
            i = j
            continue

        # identifier / keyword
        if _is_ident_start(ch):
            j = i
            while j < n and _is_ident_part(src[j]):
                j += 1
            text = src[i:j]
            tokens.append(Token("ident", text, start_line, start_col))
            advance(text)
            i = j
            continue

        # operators
        matched = False
        for op in OPERATORS:
            if src.startswith(op, i):
                tokens.append(Token("op", op, start_line, start_col))
                advance(op)
                i += len(op)
                matched = True
                break
        if matched:
            continue
        tokens.append(Token("op", ch, start_line, start_col))
        advance(ch)
        i += 1

    return tokens


# --------------------------------------------------------------------------- #
#  template detection
# --------------------------------------------------------------------------- #
def _looks_like_template(tokens: Sequence[Token], index: int) -> bool:
    """Decide whether the ``<`` at *index* opens a template argument list."""
    depth = 0
    limit = min(len(tokens), index + 60)
    for j in range(index, limit):
        tok = tokens[j]
        if tok.kind != "op":
            if tok.kind == "ident":
                continue
            return False
        text = tok.text
        if text == "<":
            depth += 1
            if depth == 1:
                nxt = tokens[j + 1] if j + 1 < len(tokens) else None
                if nxt is None or nxt.kind != "ident":
                    return False
        elif text == ">":
            depth -= 1
            if depth == 0:
                return True
        elif text == ">>":
            depth -= 2
            if depth <= 0:
                return True
        elif text in (";", "{", "}", ")", "(", "=", "==", "!=", "&&", "||",
                      "?", ":", "!", "<<", ">>", "+", "-", "*", "/", "%",
                      ">=", "<=", "+=", "-=", "&", "|", "^"):
            return False
        elif text in (",", "*", "&", "::", "...", "["):
            continue
        else:
            return False
    return False


# --------------------------------------------------------------------------- #
#  the formatter
# --------------------------------------------------------------------------- #
@dataclass
class Frame:
    kind: str = "block"        # block | class | namespace | init | switch
    case_extra: int = 0
    is_switch: bool = False


class Formatter:
    def __init__(self, src: str, options: Optional[FormatOptions] = None):
        self.src = src
        self.opt = options or FormatOptions()
        self.tokens = tokenize(src)
        self.template_open: Set[int] = set()
        for idx, tok in enumerate(self.tokens):
            if tok.kind == "op" and tok.text == "<":
                if _looks_like_template(self.tokens, idx):
                    self.template_open.add(idx)

        self.lines: List[str] = []
        self.current: List[Tuple[str, bool]] = []
        self.frames: List[Frame] = []
        self.paren_stack: List[bool] = []     # True when the paren is a cast
        self.template_depth = 0
        self.pending_switch = False
        self.pending_class = False
        self.pending_namespace = False
        self.question_depth = 0
        self.prev: Optional[Token] = None
        self.prev_op_unary = False
        self.blank_count = 0
        self.pending_indent = True
        self.has_content = False
        self.stmt_keyword: Optional[str] = None
        self.last_token: Optional[Token] = None

    # ------------------------------------------------------------------ #
    #  output helpers
    # ------------------------------------------------------------------ #
    def _case_extra(self) -> int:
        for frame in reversed(self.frames):
            if frame.is_switch:
                return frame.case_extra
        return 0

    def _indent_text(self) -> str:
        level = len(self.frames) + self._case_extra()
        if level <= 0:
            return ""
        if self.opt.use_tabs:
            return "\t" * level
        return " " * (level * self.opt.indent_size)

    def _flush(self) -> None:
        if self.current:
            self.lines.append(self._line_text(self.current))
            self.current = []
        self.pending_indent = True
        self.has_content = False

    @staticmethod
    def _line_text(segments: Sequence[Tuple[str, bool]]) -> str:
        return "".join(seg for seg, _ in segments)

    def _start_line(self) -> None:
        """Prepare a new line: blank lines and the indentation."""
        if self.current:
            return
        if self.blank_count and self.opt.keep_blank_lines and self.lines \
                and self.lines[-1] != "":
            for _ in range(min(self.blank_count, max(0, self.opt.max_blank_lines))):
                self.lines.append("")
        self.blank_count = 0
        if self.pending_indent:
            indent = self._indent_text()
            if indent:
                self.current.append((indent, False))
            self.pending_indent = False

    def _sep(self) -> None:
        """Emit the separator in front of a token."""
        self._start_line()
        if self.has_content:
            self.current.append((" ", False))

    def _emit(self, text: str, is_comment: bool = False) -> None:
        if text == "":
            return
        self._start_line()
        self.current.append((text, is_comment))
        self.has_content = True

    def _newline(self, keep_blank: bool = True) -> None:
        """Finish the current line and start a new one."""
        self._flush()
        if not keep_blank:
            self.blank_count = 0

    # ------------------------------------------------------------------ #
    #  helpers
    # ------------------------------------------------------------------ #
    def _token_before(self, tok: Optional[Token]) -> Optional[Token]:
        if tok is None:
            return None
        for position, candidate in enumerate(self.tokens):
            if candidate is tok:
                return self.tokens[position - 1] if position > 0 else None
        return None

    def _is_unary_context(self, tok: Optional[Token]) -> bool:
        """True when an operator in this position acts on a single operand."""
        if tok is None:
            return True
        if tok.kind == "op":
            return tok.text not in (")", "]", "}")
        if tok.kind == "ident":
            return tok.text in UNARY_KEYWORDS
        return False

    def _in_init_list(self) -> bool:
        return bool(self.frames) and self.frames[-1].kind == "init"

    def _in_class(self) -> bool:
        return bool(self.frames) and self.frames[-1].kind == "class"

    def _is_init_list(self, prev: Optional[Token]) -> bool:
        if prev is None:
            return False
        if prev.kind == "op" and prev.text in ("=", ",", "(", "["):
            return True
        if prev.kind == "ident" and prev.text == "return":
            return True
        if prev.kind == "ident" and self.stmt_keyword and \
                self.stmt_keyword not in KEYWORDS and self.stmt_keyword[:1].isupper():
            return True
        return False

    def _looks_like_cast(self, prev: Optional[Token]) -> bool:
        if prev is None:
            return False
        if prev.kind == "ident" and prev.text in TYPE_KEYWORDS:
            return True
        if prev.kind == "ident" and prev.text not in KEYWORDS and prev.text[:1].isupper():
            return True
        return False

    def _is_pointer_declaration(self, prev: Optional[Token]) -> bool:
        if prev is None:
            return True
        if prev.kind == "ident":
            if prev.text in TYPE_KEYWORDS:
                return True
            if prev.text not in KEYWORDS and prev.text[:1].isupper():
                return True
            return False
        if prev.kind == "op" and prev.text in ("*", "&"):
            before = self._token_before(prev)
            if before is not None and before.kind == "ident" and (
                before.text in TYPE_KEYWORDS
                or (before.text not in KEYWORDS and before.text[:1].isupper())
            ):
                return True
        return False

    def _is_unary_operator(self, text: str, prev: Optional[Token]) -> bool:
        if text in ("!", "~"):
            return True
        if text in ("++", "--", "+", "-"):
            return self._is_unary_context(prev)
        if text in ("*", "&"):
            if self._is_pointer_declaration(prev):
                return True
            return self._is_unary_context(prev)
        return False

    def _colon_is_label(self, prev: Optional[Token]) -> bool:
        """True when the colon closes a label (``case 1:``, ``public:``, ``a:``)."""
        if self.question_depth > 0:
            return False
        if self.stmt_keyword in ("case", "default"):
            return True
        if prev is None:
            return False
        if prev.kind == "ident" and prev.text in ACCESS_SPECIFIERS:
            return True
        if prev.kind == "ident" and prev.text not in KEYWORDS:
            before = self._token_before(prev)
            if before is None:
                return True
            if before.kind == "op" and before.text in (";", "{", "}", ":"):
                return True
        return False

    # ------------------------------------------------------------------ #
    #  spacing rules
    # ------------------------------------------------------------------ #
    def _needs_space(self, prev: Optional[Token], nxt: Token) -> bool:
        if prev is None:
            return False
        pt, nt = prev.text, nxt.text

        # comments always keep a space around them
        if nxt.kind == "comment" or prev.kind == "comment":
            return True

        # never a space in front of these
        if nt in (")", "]", ";", ",", "::", ".", "...", "->", "->*", ".*"):
            return False
        if nt == "[":
            return pt in ("=", ",", "(", ":") or \
                (prev.kind == "ident" and prev.text == "return")

        # never a space after these
        if pt in ("(", "[", "::", ".", "->", "->*", ".*"):
            if pt == "->" and nxt.kind == "ident" and nxt.text in TYPE_KEYWORDS:
                return True
            return False
        if pt == ",":
            return self.opt.space_after_comma

        # '(' handling
        if nt == "(":
            if prev.kind == "ident":
                if prev.text in PAREN_SPACE_KEYWORDS:
                    return True
                if prev.text in PAREN_NO_SPACE_KEYWORDS:
                    return False
            return False

        # '{' handling
        if nt == "{":
            if self._is_init_list(prev):
                return False
            return self.opt.space_before_brace
        if pt == "{":
            return not self._in_init_list()

        # ':' handling
        if nt == ":":
            return not self._colon_is_label(prev)

        # after a closing bracket
        if pt == ")":
            return not (self.paren_stack and self.paren_stack[-1])
        if pt in ("]", "}", ";"):
            return True

        # template brackets
        if pt == "<" and self.template_depth > 0:
            return False

        # postfix increment / decrement
        if nt in ("++", "--"):
            if prev.kind in ("ident", "number") or pt in (")", "]", "}"):
                return False
            return True

        # a unary operator is glued to its operand
        if prev.kind == "op" and self.prev_op_unary:
            return False

        # keywords are always separated by a space
        if prev.kind == "ident" and prev.text in KEYWORDS:
            return True
        if nxt.kind == "ident" and nxt.text in KEYWORDS:
            return True

        return True

    # ------------------------------------------------------------------ #
    #  main loop
    # ------------------------------------------------------------------ #
    def run(self) -> str:
        tokens = self.tokens
        index = 0
        total = len(tokens)

        while index < total:
            tok = tokens[index]

            # blank line bookkeeping based on the original layout
            if self.last_token is not None:
                previous_end = self.last_token.end_line or self.last_token.line
                gap = tok.line - previous_end
                if gap > 1:
                    self.blank_count = min(self.blank_count + (gap - 1), 5)
            self.last_token = tok

            if tok.kind == "pp":
                self._newline(keep_blank=self.opt.keep_blank_lines)
                self.pending_indent = False
                self._emit(tok.text.rstrip())
                self._flush()
                self.prev = None
                self.prev_op_unary = False
                self.stmt_keyword = None
                index += 1
                continue

            if tok.kind == "comment":
                if self._needs_space(self.prev, tok):
                    self._sep()
                self.current.append((tok.text, True))
                self.prev = tok
                self.prev_op_unary = False
                if tok.is_line_comment:
                    self._newline(keep_blank=False)
                index += 1
                continue

            if tok.kind == "op":
                index = self._handle_operator(tok, tokens, index)
                continue

            self._handle_value(tok)
            index += 1

        self._flush()
        return self._render()

    # ------------------------------------------------------------------ #
    def _handle_value(self, tok: Token) -> None:
        if tok.kind == "ident":
            # the state has to be updated before the line is started, because
            # the indentation depends on it
            if self.stmt_keyword is None:
                self.stmt_keyword = tok.text
            if tok.text in ("class", "struct", "union"):
                self.pending_class = True
            elif tok.text == "namespace":
                self.pending_namespace = True
            elif tok.text == "switch":
                self.pending_switch = True
            elif tok.text in ("case", "default"):
                self._reset_case_extra()

        if self._needs_space(self.prev, tok):
            self._sep()

        if tok.kind == "ident" and tok.text in ACCESS_SPECIFIERS and self._in_class():
            self._emit(tok.text)
            self.prev = tok
            self.prev_op_unary = False
            self.stmt_keyword = None
            return

        self._emit(tok.text)
        self.prev = tok
        self.prev_op_unary = False

    # ------------------------------------------------------------------ #
    def _handle_operator(self, tok: Token, tokens: Sequence[Token], index: int) -> int:
        text = tok.text
        prev = self.prev

        # ---- braces --------------------------------------------------- #
        if text == "{":
            if self._brace_inline(prev):
                if self._needs_space(prev, tok):
                    self._sep()
            else:
                self._newline(keep_blank=self.opt.keep_blank_lines)
            self._emit("{")
            kind = "block"
            if self.pending_class:
                kind = "class"
                self.pending_class = False
            elif self.pending_namespace:
                kind = "namespace"
                self.pending_namespace = False
            elif self._is_init_list(prev):
                kind = "init"
            frame = Frame(kind=kind, is_switch=self.pending_switch)
            self.pending_switch = False
            self.frames.append(frame)
            self.prev = tok
            self.prev_op_unary = False
            self.stmt_keyword = None
            if kind != "init":
                self._newline(keep_blank=False)
            return index + 1

        if text == "}":
            is_init = self._in_init_list()
            if self.frames:
                self.frames.pop()
            if not is_init:
                self._newline(keep_blank=self.opt.keep_blank_lines)
            self._emit("}")
            self.prev = tok
            self.prev_op_unary = False
            self.stmt_keyword = None
            # in Allman style the following statement starts on a new line
            nxt = tokens[index + 1] if index + 1 < len(tokens) else None
            if self.opt.brace_style == "allman" and nxt is not None and \
                    not (nxt.kind == "op" and nxt.text in (",", ";", ")", "]")):
                self._newline(keep_blank=False)
            return index + 1

        if text == ";":
            if self._needs_space(prev, tok):
                self._sep()
            self._emit(";")
            self.prev = tok
            self.prev_op_unary = False
            if not self.paren_stack:
                self._newline(keep_blank=False)
                self.stmt_keyword = None
                self.question_depth = 0
            return index + 1

        if text == ":":
            if self._colon_is_label(prev):
                self._emit(":")
                if self.stmt_keyword in ("case", "default"):
                    self._newline(keep_blank=False)
                    self._after_label()
                    self.stmt_keyword = None
                elif prev is not None and prev.kind == "ident" and \
                        prev.text in ACCESS_SPECIFIERS:
                    self._newline(keep_blank=False)
                    self.stmt_keyword = None
            else:
                if self._needs_space(prev, tok):
                    self._sep()
                self._emit(":")
                if self.question_depth > 0:
                    self.question_depth -= 1
            self.prev = tok
            self.prev_op_unary = False
            return index + 1

        if text == "(":
            self.paren_stack.append(self._looks_like_cast(prev))
            if self._needs_space(prev, tok):
                self._sep()
            self._emit("(")
            self.prev = tok
            self.prev_op_unary = False
            return index + 1

        if text == ")":
            if self.paren_stack:
                self.paren_stack.pop()
            self._emit(")")
            self.prev = tok
            self.prev_op_unary = False
            return index + 1

        if text == "[":
            self.paren_stack.append(False)
            if self._needs_space(prev, tok):
                self._sep()
            self._emit("[")
            self.prev = tok
            self.prev_op_unary = False
            return index + 1

        if text == "]":
            if self.paren_stack:
                self.paren_stack.pop()
            self._emit("]")
            self.prev = tok
            self.prev_op_unary = False
            return index + 1

        if text == "?":
            if self._needs_space(prev, tok):
                self._sep()
            self._emit("?")
            self.question_depth += 1
            self.prev = tok
            self.prev_op_unary = False
            return index + 1

        # template brackets
        if text == "<" and index in self.template_open:
            self.template_depth += 1
            self._emit("<")
            self.prev = tok
            self.prev_op_unary = False
            return index + 1

        if text == ">" and self.template_depth > 0:
            self.template_depth -= 1
            self._emit(">")
            self.prev = tok
            self.prev_op_unary = False
            return index + 1

        if text == ">>" and self.template_depth >= 2:
            self.template_depth -= 2
            self._emit(">>")
            self.prev = tok
            self.prev_op_unary = False
            return index + 1

        # pointer / reference declarations
        if text in ("*", "&"):
            if self._is_pointer_declaration(prev):
                if not (prev.kind == "op" and prev.text in ("*", "&")):
                    if self._needs_space(prev, tok):
                        self._sep()
                self._emit(text)
                self.prev = tok
                self.prev_op_unary = True
                return index + 1

        # default operator
        if self._needs_space(prev, tok):
            self._sep()
        self._emit(text)
        self.prev = tok
        self.prev_op_unary = self._is_unary_operator(text, prev)
        return index + 1

    # ------------------------------------------------------------------ #
    def _after_label(self) -> None:
        """Increase the indentation of the body of a ``case`` label."""
        for frame in reversed(self.frames):
            if frame.is_switch:
                frame.case_extra = 1
                break

    def _reset_case_extra(self) -> None:
        """A new ``case`` label starts at the level of the switch body."""
        for frame in reversed(self.frames):
            if frame.is_switch:
                frame.case_extra = 0
                break

    def _brace_inline(self, prev: Optional[Token]) -> bool:
        """True when the ``{`` should stay on the current line."""
        if self._is_init_list(prev):
            return True
        if self.opt.brace_style != "kr":
            return False
        return self.stmt_keyword in ("if", "for", "while", "switch", "catch",
                                     "else", "do", "try")

    # ------------------------------------------------------------------ #
    def _render(self) -> str:
        lines = list(self.lines)
        if self.opt.align_trailing_comments:
            lines = self._align_trailing_comments(lines)
        return "\n".join(lines).rstrip() + "\n"

    def _align_trailing_comments(self, lines: List[str]) -> List[str]:
        result = list(lines)
        i = 0
        while i < len(result):
            line = result[i]
            if line.strip() and "//" in line and not line.strip().startswith("//"):
                j = i
                while j < len(result) and result[j].strip() and "//" in result[j] \
                        and not result[j].strip().startswith("//"):
                    j += 1
                group = result[i:j]
                codes = [entry.split("//", 1)[0].rstrip() for entry in group]
                target = max(len(code) for code in codes) + 1
                if target <= 100:
                    new_group = []
                    for entry, code in zip(group, codes):
                        comment = entry.split("//", 1)[1]
                        new_group.append(code + " " * (target - len(code)) + "//" + comment)
                    result[i:j] = new_group
                i = j
            else:
                i += 1
        return result


# --------------------------------------------------------------------------- #
#  public entry point
# --------------------------------------------------------------------------- #
def format_code(src: str, options: Optional[FormatOptions] = None) -> str:
    """Format C++ source code and return the result."""
    if not src or not src.strip():
        return src
    return Formatter(src, options).run()
