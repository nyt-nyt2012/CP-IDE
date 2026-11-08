"""The code snippet library used by the "insert code" feature.

Snippets are inserted *before* the current source code.  Each snippet
declares where it should be placed:

``top``
    at the very top of the file,
``after_include``
    right after the last ``#include`` line,
``before_main``
    right before the ``main`` function,
``cursor``
    at the current cursor position of the editor.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .paths import data_dir

APP_DIR = data_dir()
SNIPPET_STORE = os.path.join(APP_DIR, "data", "snippets.json")

POSITIONS = ("top", "after_include", "before_main", "cursor")

POSITION_LABELS = {
    "top": "文件最前",
    "after_include": "在 #include 之后",
    "before_main": "在 main 函数之前",
    "cursor": "在光标处",
}


@dataclass
class Snippet:
    id: str
    name: str
    description: str
    code: str
    position: str = "top"
    builtin: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "code": self.code,
            "position": self.position,
            "builtin": self.builtin,
        }


# --------------------------------------------------------------------------- #
#  the built-in library
# --------------------------------------------------------------------------- #
BUILTIN_SNIPPETS: List[Snippet] = [
    Snippet(
        id="bits",
        name="万能头文件",
        description="#include <bits/stdc++.h>",
        code="#include <bits/stdc++.h>",
        position="top",
        builtin=True,
    ),
    Snippet(
        id="using",
        name="using namespace std;",
        description="打开标准库命名空间",
        code="using namespace std;",
        position="top",
        builtin=True,
    ),
    Snippet(
        id="fastio",
        name="快速输入输出",
        description="基于 fread / fwrite 的快速读写模板",
        code="""class FastIO {
public:
    static const int S = 1 << 20;
    char ibuf[S], obuf[S];
    int ipos = 0, ilen = 0, opos = 0;
    ~FastIO() { flush(); }
    inline char gc() {
        if (ipos == ilen) {
            ilen = (int)fread(ibuf, 1, S, stdin);
            ipos = 0;
            if (!ilen) return 0;
        }
        return ibuf[ipos++];
    }
    template <class T> inline bool read(T &x) {
        char c = gc();
        while (c && (c < '0' || c > '9') && c != '-') c = gc();
        if (!c) return false;
        bool neg = false;
        if (c == '-') { neg = true; c = gc(); }
        x = 0;
        while (c >= '0' && c <= '9') { x = x * 10 + (c - '0'); c = gc(); }
        if (neg) x = -x;
        return true;
    }
    inline void pc(char c) {
        if (opos == S) flush();
        obuf[opos++] = c;
    }
    template <class T> inline void write(T x) {
        if (x < 0) { pc('-'); x = -x; }
        char s[24];
        int n = 0;
        do { s[n++] = char('0' + x % 10); x /= 10; } while (x);
        while (n) pc(s[--n]);
    }
    inline void puts_(const char *s) { while (*s) pc(*s++); }
    inline void flush() { if (opos) { fwrite(obuf, 1, opos, stdout); opos = 0; } }
};""",
        position="top",
        builtin=True,
    ),
    Snippet(
        id="debug",
        name="调试输出宏",
        description="dbg(x) 打印变量到 stderr",
        code="""#define dbg(x) cerr << #x << " = " << (x) << endl
#define dbgl(x) cerr << #x << " = " << (x) << " at line " << __LINE__ << endl""",
        position="top",
        builtin=True,
    ),
    Snippet(
        id="consts",
        name="常用常量",
        description="MOD / INF / EPS 等常量定义",
        code="""const int MOD = 1000000007;
const long long INF = (1LL << 62);
const double EPS = 1e-9;
const int dx[4] = {0, 1, 0, -1};
const int dy[4] = {1, 0, -1, 0};""",
        position="top",
        builtin=True,
    ),
    Snippet(
        id="prefix",
        name="字符串转数字",
        description="split / stoll 辅助函数",
        code="""vector<string> split(const string &s, char sep = ' ') {
    vector<string> res;
    string cur;
    for (char c : s) {
        if (c == sep) { res.push_back(cur); cur.clear(); }
        else cur.push_back(c);
    }
    res.push_back(cur);
    return res;
}""",
        position="top",
        builtin=True,
    ),
    Snippet(
        id="fenwick",
        name="树状数组",
        description="Fenwick 树模板",
        code="""struct Fenwick {
    int n;
    vector<int> t;
    Fenwick(int n) : n(n), t(n + 1, 0) {}
    void add(int x, int v) { for (; x <= n; x += x & -x) t[x] += v; }
    int sum(int x) { int r = 0; for (; x; x -= x & -x) r += t[x]; return r; }
    int query(int l, int r) { return sum(r) - sum(l - 1); }
};""",
        position="top",
        builtin=True,
    ),
    Snippet(
        id="segtree",
        name="线段树",
        description="区间求和线段树模板",
        code="""struct SegTree {
    int n;
    vector<int> t;
    SegTree(int n) : n(n), t(4 * n + 4, 0) {}
    void build(int p, int l, int r, const vector<int> &a) {
        if (l == r) { t[p] = a[l]; return; }
        int m = (l + r) >> 1;
        build(p << 1, l, m, a);
        build(p << 1 | 1, m + 1, r, a);
        t[p] = t[p << 1] + t[p << 1 | 1];
    }
    void build(const vector<int> &a) { build(1, 1, n, a); }
    void add(int p, int l, int r, int x, int v) {
        if (l == r) { t[p] += v; return; }
        int m = (l + r) >> 1;
        if (x <= m) add(p << 1, l, m, x, v);
        else add(p << 1 | 1, m + 1, r, x, v);
        t[p] = t[p << 1] + t[p << 1 | 1];
    }
    void add(int x, int v) { add(1, 1, n, x, v); }
    int query(int p, int l, int r, int L, int R) {
        if (L <= l && r <= R) return t[p];
        int m = (l + r) >> 1, res = 0;
        if (L <= m) res += query(p << 1, l, m, L, R);
        if (R > m) res += query(p << 1 | 1, m + 1, r, L, R);
        return res;
    }
    int query(int L, int R) { return query(1, 1, n, L, R); }
};""",
        position="top",
        builtin=True,
    ),
    Snippet(
        id="mainheader",
        name="程序头注释",
        description="在文件顶部插入注释头",
        code="""/*
 *  File: %FILENAME%
 *  Problem: %TITLE%
 *  Author: %AUTHOR%
 *  Date: %DATE%
 */""",
        position="top",
        builtin=True,
    ),
]


# --------------------------------------------------------------------------- #
#  user snippets
# --------------------------------------------------------------------------- #
def _load_user_snippets() -> List[Snippet]:
    if not os.path.isfile(SNIPPET_STORE):
        return []
    try:
        with open(SNIPPET_STORE, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []
    result = []
    for item in data if isinstance(data, list) else []:
        try:
            result.append(
                Snippet(
                    id=str(item.get("id") or "user-%d" % len(result)),
                    name=str(item.get("name") or "未命名片段"),
                    description=str(item.get("description") or ""),
                    code=str(item.get("code") or ""),
                    position=item.get("position") if item.get("position") in POSITIONS else "top",
                    builtin=False,
                )
            )
        except Exception:  # pragma: no cover - defensive
            continue
    return result


def _save_user_snippets(snippets: List[Snippet]) -> None:
    os.makedirs(os.path.dirname(SNIPPET_STORE), exist_ok=True)
    payload = [s.to_dict() for s in snippets if not s.builtin]
    with open(SNIPPET_STORE, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def all_snippets() -> List[Snippet]:
    return BUILTIN_SNIPPETS + _load_user_snippets()


def get_snippet(snippet_id: str) -> Optional[Snippet]:
    for snippet in all_snippets():
        if snippet.id == snippet_id:
            return snippet
    return None


def save_user_snippet(snippet: Snippet) -> Snippet:
    snippets = _load_user_snippets()
    for index, existing in enumerate(snippets):
        if existing.id == snippet.id:
            snippets[index] = snippet
            break
    else:
        snippets.append(snippet)
    _save_user_snippets(snippets)
    return snippet


def delete_user_snippet(snippet_id: str) -> bool:
    snippets = _load_user_snippets()
    remaining = [s for s in snippets if s.id != snippet_id]
    if len(remaining) == len(snippets):
        return False
    _save_user_snippets(remaining)
    return True


# --------------------------------------------------------------------------- #
#  insertion
# --------------------------------------------------------------------------- #
_INCLUDE_RE = re.compile(r"^\s*#\s*include\b")
_MAIN_RE = re.compile(r"^\s*(?:int|long|void|auto)\s+main\s*\(")


def insert_snippet(code: str, snippet: Snippet, position: Optional[str] = None) -> str:
    """Insert *snippet* into *code* at the requested position."""
    position = position or snippet.position
    payload = snippet.code
    if not payload:
        return code

    if position == "cursor":
        return payload + code

    lines = code.split("\n")

    if position == "after_include":
        last_include = -1
        for index, line in enumerate(lines):
            if _INCLUDE_RE.match(line):
                last_include = index
        if last_include >= 0:
            lines[last_include + 1:last_include + 1] = payload.split("\n")
            return "\n".join(lines)
        position = "top"

    if position == "before_main":
        for index, line in enumerate(lines):
            if _MAIN_RE.match(line):
                block = payload.split("\n")
                lines[index:index] = block + [""]
                return "\n".join(lines)
        position = "top"

    # "top": keep the #include directives at the very top
    insert_at = 0
    while insert_at < len(lines) and (
        not lines[insert_at].strip() or _INCLUDE_RE.match(lines[insert_at])
    ):
        insert_at += 1
    block = payload.split("\n")
    if insert_at and block:
        lines[insert_at:insert_at] = [""] + block
    else:
        lines[insert_at:insert_at] = block
    return "\n".join(lines)
