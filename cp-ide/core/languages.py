"""语言识别：按文件扩展名决定编辑模式、预览方式与编译 / 运行策略。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class Language:
    """一种文件类型。"""

    id: str
    name: str
    extensions: Tuple[str, ...]
    cm_mode: str      # CodeMirror 的 mode
    kind: str         # code（可编译运行） / markdown（可渲染） / pdf（只读预览）

    @property
    def runnable(self) -> bool:
        return self.kind == "code"

    @property
    def editable(self) -> bool:
        return self.kind != "pdf"


LANGUAGES: Tuple[Language, ...] = (
    Language(
        "cpp",
        "C++",
        (".cpp", ".cxx", ".cc", ".c", ".h", ".hpp", ".hh", ".hxx", ".inl"),
        "text/x-c++src",
        "code",
    ),
    Language(
        "python",
        "Python",
        (".py", ".pyw", ".pyi"),
        "text/x-python",
        "code",
    ),
    Language(
        "markdown",
        "Markdown",
        (".md", ".markdown", ".mdown", ".mkd"),
        "text/x-markdown",
        "markdown",
    ),
    Language(
        "pdf",
        "PDF",
        (".pdf",),
        "text/plain",
        "pdf",
    ),
    Language(
        "text",
        "纯文本",
        (".txt", ".log", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
         ".csv", ".tsv", ".in", ".out", ".sql", ".sh", ".bat", ".xml", ".html", ".css"),
        "text/plain",
        "text",
    ),
)

BY_ID: Dict[str, Language] = {lang.id: lang for lang in LANGUAGES}
BY_EXT: Dict[str, Language] = {}
for _lang in LANGUAGES:
    for _ext in _lang.extensions:
        BY_EXT.setdefault(_ext, _lang)

#: 认不出来时按纯文本处理（不会误当成 C++ 去编译）
DEFAULT = BY_ID["text"]


def detect(name: str) -> Language:
    """根据文件名判断语言。"""
    ext = os.path.splitext(name or "")[1].lower()
    return BY_EXT.get(ext, DEFAULT)


def get(language_id: str) -> Language:
    """按 id 取语言，认不出来时返回纯文本。"""
    return BY_ID.get((language_id or "").strip().lower(), DEFAULT)
